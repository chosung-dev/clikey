# ui_qt/toast.py
"""화면 오른쪽 아래 윈도우 알림.

Qt 의 QSystemTrayIcon.showMessage 로도 띄울 수 있지만 소리를 끌 방법이 없고
정보 아이콘도 빠지지 않는다. 윈도우 셸을 직접 불러 둘 다 고른다.

알림을 띄우려면 알림 영역에 아이콘이 하나 있어야 한다. 보이지 않는 창을
하나 만들어 그 아이콘을 붙여두고, 앱이 사는 동안 함께 둔다.

    from ui_qt import toast
    toast.show("Clikey", "매크로가 끝났습니다", sound=True)
"""
from __future__ import annotations

from typing import Optional

import win32api
import win32con
import win32gui

from ui_qt import theme as T

# Shell_NotifyIcon 에 넘기는 값들
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_NONE, NIIF_NOSOUND = 0x00, 0x10

WINDOW_CLASS = "ClikeyToastHost"
DEFAULT_TITLE = "Clikey"


class _Host:
    """알림을 붙여둘 보이지 않는 창 하나."""

    def __init__(self) -> None:
        instance = win32api.GetModuleHandle(None)

        spec = win32gui.WNDCLASS()
        spec.hInstance = instance
        spec.lpszClassName = WINDOW_CLASS
        spec.lpfnWndProc = {win32con.WM_DESTROY: lambda *a: 0}
        self.atom = win32gui.RegisterClass(spec)
        self.instance = instance

        self.hwnd = win32gui.CreateWindow(
            self.atom, DEFAULT_TITLE, win32con.WS_OVERLAPPED,
            0, 0, 0, 0, 0, 0, instance, None)

        self.icon = self._load_icon(instance)
        win32gui.Shell_NotifyIcon(
            NIM_ADD,
            (self.hwnd, 0, NIF_ICON | NIF_TIP, 0, self.icon, DEFAULT_TITLE))

    @staticmethod
    def _load_icon(instance):
        try:
            return win32gui.LoadImage(
                instance, T.APP_ICON, win32con.IMAGE_ICON, 0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        except Exception:
            return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def balloon(self, title: str, message: str, sound: bool,
                seconds: float) -> None:
        flags = NIIF_NONE if sound else NIIF_NONE | NIIF_NOSOUND
        win32gui.Shell_NotifyIcon(
            NIM_MODIFY,
            (self.hwnd, 0, NIF_INFO, 0, self.icon, DEFAULT_TITLE,
             message, int(seconds * 1000), title, flags))

    def close(self) -> None:
        try:
            win32gui.Shell_NotifyIcon(NIM_DELETE, (self.hwnd, 0))
            win32gui.DestroyWindow(self.hwnd)
            win32gui.UnregisterClass(self.atom, self.instance)
        except Exception:
            pass


_host: Optional[_Host] = None


def show(title: str, message: str, sound: bool = True,
         seconds: float = 5.0) -> bool:
    """알림을 띄운다. 띄우지 못하면 False.

    UI 스레드에서 불러야 한다 — 창을 만들고 그 창이 메시지를 받아야 한다.
    """
    global _host
    try:
        if _host is None:
            _host = _Host()
        # 윈도우는 내용이 빈 알림을 그냥 버린다. 아무 일도 없던 것처럼 보이므로
        # 비어 있으면 앱 이름으로 채워 어쨌든 뜨게 한다.
        _host.balloon(title or DEFAULT_TITLE, message or DEFAULT_TITLE,
                      sound, seconds)
        return True
    except Exception:
        return False


def close() -> None:
    """앱을 닫을 때 알림 영역에서 아이콘을 거둔다."""
    global _host
    if _host is not None:
        _host.close()
        _host = None
