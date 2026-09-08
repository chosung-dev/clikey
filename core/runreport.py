# core/runreport.py
"""실행 결과를 사람과 Claude 가 읽을 수 있는 모양으로 옮긴다.

`ui_qt/runner.py` 에 있던 것을 내려왔다. MCP 서버가 같은 문구를 써야 하는데,
거기에 두면 서버가 PySide6 를 통째로 끌고 온다. 정지 단축키를 잡았다 놓는
일도 UI 와 무관하므로 함께 내렸다.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from core import hotkeys
from core.graph import StopReason
from core.graph.engine import RunResult

STOP_HOTKEY = "f9"

REASON_TEXT = {
    StopReason.COMPLETED: "끝까지 실행했습니다",
    StopReason.STOP_NODE: "중지 노드에서 끝났습니다",
    StopReason.STOPPED: "중지했습니다",
    StopReason.MAX_STEPS: "노드 실행 횟수 상한에 걸렸습니다",
    StopReason.TIMEOUT: "최대 실행 시간을 넘겼습니다",
    StopReason.NO_DECIDER: "판단할 상대가 없어 멈췄습니다",
    StopReason.BAD_DECISION: "선택지에 없는 답을 받아 멈췄습니다",
}

#: 매크로가 뜻대로 끝난 사유. 나머지는 실패로 본다.
GOOD_REASONS = frozenset({StopReason.COMPLETED, StopReason.STOP_NODE})


def describe(result: RunResult) -> str:
    if result.reason == StopReason.ERROR:
        return f"오류로 멈췄습니다 — {result.error}"
    head = REASON_TEXT.get(result.reason, result.reason)
    return f"{head} · 노드 {result.steps}회 · {result.elapsed:.1f}초"


def summarize_run(result: RunResult, path: Optional[List[str]] = None) -> Dict[str, Any]:
    """MCP 툴이 돌려줄 결과.

    `path` 를 함께 담는 것이 여기서 값을 한다. 사유만으로는 "끝까지
    실행했습니다" 밖에 말할 수 없지만, 어느 조건에서 갈라졌는지 알면 왜 아무
    일도 없었는지 짚어줄 수 있다.
    """
    summary: Dict[str, Any] = {
        "ok": result.reason in GOOD_REASONS,
        "status": "finished",
        "reason": result.reason,
        "steps": result.steps,
        "elapsed": round(result.elapsed, 1),
        "text": describe(result),
    }
    if path:
        summary["path"] = list(path)
    if result.error:
        summary["error"] = result.error
    return summary


class PathRecorder:
    """지나온 길 가운데 갈라진 곳만 남긴다.

    전부 남기면 반복 매크로에서 수천 줄이 되고, 정작 알고 싶은 "어느 쪽으로
    갔는가" 가 묻힌다. 나갈 포트가 둘 이상인 노드만 적는다.
    """

    def __init__(self, graph, limit: int = 40):
        self.graph = graph
        self.limit = limit
        self.entries: List[str] = []
        self._dropped = 0

    def __call__(self, node_id: str, port: Optional[str]) -> None:
        node = self.graph.node(node_id)
        if node is None or len(node.ports) < 2:
            return
        if len(self.entries) >= self.limit:
            self._dropped += 1
            return
        label = node.name or node.type
        self.entries.append(f"{label}({node_id}) → {port or '없음'}")

    def result(self) -> List[str]:
        if self._dropped:
            return self.entries + [f"… 그 밖에 {self._dropped}회"]
        return list(self.entries)


@contextmanager
def stop_hotkey(stop: threading.Event, key: str = STOP_HOTKEY):
    """실행 중에만 전역 정지키를 걸어 둔다.

    매크로가 도는 동안에는 마우스·키보드를 매크로가 가져가므로 창을 클릭해
    멈출 수 없다. 잡지 못해도 실행은 그대로 간다 — 멈출 길이 하나 없어질 뿐
    실행 자체를 막을 일은 아니다.
    """
    from core.keyboard_hotkey import _get_keyboard

    handle = None
    name = hotkeys.normalize(key or "")
    if name and not hotkeys.is_bare_modifier(name):
        try:
            handle = _get_keyboard().add_hotkey(name, stop.set, suppress=False)
        except Exception:
            handle = None
    try:
        yield
    finally:
        if handle is not None:
            try:
                _get_keyboard().remove_hotkey(handle)
            except Exception:
                pass
