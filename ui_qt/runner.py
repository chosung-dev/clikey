# ui_qt/runner.py
"""매크로 실행을 UI 스레드 밖에서 돌리고 진행 상황을 신호로 알린다.

매크로가 도는 동안에는 마우스·키보드를 매크로가 가져가므로, 창을 클릭해
멈출 수 없다. 그래서 실행 중에만 매크로의 정지 단축키를 전역으로 걸어 둔다.
"""
from __future__ import annotations

import threading
from contextlib import nullcontext
from typing import Optional

from PySide6.QtCore import QObject, Signal

from core.graph import Graph, GraphExecutor
from core.runreport import stop_hotkey as _stop_hotkey

# 문구와 정지키 관리는 core/runreport.py 에 있다 — MCP 서버도 같은 것을 쓴다.
# 여기서 다시 내보내는 것은 이미 ui_qt.runner 에서 가져다 쓰는 곳이 있어서다.
from core.runreport import REASON_TEXT, STOP_HOTKEY, describe  # noqa: F401


class MacroRunner(QObject):
    """그래프 하나를 백그라운드에서 실행한다."""

    started = Signal()
    node_entered = Signal(str)
    # 알림 노드는 실행 스레드에서 닿는다. 화면에 띄우는 일은 UI 스레드에서만
    # 할 수 있으므로 신호로 넘긴다.
    notify_asked = Signal(str, str, bool, float)
    finished = Signal(object)          # RunResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self.notify_asked.connect(self._show_toast)
        self._stop = threading.Event()

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

        executor = GraphExecutor(
            graph,
            stop_callback=self._stop.is_set,
            on_node=self.node_entered.emit,
            step_delay=step_delay,
            mouse_move_duration=mouse_move_duration,
            notify=self.notify_asked.emit,
            max_seconds=max_seconds,
        )

        # 매크로가 도는 동안에는 마우스·키보드를 매크로가 가져가 창을 클릭해
        # 멈출 수 없다. 그래서 실행 중에만 전역 정지키를 걸어 둔다.
        guard = (_stop_hotkey(self._stop, stop_hotkey) if bind_stop_hotkey
                 else nullcontext())

        def work():
            with guard:
                result = executor.run()
            self.finished.emit(result)

        self._thread = threading.Thread(target=work, daemon=True)
        self.started.emit()
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------

    @staticmethod
    def _show_toast(title: str, message: str, sound: bool,
                    seconds: float) -> None:
        from ui_qt import toast

        toast.show(title, message, sound, seconds)
