# ui_qt/runner.py
"""매크로 실행을 UI 스레드 밖에서 돌리고 진행 상황을 신호로 알린다.

매크로가 도는 동안에는 마우스·키보드를 매크로가 가져가므로, 창을 클릭해
멈출 수 없다. 그래서 실행 중에만 매크로의 정지 단축키를 전역으로 걸어 둔다.
"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from core import hotkeys
from core.graph import Graph, GraphExecutor, StopReason
from core.graph.engine import RunResult
from core.keyboard_hotkey import _get_keyboard

STOP_HOTKEY = "f9"

REASON_TEXT = {
    StopReason.COMPLETED: "끝까지 실행했습니다",
    StopReason.STOP_NODE: "중지 노드에서 끝났습니다",
    StopReason.STOPPED: "중지했습니다",
    StopReason.MAX_STEPS: "노드 실행 횟수 상한에 걸렸습니다",
    StopReason.TIMEOUT: "최대 실행 시간을 넘겼습니다",
}


def describe(result: RunResult) -> str:
    if result.reason == StopReason.ERROR:
        return f"오류로 멈췄습니다 — {result.error}"
    head = REASON_TEXT.get(result.reason, result.reason)
    return f"{head} · 노드 {result.steps}회 · {result.elapsed:.1f}초"


class MacroRunner(QObject):
    """그래프 하나를 백그라운드에서 실행한다."""

    started = Signal()
    node_entered = Signal(str)
    finished = Signal(object)          # RunResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._hotkey = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------

    def start(self, graph: Graph, step_delay: float = 0.0,
              mouse_move_duration: float = 0.0,
              max_seconds: Optional[float] = 600.0,
              bind_stop_hotkey: bool = True,
              stop_hotkey: str = STOP_HOTKEY) -> bool:
        """`bind_stop_hotkey=False` 는 부르는 쪽이 정지키를 직접 관리할 때."""
        if self.running:
            return False

        self._stop.clear()
        if bind_stop_hotkey:
            self._bind_stop_hotkey(stop_hotkey)

        executor = GraphExecutor(
            graph,
            stop_callback=self._stop.is_set,
            on_node=self.node_entered.emit,
            step_delay=step_delay,
            mouse_move_duration=mouse_move_duration,
            max_seconds=max_seconds,
        )

        def work():
            try:
                result = executor.run()
            finally:
                self._release_stop_hotkey()
            self.finished.emit(result)

        self._thread = threading.Thread(target=work, daemon=True)
        self.started.emit()
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ 전역 정지키

    def _bind_stop_hotkey(self, key: str = STOP_HOTKEY) -> None:
        key = hotkeys.normalize(key or "")
        if not key or hotkeys.is_bare_modifier(key):
            self._hotkey = None
            return
        try:
            kb = _get_keyboard()
            self._hotkey = kb.add_hotkey(key, self.stop, suppress=False)
        except Exception:
            self._hotkey = None

    def _release_stop_hotkey(self) -> None:
        if self._hotkey is None:
            return
        try:
            _get_keyboard().remove_hotkey(self._hotkey)
        except Exception:
            pass
        self._hotkey = None
