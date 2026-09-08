# core/graph/engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple
import time

from core.graph.model import Graph, Node, resolve_pos

# Lazy imports — core.graph 를 import 하는 것만으로 autoit/keyboard 가 딸려오지 않게.
_mouse = None
_screen = None
_image_matcher = None
_keyboard = None


def _get_mouse():
    global _mouse
    if _mouse is None:
        from core import mouse as m
        _mouse = m
    return _mouse


def _get_screen():
    global _screen
    if _screen is None:
        from core import screen as s
        _screen = s
    return _screen


def _get_image_matcher():
    global _image_matcher
    if _image_matcher is None:
        from core.image_matcher import ImageMatcher
        _image_matcher = ImageMatcher
    return _image_matcher


def _get_keyboard():
    global _keyboard
    if _keyboard is None:
        import keyboard as kb
        _keyboard = kb
    return _keyboard


def _as_fraction(answer):
    """{"x": 0.62, "y": 0.34} 또는 (0.62, 0.34) 를 (x, y) 로. 벗어나면 None."""
    if isinstance(answer, dict):
        pair = (answer.get("x"), answer.get("y"))
    elif isinstance(answer, (list, tuple)) and len(answer) == 2:
        pair = tuple(answer)
    else:
        return None
    try:
        x, y = float(pair[0]), float(pair[1])
    except (TypeError, ValueError):
        return None
    # 영역 밖을 짚은 것은 잘못 받은 답이다. 가장자리로 끌어당기지 않는다.
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return x, y


class StopReason:
    COMPLETED = "completed"      # 갈 곳이 없어 자연히 끝남
    STOP_NODE = "stop_node"      # 중지 노드를 만남
    STOPPED = "stopped"          # 사용자가 정지 (F9)
    MAX_STEPS = "max_steps"      # 노드 실행 횟수 상한
    TIMEOUT = "timeout"          # 최대 실행 시간 초과
    ERROR = "error"              # 노드 실행 중 예외
    NO_DECIDER = "no_decider"    # 판단 노드에 닿았으나 물어볼 상대가 없음
    BAD_DECISION = "bad_decision"  # 선택지에 없는 답을 받음


@dataclass
class RunResult:
    reason: str
    steps: int
    elapsed: float
    last_node: Optional[str] = None
    error: Optional[str] = None


