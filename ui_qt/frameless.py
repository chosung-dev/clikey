# ui_qt/frameless.py
"""네이티브 타이틀바 없는 창.

Qt 의 FramelessWindowHint 로 기본 테두리를 지우되, WM_NCHITTEST 만 직접
답해준다. 이동·가장자리 리사이즈·스냅·더블클릭 최대화는 전부 Windows 가
원래대로 처리하므로 직접 구현할 게 없다.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QLineEdit, QWidget

WM_NCHITTEST = 0x0084

HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT = 10, 11
HTTOP, HTTOPLEFT, HTTOPRIGHT = 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

RESIZE_MARGIN = 8          # 가장자리에서 리사이즈가 잡히는 두께(논리 px)

# Windows 11 둥근 모서리
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# 창 스타일 (가장자리를 끌어 크기를 바꾸려면 WS_THICKFRAME 이 있어야 한다)
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
SWP_FRAMECHANGED = 0x0020
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0004, 0x0010


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hWnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class FramelessWindow(QWidget):
    """타이틀바 없는 창. 끌어서 옮길 영역은 `is_caption_at()` 으로 정한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self._round_corners()
        self._enable_resizing()

    # ------------------------------------------------------------ 끌 수 있는 영역

    #: 이 위젯 종류 위에서는 창을 끌지 않는다 (클릭이 위젯에 가야 한다)
    INTERACTIVE = (QAbstractButton, QLineEdit, QAbstractSlider)

    def caption_bar(self) -> Optional[QWidget]:
        """끌어서 창을 옮길 수 있는 막대. 하위 클래스가 `_caption_bar` 로 지정한다."""
        return getattr(self, "_caption_bar", None)

    def is_caption_at(self, pos: QPoint) -> bool:
        """이 지점을 끌면 창이 움직여야 하는가.

        상단 막대 안이면 참이지만, 그 위에 놓인 버튼·입력칸 위는 거짓이다.
        여기서 참을 돌려주면 Windows 가 그 클릭을 창 드래그로 가져가 버려서
        버튼이 눌리지 않는다.
        """
        bar = self.caption_bar()
        if bar is None or not self._contains(bar, pos):
            return False

        widget = self.childAt(pos)
        while widget is not None and widget is not bar:
            if isinstance(widget, self.INTERACTIVE):
                return False
            widget = widget.parentWidget()
        return True

    def _contains(self, widget: QWidget, pos: QPoint) -> bool:
        """창 좌표 pos 가 위젯 안인가. 위젯이 몇 겹 안에 있어도 맞게 판정한다."""
        return widget.rect().contains(widget.mapFrom(self, pos))

    # ------------------------------------------------------------ 내부

    def showEvent(self, event):
        # Qt 가 창을 다시 만들면 스타일이 되돌아갈 수 있어 뜰 때마다 확인한다
        super().showEvent(event)
        self._enable_resizing()

    def _enable_resizing(self) -> None:
        """가장자리를 끌어 크기를 바꿀 수 있게 WS_THICKFRAME 을 붙인다.

        WM_NCHITTEST 에 HTLEFT 같은 값을 돌려줘도, 창에 이 스타일이 없으면
        Windows 는 크기를 바꾸지 않는다. 커서 모양만 바뀌고 끌리지 않는다.

        Qt 의 FramelessWindowHint 가 비클라이언트 영역을 이미 없애 두어서,
        이 스타일을 붙여도 테두리가 새로 생기지는 않는다.
        """
        try:
            hwnd = wintypes.HWND(int(self.winId()))
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            if style & WS_THICKFRAME:
                return
            user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)
            user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOSIZE | SWP_NOMOVE
                | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def _round_corners(self) -> None:
        try:
            hwnd = int(self.winId())
            pref = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(pref),
                ctypes.sizeof(pref),
            )
        except Exception:
            pass

    def _hit_test(self, local: QPoint) -> int:
        m = RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = local.x(), local.y()

        if self.isMaximized():
            return HTCAPTION if self.is_caption_at(local) else HTCLIENT

        left, right = x < m, x >= w - m
        top, bottom = y < m, y >= h - m

        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM

        return HTCAPTION if self.is_caption_at(local) else HTCLIENT

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_NCHITTEST:
                # lParam 은 물리 픽셀이다. 모니터마다 배율이 다르면 화면
                # 전체를 한 배율로 나눌 수 없어 (주 모니터 밖에서 좌표가
                # 통째로 어긋난다) Qt 가 이미 맞춰 둔 커서 자리를 쓴다.
                return True, self._hit_test(self.mapFromGlobal(QCursor.pos()))

        return super().nativeEvent(event_type, message)

    # ------------------------------------------------------------ 편의

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
