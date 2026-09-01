"""Clikey 진입점."""
import sys
import threading
import time
import webbrowser

_startup_time = time.perf_counter()

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.persistence import load_app_state, save_app_state  # noqa: E402
from core.version import (  # noqa: E402
    __version__,
    get_latest_version,
    get_release_url,
    is_update_available,
)
from ui_qt import dialogs, theme as T  # noqa: E402
from ui_qt.home import HomeWindow  # noqa: E402
from utils.admin_utils import request_admin_if_needed  # noqa: E402

UPDATE_CHECK_INTERVAL = 86400  # 하루


class UpdateChecker(QObject):
    """하루에 한 번 새 버전을 확인한다. 실패는 조용히 넘긴다.

    확인은 네트워크를 타므로 백그라운드에서, 알림은 UI 스레드에서 한다.
    그 사이를 신호로 잇는 이유는 단축키 콜백과 같다 — 백그라운드 스레드에는
    이벤트 루프가 없어 QTimer 로는 아무 일도 일어나지 않는다.
    """

    found = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.found.connect(self._ask)

    def start(self) -> None:
        threading.Thread(target=self._look, daemon=True).start()

    def _look(self) -> None:
        try:
            state = load_app_state()
            now = time.time()
            if now - state.get("last_update_check", 0) < UPDATE_CHECK_INTERVAL:
                return

            latest = get_latest_version()
            save_app_state({"last_update_check": now})

            if latest and is_update_available(__version__, latest):
                self.found.emit(latest)
        except Exception:
            pass

    def _ask(self, latest: str) -> None:
        if dialogs.confirm(
            self.window, "업데이트가 있습니다",
            f"현재 버전 {__version__}\n최신 버전 {latest}\n\n다운로드 페이지를 열까요?",
            ok_text="열기",
        ):
            webbrowser.open(get_release_url())


def main() -> int:
    if not request_admin_if_needed():
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Clikey")
    app.setApplicationDisplayName("Clikey")
    app.setWindowIcon(QIcon(T.APP_ICON))

    window = HomeWindow(ratio=app.devicePixelRatio())
    window.show()

    UpdateChecker(window).start()

    print(f"[Startup] UI ready in {time.perf_counter() - _startup_time:.3f}s")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