class GraphExecutor:
    """포인터 루프 방식 실행기.

    재귀가 아니라 '현재 노드'를 옮겨가며 도는 구조라, 일시정지·한 단계씩 실행·
    현재 노드 하이라이트가 별도 장치 없이 따라온다.
    """

    def __init__(
        self,
        graph: Graph,
        stop_callback: Optional[Callable[[], bool]] = None,
        on_node: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable[[str, Optional[str]], None]] = None,
        step_delay: float = 0.0,
        mouse_move_duration: float = 0.0,
        notify: Optional[Callable[[str, str, bool, float], None]] = None,
        ask: Optional[Callable[[Node], Optional[str]]] = None,
        max_steps: int = 1_000_000,
        max_seconds: Optional[float] = None,
    ):
        self.graph = graph
        self.stop_callback = stop_callback
        # on_node 는 들어가기 직전, on_exit 는 나가는 포트가 정해진 뒤에 부른다.
        # 편집기 하이라이트는 앞엣것이, 지나온 길 기록은 뒤엣것이 필요하다.
        self.on_node = on_node
        self.on_exit = on_exit
        self.step_delay = step_delay
        self.mouse_move_duration = mouse_move_duration
        # 알림은 화면에 띄우는 일이라 UI 쪽에서 넣어준다. 엔진은 어떤 UI도
        # 알지 못하므로 부르는 쪽이 방법을 건네는 구조로 둔다.
        self.notify = notify
        # 판단을 구하는 방법. notify 와 같은 규칙 — 엔진은 누구에게 어떻게
        # 묻는지 모른다. UI 실행처럼 구할 상대가 없으면 None 이다.
        self.ask = ask
        self.max_steps = max_steps
        self.max_seconds = max_seconds

        self.current: Optional[str] = None
        self.steps = 0
        self.coords: Dict[str, Tuple[int, int]] = {}
        self._loop_counts: Dict[str, int] = {}
        self._started_at = 0.0
        #: 답을 기다린 시간. 최대 실행 시간에서 뺀다 — 사람(또는 Claude)이
        #: 늦게 답한 것을 매크로가 오래 돈 것으로 셀 수는 없다.
        self._waited = 0.0
        #: 노드 실행 중에 정해진 종료 사유. 포트를 돌려줄 수 없는 사정을
        #: step() 에 전한다. None 반환만으로는 '중지 노드' 와 구별되지 않는다.
        self._halt: Optional[str] = None

        self.reset()

    # ------------------------------------------------------------ 제어

    def should_stop(self) -> bool:
        return bool(self.stop_callback()) if self.stop_callback else False

    def reset(self) -> None:
        self.current = self.graph.entry
        self.steps = 0
        self.coords = {}
        self._loop_counts = {}
        self._started_at = time.perf_counter()
        self._waited = 0.0
        self._halt = None

    @property
    def finished(self) -> bool:
        return self.current is None

    @property
    def elapsed(self) -> float:
        """실제로 매크로가 돈 시간. 판단을 기다린 시간은 빼고 센다.

        빼지 않으면 Claude 가 답하는 데 걸린 시간이 최대 실행 시간을 먹어,
        답을 받아 이어 돌자마자 시간 초과로 끊긴다.
        """
        return time.perf_counter() - self._started_at - self._waited

    def step(self) -> Optional[str]:
        """현재 노드 하나를 실행하고 포인터를 옮긴다.

        계속 돌 수 있으면 None, 멈춰야 하면 StopReason 을 반환한다.
        """
        if self.current is None:
            return StopReason.COMPLETED
        if self.should_stop():
            return StopReason.STOPPED
        if self.steps >= self.max_steps:
            return StopReason.MAX_STEPS
        if self.max_seconds is not None and self.elapsed > self.max_seconds:
            return StopReason.TIMEOUT

        node = self.graph.node(self.current)
        if node is None:
            self.current = None
            return StopReason.COMPLETED

        if self.on_node:
            self.on_node(node.id)

        port = self._execute(node)
        self.steps += 1

        if self.on_exit:
            self.on_exit(node.id, port)

        # 노드가 사정을 남겼으면 그것이 종료 사유다. 먼저 봐야 한다 —
        # 포트가 없다는 이유만으로는 중지 노드와 구별할 수 없다.
        if self._halt is not None:
            reason, self._halt = self._halt, None
            self.current = None
            return reason

        if port is None:
            self.current = None
            return StopReason.STOP_NODE

        self.current = self.graph.next_id(node.id, port)
        if self.current is None:
            return StopReason.COMPLETED
        return None

    def run(self) -> RunResult:
        self.reset()
        reason = None
        last = self.current
        try:
            while True:
                last = self.current or last
                reason = self.step()
                if reason is not None:
                    break
                if self.step_delay > 0 and not self._interruptible_sleep(self.step_delay):
                    reason = StopReason.STOPPED
                    break
        except Exception as exc:
            return RunResult(
                reason=StopReason.ERROR,
                steps=self.steps,
                elapsed=self.elapsed,
                last_node=last,
                error=f"{type(exc).__name__}: {exc}",
            )

        return RunResult(
            reason=reason,
            steps=self.steps,
            elapsed=self.elapsed,
            last_node=last,
        )

    def _interruptible_sleep(self, seconds: float) -> bool:
        """정지 요청이 오면 즉시 끊는 대기. 끝까지 잤으면 True."""
        end = time.perf_counter() + seconds
        while True:
            remaining = end - time.perf_counter()
            if remaining <= 0:
                return True
            if self.should_stop():
                return False
            time.sleep(min(remaining, 0.02))

    # ------------------------------------------------------------ 노드 실행

    def _execute(self, node: Node) -> Optional[str]:
        """노드를 실행하고 나갈 포트 이름을 반환. None 이면 흐름 종료."""
        handler = getattr(self, f"_do_{node.type}", None)
        if handler is None:
            # 모르는 노드는 건너뛴다 — 구버전 앱에서 신형 파일을 열었을 때
            return "next"
        return handler(node)

    # --- 흐름 ---

    def _do_start(self, node: Node) -> str:
        return "next"

    def _do_stop(self, node: Node) -> None:
        return None

    def _do_loop(self, node: Node) -> str:
        """몸통을 최대 횟수만큼 되풀이한 뒤 done 으로 나간다.

        세는 것은 '이 노드에 들른 횟수' 가 아니라 '몸통으로 내보낸 횟수' 다.
        들른 횟수로 세면 마지막 한 바퀴가 사라져 max=1 이면 몸통이 한 번도
        돌지 않는다.
        """
        limit = int(node.params.get("max", 0) or 0)
        sent = self._loop_counts.get(node.id, 0)

        if limit <= 0 or sent < limit:      # 0 = 무한
            self._loop_counts[node.id] = sent + 1
            return "loop"

        self._loop_counts[node.id] = 0      # 다시 들어올 때를 위해 초기화
        return "done"

    def _do_ask(self, node: Node) -> Optional[str]:
        """판단을 구하고, 받은 답을 그대로 나갈 포트로 삼는다.

        선택지가 곧 포트라 좌표가 오갈 일이 없다 — 묻는 쪽은 한 단어만
        돌려주면 된다.
        """
        if self.ask is None:
            self._halt = StopReason.NO_DECIDER
            return None

        waiting_from = time.perf_counter()
        try:
            picked = self.ask(node)
        finally:
            self._waited += time.perf_counter() - waiting_from

        # 기다리는 사이에 사용자가 멈췄을 수 있다. 그때 돌아오는 빈 답을
        # '잘못된 선택' 으로 적으면 멈춘 사람에게 엉뚱한 이유가 보인다.
        if self.should_stop():
            self._halt = StopReason.STOPPED
            return None

        # 없는 선택지를 첫 포트로 대신하지 않는다. 잘못 받은 답을 성공으로
        # 위장하면 어디서 어긋났는지 찾을 길이 없다.
        if picked not in node.ports:
            self._halt = StopReason.BAD_DECISION
            return None
        return picked

    def _do_ai_point(self, node: Node) -> Optional[str]:
        """화면에서 짚을 자리를 물어, 그 좌표를 뒤쪽 노드가 쓰게 남긴다.

        받는 값은 픽셀이 아니라 영역 안의 비율(0~1)이다. 그림은 오가는 길에
        줄어들 수 있어 픽셀로 주고받으면 조용히 어긋난다. 비율은 얼마로
        줄어들든 같은 자리를 가리킨다.
        """
        if self.ask is None:
            self._halt = StopReason.NO_DECIDER
            return None

        region = node.params.get("region")
        if not (isinstance(region, (list, tuple)) and len(region) == 4):
            self._halt = StopReason.BAD_DECISION
            return None

        waiting_from = time.perf_counter()
        try:
            answer = self.ask(node)
        finally:
            self._waited += time.perf_counter() - waiting_from

        if self.should_stop():
            self._halt = StopReason.STOPPED
            return None

        if answer is None:
            return "못 찾음"          # 못 찾은 것은 실패가 아니라 갈래다

        spot = _as_fraction(answer)
        if spot is None:
            self._halt = StopReason.BAD_DECISION
            return None

        x1, y1, x2, y2 = (int(v) for v in region)
        self.coords[node.id] = (round(x1 + spot[0] * (x2 - x1)),
                                round(y1 + spot[1] * (y2 - y1)))
        return "찾음"

    def _do_notify(self, node: Node) -> str:
        if self.notify is not None:
            self.notify(
                str(node.params.get("title") or "Clikey"),
                str(node.params.get("message") or ""),
                node.params.get("sound", True) is not False,
                float(node.params.get("seconds", 5) or 5),
            )
        return "next"

    # --- 대기 ---

    def _do_delay(self, node: Node) -> str:
        seconds = float(node.params.get("seconds", 0) or 0)
        if seconds > 0:
            self._interruptible_sleep(seconds)
        return "next"

    # --- 마우스 ---

    def _do_mouse_click(self, node: Node) -> str:
        pos = resolve_pos(node.params.get("pos"), self.coords)
        if pos is None:
            return "next"
        button = node.params.get("button", "left")
        _get_mouse().mouse_move_click(pos[0], pos[1], button, self.mouse_move_duration)
        return "next"

    def _do_mouse_move(self, node: Node) -> str:
        pos = resolve_pos(node.params.get("pos"), self.coords)
        if pos is None:
            return "next"
        _get_mouse().mouse_move_only(pos[0], pos[1], self.mouse_move_duration)
        return "next"

    def _do_mouse_down(self, node: Node) -> str:
        _get_mouse().mouse_down_at_current(node.params.get("button", "left"))
        return "next"

    def _do_mouse_up(self, node: Node) -> str:
        _get_mouse().mouse_up_at_current(node.params.get("button", "left"))
        return "next"

    # --- 키보드 ---

    def _key_action(self, node: Node, action: str) -> str:
        from core.keyboard_hotkey import normalize_key_for_keyboard

        key = normalize_key_for_keyboard(node.params.get("key") or "")
        if not key:
            return "next"
        kb = _get_keyboard()
        try:
            if action == "press":
                kb.press_and_release(key)
            elif action == "down":
                kb.press(key)
            else:
                kb.release(key)
        except Exception:
            pass
        return "next"

    def _do_key_press(self, node: Node) -> str:
        return self._key_action(node, "press")

    def _do_key_down(self, node: Node) -> str:
        return self._key_action(node, "down")

    def _do_key_up(self, node: Node) -> str:
        return self._key_action(node, "up")

    # --- 조건 ---

    def _do_image_match(self, node: Node) -> str:
        template = node.params.get("template")
        if not template:
            return "false"

        region = node.params.get("region")
        region = tuple(region) if isinstance(region, (list, tuple)) and len(region) == 4 else None
        threshold = float(node.params.get("threshold", 0.9))

        found = _get_image_matcher().find_image_on_screen(
            template, threshold=threshold, search_region=region
        )
        if not found:
            return "false"

        self.coords[node.id] = found
        return "true"

    def _do_rgb_match(self, node: Node) -> str:
        pos = resolve_pos(node.params.get("pos"), self.coords)
        if pos is None:
            return "false"

        actual = _get_screen().grab_rgb_at(pos[0], pos[1])
        if actual is None:
            return "false"

        expected = node.params.get("color")
        if not (isinstance(expected, (list, tuple)) and len(expected) == 3):
            return "false"

        tolerance = int(node.params.get("tolerance", 0) or 0)
        if any(abs(int(e) - a) > tolerance for e, a in zip(expected, actual)):
            return "false"

        self.coords[node.id] = pos
        return "true"
