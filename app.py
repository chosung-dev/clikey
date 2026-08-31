"""Clikey 진입점."""
import os
import sys
import threading
import time
import webbrowser

_startup_time = time.perf_counter()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.persistence import load_app_state, save_app_state  # noqa: E402
from core.version import (  # noqa: E402
    __version__,
    get_latest_version,
    get_release_url,
    is_update_available,
)
from ui_qt import theme as T  # noqa: E402
from ui_qt.home import HomeWindow  # noqa: E402
from utils.admin_utils import request_admin_if_needed  # noqa: E402

UPDATE_CHECK_INTERVAL = 86400  # 하루


def check_update(window) -> None:
    """하루에 한 번 새 버전을 확인한다. 실패는 조용히 넘긴다."""
    try:
        state = load_app_state()
        now = time.time()
        if now - state.get("last_update_check", 0) < UPDATE_CHECK_INTERVAL:
            return

        latest = get_latest_version()
        state["last_update_check"] = now
        save_app_state(state)

        if not (latest and is_update_available(__version__, latest)):
            return

        def ask():
            answer = QMessageBox.question(
                window,
                "업데이트 확인",
                f"업데이트가 있습니다.\n다운로드 하러 가시겠습니까?\n\n"
                f"현재 버전: {__version__}\n최신 버전: {latest}",
            )
            if answer == QMessageBox.Yes:
                webbrowser.open(get_release_url())

        # UI 스레드로 넘긴다
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, ask)
    except Exception:
        pass


def main() -> int:
    if not request_admin_if_needed():
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Clikey")
    app.setApplicationDisplayName("Clikey")
    app.setWindowIcon(QIcon(T.APP_ICON))

    window = HomeWindow(ratio=app.devicePixelRatio())
    window.show()

    threading.Thread(target=check_update, args=(window,), daemon=True).start()

    print(f"[Startup] UI ready in {time.perf_counter() - _startup_time:.3f}s")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
