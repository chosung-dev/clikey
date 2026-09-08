# clikey_mcp.py
"""Clikey 를 MCP 서버로 내놓는다 — 목록 보기와 실행, 그리고 판단 받기.

화면을 찍는 툴도, 마우스를 움직이는 툴도 내놓지 않는다. 그것을 열면 좌표를
주고받아야 하고 스크린샷 배율·크롭 원점·멀티모니터 음수 오프셋·DPI 가
한꺼번에 얽힌다. 좌표는 사용자가 편집기에서 픽커로 찍어 그래프 안에 두고,
Claude 는 판단 노드의 선택지 가운데 하나를 이름으로 고르기만 한다.

판단이 필요하면 실행을 그 자리에 세우고 `run_macro` 가 먼저 돌아온다.
`resume_macro` 로 답을 넣으면 이어서 돈다. MCP 의 sampling 을 쓰면 한 번에
끝나지만 Claude Code 가 아직 그것을 지원하지 않아 평범한 툴 두 개로 만든다.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import replace
from typing import Any, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.utilities.types import Image
from mcp_types import TextContent

from core import library, runlock, runreport
from core.graph import Graph, GraphExecutor
from core.graph.model import Node

mcp = MCPServer("Clikey")

#: 판단을 기다리는 시간. 기다리는 동안 매크로는 마우스·키보드를 붙들고 있으므로
#: 넉넉하게 잡을 수 없다. 사람이 승인 버튼을 눌러야 하는 경우까지는 견디되,
#: Claude 가 답하지 않고 사라지면 실행을 접고 실행권을 놓는다.
DECISION_TIMEOUT = 180.0

#: 툴 호출 하나가 붙들려 있을 수 있는 시간의 위쪽 한계
MAX_RUN_SECONDS = 900.0

_runs: Dict[str, "_Run"] = {}
_runs_guard = threading.Lock()

#: 앱이 켜져 있을 때 ui_qt.mcp_bridge 가 넣어준다. 없으면 알림 노드는 조용히
#: 지나간다 — 서버만 따로 띄웠을 때는 화면에 손댈 방법이 없다.
_toast = None


def set_toast(fn) -> None:
    """알림 노드가 쓸 방법을 건넨다. 엔진의 notify 와 같은 규칙이다."""
    global _toast
    _toast = fn


# ---------------------------------------------------------------- 실행 하나


class _Run:
    """돌고 있는 매크로 하나. 판단을 기다리는 동안에도 살아 있다."""

    def __init__(self, name: str, graph: Graph, repeat: int, interval: float,
                 max_seconds: float):
        self.name = name
        self.graph = graph
        self.repeat = repeat
        self.interval = interval
        self.max_seconds = max_seconds

        self.token = secrets.token_hex(4)
        self.stop = threading.Event()
        self.answered = threading.Event()   # resume 이 답을 넣었다
        self.surfaced = threading.Event()   # 물어볼 것이 생겼거나 끝났다

        self.question: Optional[Dict[str, Any]] = None
        self.answer: Optional[str] = None
        self.result = None
        self.path: List[str] = []
        self.done = False
        self.finished_at = 0.0
        #: 답을 기다리다 시간이 다 됐다. 정지와 같은 방법으로 실행을 접지만
        #: 사용자에게는 다른 이유를 보여야 한다.
        self.expired = False
        self.thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------ 판단

    def ask(self, node: Node):
        """엔진이 판단 노드에 닿으면 불린다. 답이 올 때까지 이 자리에 선다.

        고르는 노드(ask)에는 선택지 하나를, 짚는 노드(ai_point)에는 영역 안의
        비율을 돌려준다. 어느 쪽을 물었는지는 kind 로 알린다.
        """
        point = node.type == "ai_point"
        self.question = {
            "kind": "point" if point else "choice",
            "prompt": str(node.params.get("prompt") or ""),
            "choices": [] if point else list(node.ports),
            "shot": _screenshot(node.params.get("region")),
        }
        self.answer = None
        self.answered.clear()
        self.surfaced.set()          # run_macro / resume_macro 를 깨운다

        # 답과 정지를 함께 기다린다. 답만 기다리면 판단 대기 중에 F9 가 듣지
        # 않아, 사용자가 멈출 방법이 사라진다.
        end = time.monotonic() + DECISION_TIMEOUT
        while not self.answered.is_set():
            if self.stop.is_set():
                return None
            if time.monotonic() > end:
                self.expired = True
                self.stop.set()
                return None
            self.answered.wait(0.05)
        return self.answer

    # ------------------------------------------------------------ 실행

    def _work(self) -> None:
        recorder = runreport.PathRecorder(self.graph)
        result = None
        steps = 0
        spent = 0.0
        try:
            with runreport.stop_hotkey(self.stop):
                for turn in range(max(1, self.repeat)):
                    if self.stop.is_set():
                        break
                    if turn and self.stop.wait(max(0.0, self.interval)):
                        break
                    executor = GraphExecutor(
                        self.graph,
                        stop_callback=self.stop.is_set,
                        on_exit=recorder,
                        ask=self.ask,
                        notify=_notify,
                        max_seconds=self.max_seconds,
                    )
                    result = executor.run()
                    # 회차마다 실행기를 새로 만들므로 그대로 두면 마지막 한
                    # 바퀴만 셈에 남는다. 몇 번을 돌았든 합쳐서 보고한다.
                    steps += result.steps
                    spent += result.elapsed
                    if result.reason not in runreport.GOOD_REASONS:
                        break
                if result is not None:
                    result = replace(result, steps=steps,
                                     elapsed=round(spent, 3))
        finally:
            self.result = result
            self.path = recorder.result()
            self.question = None
            self.done = True
            self.finished_at = time.monotonic()
            self.surfaced.set()
            runlock.release()

    def start(self) -> None:
        self.thread = threading.Thread(target=self._work, daemon=True,
                                       name="clikey-run-" + self.token)
        self.thread.start()

    def budget(self) -> float:
        """이 실행이 걸릴 수 있는 시간. repeat 을 셈에 넣는다.

        회차마다 실행기를 새로 만들어 max_seconds 도 회차마다 다시 센다.
        한 회차분만 기다리면 반복 매크로는 늘 '아직 돌고 있음' 으로 돌아간다.
        """
        turns = max(1, self.repeat)
        return min(self.max_seconds * turns + self.interval * (turns - 1) + 5.0,
                   MAX_RUN_SECONDS)

    def wait(self) -> None:
        self.surfaced.wait(self.budget())

    # ------------------------------------------------------------ 결과

    def payload(self) -> list:
        """지금 상태를 툴 결과로. 판단 요청이면 화면 그림을 함께 담는다."""
        if self.done:
            _forget(self.token)
            if self.result is None:
                return [_text({"ok": False, "status": "finished",
                               "reason": "stopped",
                               "text": "실행을 시작하지 못했습니다"})]
            summary = runreport.summarize_run(self.result, self.path)
            if self.expired:
                summary["ok"] = False
                summary["reason"] = "decision_timeout"
                summary["text"] = (
                    "판단을 기다리다 " + str(int(DECISION_TIMEOUT)) +
                    "초가 지나 실행을 접었습니다. 매크로가 마우스·키보드를 "
                    "붙들고 있으므로 오래 기다릴 수 없습니다.")
            return [_text(summary)]

        question = self.question
        if question is None:
            # 기다린 시간 안에 아무 소식이 없다. 실행은 계속 돌고 있다.
            return [_text({
                "ok": True, "status": "running", "token": self.token,
                "text": "아직 돌고 있습니다. 잠시 뒤 check_macro 에 이 token 을 "
                        "넘겨 결과를 받으세요. 사용자는 F9 로 멈출 수 있습니다.",
            })]

        if question["kind"] == "point":
            body = {
                "ok": True,
                "status": "needs_point",
                "token": self.token,
                "prompt": question["prompt"],
                "text": "그림에서 짚을 자리를 찾아 point_macro 를 부르세요. "
                        "x·y 는 픽셀이 아니라 그림 안의 비율입니다 — 왼쪽 위가 "
                        "0,0 이고 오른쪽 아래가 1,1 입니다. 찾지 못했으면 "
                        "found 를 false 로 두세요. token 은 "
                        + self.token + " 입니다.",
            }
        else:
            body = {
                "ok": True,
                "status": "needs_decision",
                "token": self.token,
                "prompt": question["prompt"],
                "choices": question["choices"],
                "text": "화면을 보고 choices 가운데 하나를 골라 resume_macro 를 "
                        "부르세요. token 은 " + self.token + " 입니다.",
            }
        blocks = [_text(body)]
        if question["shot"] is not None:
            blocks.append(Image(data=question["shot"], format="png"))
        return blocks


# ---------------------------------------------------------------- 도우미


def _text(body: Dict[str, Any]) -> TextContent:
    return TextContent(type="text",
                       text=json.dumps(body, ensure_ascii=False, indent=2))


def _notify(title: str, message: str, sound: bool, seconds: float) -> None:
    if _toast is not None:
        _toast(title, message, sound, seconds)


def _screenshot(region) -> Optional[bytes]:
    """판단에 쓸 화면. 못 찍으면 None — 글자만으로도 물을 수는 있다."""
    try:
        import cv2

        from core.image_matcher import ImageMatcher

        box = (tuple(region)
               if isinstance(region, (list, tuple)) and len(region) == 4
               else None)
        frame = ImageMatcher._take_screenshot(box)
        ok, buffer = cv2.imencode(".png", frame)
        return buffer.tobytes() if ok else None
    except Exception:
        return None


def _remember(run: _Run) -> None:
    with _runs_guard:
        _runs[run.token] = run


def _forget(token: str) -> None:
    with _runs_guard:
        _runs.pop(token, None)


def _find(token: str) -> Optional[_Run]:
    with _runs_guard:
        return _runs.get(token)


#: 끝난 실행을 이만큼 두었다가 치운다. 결과를 아직 안 읽어간 것을 곧바로
#: 버리면 '만료된 토큰' 만 돌려주게 된다.
KEEP_FINISHED = 600.0


def _sweep() -> None:
    """읽어가지 않은 채 끝난 실행을 치운다.

    payload() 는 결과를 돌려주면서 지우지만, 아무도 부르지 않으면 그대로
    남는다 — 판단을 받고 답하지 않았거나, 오래 도는 실행을 다시 확인하지
    않은 경우다. 앱이 계속 켜져 있는 프로그램이라 쌓이면 그대로 샌다.
    """
    now = time.monotonic()
    with _runs_guard:
        stale = [t for t, r in _runs.items()
                 if r.done and now - r.finished_at > KEEP_FINISHED]
        for token in stale:
            _runs.pop(token, None)


def _load(name: str):
    """이름으로 매크로를 찾는다. '폴더/이름' 도 받는다."""
    wanted = name.strip().replace(chr(92), "/")
    folder, _, leaf = wanted.rpartition("/")

    hits = [m for m in library.scan()
            if m.folder != library.UNFILED and m.name == leaf
            and (not folder or m.folder == folder)]
    if not hits:
        return None, ("‘" + name + "’ 매크로를 찾을 수 없습니다. "
                      "list_macros 로 이름을 확인하세요.")
    if len(hits) > 1:
        where = ", ".join(m.folder + "/" + m.name for m in hits)
        return None, "같은 이름이 여럿입니다. 폴더까지 적어주세요 — " + where
    return hits[0], ""


# ---------------------------------------------------------------- 툴


@mcp.tool()
def list_macros() -> list:
    """저장된 매크로 목록. run_macro 에 넘길 이름을 여기서 확인한다.

    needs_decision 이 true 인 매크로는 도는 도중에 판단을 물어온다.
    """
    _sweep()
    rows = []
    for entry in library.scan():
        if entry.folder == library.UNFILED:
            continue
        rows.append({
            "name": entry.name,
            "folder": entry.folder,
            "nodes": entry.nodes,
            "enabled": entry.enabled,
            "needs_decision": entry.mcp_only,
            "broken": entry.broken,
        })
    return [_text({"macros": rows, "count": len(rows)})]


@mcp.tool()
def run_macro(name: str, repeat: int = 1, interval: float = 0.0,
              max_seconds: float = 60.0) -> list:
    """매크로를 실행한다.

    끝까지 돌면 결과를, 판단 노드에 닿으면 판단 요청(화면 그림과 선택지)을
    돌려준다. 판단 요청을 받으면 resume_macro 로 답해야 이어서 돈다.

    repeat 와 interval 은 반복을 Clikey 쪽에서 돌기 위한 것이다. 같은 매크로를
    여러 번 부르는 대신 여기에 적으면 툴 호출 한 번으로 끝난다.

    오래 걸려 status "running" 으로 돌아오면 함께 온 token 을 wait_for_macro
    에 넘겨 마저 기다린다.

    사용자는 언제든 F9 로 멈출 수 있다.
    """
    _sweep()
    entry, problem = _load(name)
    if entry is None:
        return [_text({"ok": False, "status": "finished", "text": problem})]
    if not entry.enabled:
        return [_text({"ok": False, "status": "finished",
                       "text": "‘" + entry.name + "’ 은 사용 안 함 상태입니다."})]

    busy = runlock.holder()
    if busy is not None:
        return [_text({"ok": False, "status": "busy",
                       "text": "‘" + busy + "’ 가 돌고 있습니다. 끝나기를 "
                               "기다리거나 F9 로 멈춘 뒤 다시 부르세요."})]

    try:
        graph = Graph.from_json(entry.path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [_text({"ok": False, "status": "finished",
                       "text": "매크로를 읽을 수 없습니다 — " + str(exc)})]

    problems = graph.validate()
    if problems:
        return [_text({"ok": False, "status": "finished",
                       "text": "실행할 수 없는 매크로입니다",
                       "problems": problems[:5]})]

    # 실행권은 하나뿐이다. 앱에서 돌리는 것과도 같은 것을 본다.
    if not runlock.acquire(entry.name):
        return [_text({"ok": False, "status": "busy",
                       "text": "다른 매크로가 먼저 시작했습니다. 잠시 뒤 다시 부르세요."})]

    run = _Run(entry.name, graph, int(repeat), float(interval),
               min(float(max_seconds), MAX_RUN_SECONDS))
    _remember(run)
    run.start()
    run.wait()
    return run.payload()


@mcp.tool()
def resume_macro(token: str, choice: str) -> list:
    """판단 요청에 답하고 실행을 이어간다.

    choice 는 판단 요청의 choices 에 있던 값 그대로여야 한다. 다른 값을 주면
    엉뚱한 곳으로 가지 않고 그 자리에서 멈춘다.
    """
    run = _find(token)
    if run is None:
        return [_text({"ok": False, "status": "finished",
                       "text": "만료되었거나 없는 요청입니다. "
                               "run_macro 로 다시 실행하세요."})]
    if run.done:
        return run.payload()

    question = run.question
    if question is None:
        return [_text({"ok": True, "status": "running", "token": token,
                       "text": "지금은 판단을 기다리는 중이 아닙니다."})]
    if question["kind"] == "point":
        return [_text({"ok": False, "status": "needs_point", "token": token,
                       "text": "이 자리는 고르는 것이 아니라 짚는 것입니다. "
                               "point_macro 를 부르세요."})]

    allowed = question["choices"]
    if choice not in allowed:
        return [_text({"ok": False, "status": "needs_decision", "token": token,
                       "choices": allowed,
                       "text": "‘" + str(choice) + "’ 는 선택지에 없습니다. "
                               + ", ".join(allowed) + " 가운데 하나를 고르세요."})]

    run.surfaced.clear()
    run.answer = choice
    run.answered.set()
    run.wait()
    return run.payload()


@mcp.tool()
def check_macro(token: str) -> list:
    """아직 돌고 있는 실행의 결과를 받아온다.

    run_macro 가 status "running" 으로 돌아왔을 때 쓴다. 기다리지 않고 지금
    상태를 그대로 준다 — 끝났으면 결과를, 판단을 기다리는 중이면 그 요청을.
    기다리려면 wait_for_macro 를 쓴다.
    """
    return _peek(token, 0.0)


@mcp.tool()
def wait_for_macro(token: str, wait_seconds: float = 30.0) -> list:
    """돌고 있는 실행이 끝나거나 판단을 물어올 때까지 기다린다.

    check_macro 를 여러 번 부르는 대신 한 번에 기다린다. 그 안에 끝나지
    않으면 다시 "running" 으로 돌아오므로 또 부르면 된다.
    """
    return _peek(token, max(0.0, min(float(wait_seconds), 300.0)))


def _peek(token: str, seconds: float) -> list:
    _sweep()
    run = _find(token)
    if run is None:
        return [_text({"ok": False, "status": "finished",
                       "text": "만료되었거나 없는 토큰입니다. "
                               "run_macro 로 다시 실행하세요."})]
    if seconds and not run.done and run.question is None:
        run.surfaced.wait(seconds)
    return run.payload()


@mcp.tool()
def point_macro(token: str, x: float = 0.0, y: float = 0.0,
                found: bool = True) -> list:
    """‘AI 위치 찾기’ 요청에 자리를 짚어주고 실행을 이어간다.

    x 와 y 는 픽셀이 아니라 받은 그림 안의 비율이다 — 왼쪽 위가 (0, 0),
    오른쪽 아래가 (1, 1). 그림은 오가는 길에 줄어들 수 있어 픽셀로 주고받으면
    조용히 어긋나지만, 비율은 얼마로 줄어들든 같은 자리를 가리킨다.

    찾지 못했으면 found 를 false 로 둔다 — 그러면 '못 찾음' 갈래로 나간다.
    """
    _sweep()
    run = _find(token)
    if run is None:
        return [_text({"ok": False, "status": "finished",
                       "text": "만료되었거나 없는 요청입니다. "
                               "run_macro 로 다시 실행하세요."})]
    if run.done:
        return run.payload()

    question = run.question
    if question is None:
        return [_text({"ok": True, "status": "running", "token": token,
                       "text": "지금은 짚을 자리를 기다리는 중이 아닙니다."})]
    if question["kind"] != "point":
        return [_text({"ok": False, "status": "needs_decision", "token": token,
                       "choices": question["choices"],
                       "text": "이 자리는 짚는 것이 아니라 고르는 것입니다. "
                               "resume_macro 를 부르세요."})]

    if found and not (0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0):
        return [_text({"ok": False, "status": "needs_point", "token": token,
                       "text": "x 와 y 는 0 과 1 사이의 비율이어야 합니다. "
                               "픽셀 값을 넣지 마세요."})]

    run.surfaced.clear()
    run.answer = {"x": float(x), "y": float(y)} if found else None
    run.answered.set()
    run.wait()
    return run.payload()


def shutdown() -> None:
    """앱을 닫을 때 기다리고 있는 실행을 모두 접는다."""
    with _runs_guard:
        runs = list(_runs.values())
        _runs.clear()
    for run in runs:
        run.stop.set()
        run.answered.set()
