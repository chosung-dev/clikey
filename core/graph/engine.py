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


class StopReason:
    COMPLETED = "completed"      # 갈 곳이 없어 자연히 끝남
    STOP_NODE = "stop_node"      # 중지 노드를 만남
    STOPPED = "stopped"          # 사용자가 정지 (F9)
    MAX_STEPS = "max_steps"      # 노드 실행 횟수 상한
    TIMEOUT = "timeout"          # 최대 실행 시간 초과
    ERROR = "error"              # 노드 실행 중 예외


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
        step_delay: float = 0.0,
        mouse_move_duration: float = 0.0,
        max_steps: int = 1_000_000,
        max_seconds: Optional[float] = None,
    ):
        self.graph = graph
        self.stop_callback = stop_callback
        self.on_node = on_node
        self.step_delay = step_delay
        self.mouse_move_duration = mouse_move_duration
        self.max_steps = max_steps
        self.max_seconds = max_seconds

        self.current: Optional[str] = None
        self.steps = 0
        self.coords: Dict[str, Tuple[int, int]] = {}
        self._loop_counts: Dict[str, int] = {}
        self._started_at = 0.0

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

    @property
    def finished(self) -> bool:
        return self.current is None

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
        if self.max_seconds is not None and (time.perf_counter() - self._started_at) > self.max_seconds:
            return StopReason.TIMEOUT

        node = self.graph.node(self.current)
        if node is None:
            self.current = None
            return StopReason.COMPLETED

        if self.on_node:
            self.on_node(node.id)

        port = self._execute(node)
        self.steps += 1

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
                elapsed=time.perf_counter() - self._started_at,
                last_node=last,
                error=f"{type(exc).__name__}: {exc}",
            )

        return RunResult(
            reason=reason,
            steps=self.steps,
            elapsed=time.perf_counter() - self._started_at,
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
        limit = int(node.params.get("max", 0) or 0)
        count = self._loop_counts.get(node.id, 0) + 1

        if limit <= 0:                      # 0 = 무한
            self._loop_counts[node.id] = count
            return "loop"

        if count < limit:
            self._loop_counts[node.id] = count
            return "loop"

        self._loop_counts[node.id] = 0      # 다시 들어올 때를 위해 초기화
        return "done"

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
