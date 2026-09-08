# ui_qt/mcp_bridge.py
"""앱 안에서 MCP 서버를 함께 띄운다.

별도 프로세스로 두면 실행권(core.runlock)을 나눠 볼 수 없다. 앱에서 돌리는
매크로와 Claude 가 시작한 매크로가 서로 마우스를 뺏는 것을 막으려면 같은
파이썬 안에 있어야 한다.

127.0.0.1 에만 붙는다. 밖에서는 닿지 않는다.
"""
from __future__ import annotations

import asyncio
import socket
import threading
from typing import Optional

PORT = 3001
HOST = "127.0.0.1"

_thread: Optional[threading.Thread] = None
_error: Optional[str] = None
_port: Optional[int] = None
_toaster = None          # 메인 스레드에 사는 알림 다리
#: 돌고 있는 uvicorn 서버. 직접 들고 있어야 내릴 수 있다 — mcp.run() 에 맡기면
#: 손잡이가 없어 앱을 껐다 켜는 수밖에 없다.
_server = None


def url(port: int = PORT) -> str:
    return f"http://{HOST}:{port}/mcp"


def register_command(port: int = PORT) -> str:
    """Claude Code 에 등록하는 명령. 설정창에서 그대로 보여준다."""
    return ("claude mcp add --transport http --scope user clikey " + url(port))


def port_is_free(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return True


def running() -> bool:
    return _thread is not None and _thread.is_alive()


def status() -> str:
    """설정창에 보여줄 한 줄."""
    if _error:
        return _error
    if running():
        return f"포트 {_port} 에서 대기 중"
    return "꺼져 있음"


def start(port: int = PORT) -> bool:
    """서버를 띄운다. 이미 떠 있으면 아무 일도 하지 않는다."""
    global _thread, _error, _port

    if running():
        return True
    if not port_is_free(port):
        _error = f"포트 {port} 가 이미 쓰이고 있습니다"
        return False

    _error = None
    _port = port
    ready = threading.Event()

    # 알림 다리는 반드시 여기서, 메인 스레드에서 만든다. 서버 스레드에서
    # 만들면 그 QObject 가 서버 스레드에 속하게 되고, 실행 스레드가 보낸
    # 신호는 Qt 이벤트 루프가 없는 그곳에 쌓이기만 해 알림이 뜨지 않는다.
    _attach_toast()

    def serve():
        global _error, _server
        try:
            # uvicorn 은 메인 스레드가 아니면 시그널 핸들러를 걸지 않는다.
            # 다만 이벤트 루프는 이 스레드에 직접 만들어 줘야 한다 — 스레드가
            # 처음이라 루프가 없으면 서버가 뜨기도 전에 넘어진다.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            import uvicorn

            from clikey_mcp import mcp

            # mcp.run() 을 쓰지 않는다. 그쪽은 서버를 안에서 만들고 버려 손잡이가
            # 남지 않아, 끄려면 앱을 통째로 다시 시작해야 한다.
            app = mcp.streamable_http_app(streamable_http_path="/mcp", host=HOST)
            _server = uvicorn.Server(uvicorn.Config(
                app, host=HOST, port=port, log_level="warning"))
            ready.set()
            loop.run_until_complete(_server.serve())
        except Exception as exc:
            _error = f"서버를 띄우지 못했습니다 — {exc}"
        finally:
            _server = None
            ready.set()

    _thread = threading.Thread(target=serve, daemon=True, name="clikey-mcp")
    _thread.start()

    # 임포트에서 넘어지는 것 정도는 바로 알 수 있다. 실제 바인딩까지 기다리지는
    # 않는다 — 앱이 뜨는 것을 붙들 이유가 없다.
    ready.wait(5.0)
    return _error is None


def _attach_toast() -> None:
    """알림 노드를 앱의 토스트에 잇는다.

    화면에 띄우는 일은 UI 스레드에서만 할 수 있으므로 신호를 거쳐 넘긴다 —
    실행 스레드에서 곧바로 부르면 아무것도 뜨지 않는다. 이 함수는 메인
    스레드에서 불러야 한다.
    """
    global _toaster
    try:
        import clikey_mcp

        if _toaster is None:
            _toaster = _Toaster()
        clikey_mcp.set_toast(_toaster.ask)
    except Exception:
        pass


def stop() -> None:
    """서버를 내리고 기다리던 실행을 접는다.

    붙들려 있는 실행부터 풀어준다 — 그대로 두면 마우스를 쥔 채 사라진다.
    """
    global _thread, _server, _port, _error
    try:
        import clikey_mcp

        clikey_mcp.shutdown()
    except Exception:
        pass

    server = _server
    if server is not None:
        # uvicorn 이 제 루프에서 이 값을 들여다본다. 다른 스레드에서 세워도 된다.
        server.should_exit = True

    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(5.0)

    _thread = None
    _server = None
    _port = None
    _error = None


def apply(enabled: bool, port: int) -> None:
    """설정한 대로 서버를 맞춘다. 이미 그 모습이면 아무 일도 하지 않는다.

    켜고 끄는 데 앱을 다시 시작하지 않아도 되게 한다 — 편집기에 손대던 것이
    있으면 재시작이 그것을 날린다.
    """
    if not enabled:
        if running():
            stop()
        return

    if running():
        if _port == port:
            return
        stop()          # 포트가 바뀌었으면 옮겨 앉는다
    start(port)


class _Toaster:
    """알림을 UI 스레드로 넘기는 다리."""

    def __init__(self):
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QApplication

        class Bridge(QObject):
            asked = Signal(str, str, bool, float)

            def __init__(self):
                super().__init__()
                self.asked.connect(self._show)

            @staticmethod
            def _show(title, message, sound, seconds):
                from ui_qt import toast

                toast.show(title, message, sound, seconds)

        self._bridge = Bridge()
        # 앱에 매달아 두어야 가비지 컬렉션에 쓸려가지 않는다
        app = QApplication.instance()
        if app is not None:
            self._bridge.setParent(app)

    def ask(self, title: str, message: str, sound: bool, seconds: float) -> None:
        self._bridge.asked.emit(title, message, sound, seconds)
