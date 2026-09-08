"""Clikey 진입점."""
import sys
import threading
import time
import webbrowser

_startup_time = time.perf_counter()

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import prefs  # noqa: E402
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

    # Claude MCP 연동. 켜져 있을 때만 포트를 연다. 설정에서 켜고 끄면
    # 같은 길(mcp_bridge.apply)로 그 자리에서 따라간다.
    from ui_qt import mcp_bridge  # noqa: E402

    settings = prefs.load()
    mcp_bridge.apply(bool(settings.get("mcp_enabled")),
                     int(settings.get("mcp_port") or mcp_bridge.PORT))

    print(f"[Startup] UI ready in {time.perf_counter() - _startup_time:.3f}s")
    try:
        return app.exec()
    finally:
        # 붙들려 있는 실행을 먼저 풀어준다 — 그대로 두면 마우스를 쥔 채
        # 프로세스가 사라진다
        mcp_bridge.stop()
        # 알림을 띄웠다면 알림 영역에 아이콘이 남아 있다
        from ui_qt import toast
        toast.close()


if __name__ == "__main__":
    sys.exit(main())
