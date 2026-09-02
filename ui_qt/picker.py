# ui_qt/picker.py
"""주 모니터에서 좌표·색·영역을 집는 오버레이.

화면을 한 장 찍어 그대로 덮어 보여주고, 그 위에서 고르게 한다. 실시간 화면
위에서 고르면 대상이 움직이거나 사라져서 집기 어렵다 — 정지된 그림 위에서
고르는 편이 확실하다.

주 모니터만 다룬다. 모니터마다 배율이 다르면 화면 좌표와 실제 픽셀이 어긋나
여기서 집은 자리와 매크로가 누르는 자리가 달라지는데, 주 모니터로 한정하면
그 어긋남이 아예 생기지 않는다.

    result = pick_from_screen(parent)
    if result:
        print(result.x, result.y, result.rgb)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QDialog

ZOOM = 8                 # 확대경 배율
ZOOM_PIXELS = 15         # 확대경에 보이는 원본 픽셀 수 (한 변)
MAG_SIZE = ZOOM * ZOOM_PIXELS
MAG_GAP = 22             # 커서와 확대경 사이 간격


@dataclass
class PickResult:
    x: int
    y: int
    rgb: Tuple[int, int, int]


class ScreenPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        self.shot, self.origin = self._grab_main_screen()
        self.setGeometry(QRect(self.origin, self.shot.deviceIndependentSize().toSize()))

        self.cursor_at = QPoint(0, 0)
        self.result: Optional[PickResult] = None

    # ------------------------------------------------------------ 화면 찍기

    @staticmethod
    def _grab_main_screen():
        """주 모니터만 한 장 찍는다."""
        screen = QGuiApplication.primaryScreen()
        return screen.grabWindow(0), screen.geometry().topLeft()

    # ------------------------------------------------------------ 값 읽기

    def _local(self, global_pos: QPoint) -> QPoint:
        return global_pos - self.origin

    def color_at(self, global_pos: QPoint) -> Tuple[int, int, int]:
        local = self._local(global_pos)
        ratio = self.shot.devicePixelRatio()
        image = self.shot.toImage()
        x = min(max(int(local.x() * ratio), 0), image.width() - 1)
        y = min(max(int(local.y() * ratio), 0), image.height() - 1)
        color = image.pixelColor(x, y)
        return color.red(), color.green(), color.blue()

    # ------------------------------------------------------------ 그리기

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.shot)

        local = self.cursor_at
        rgb = self.color_at(local + self.origin)

        self._draw_crosshair(painter, local)
        self._draw_magnifier(painter, local, rgb)
        self._draw_hint(painter)

    def _draw_crosshair(self, painter: QPainter, at: QPoint) -> None:
        pen = QPen(QColor(58, 91, 199, 170), 1)
        painter.setPen(pen)
        painter.drawLine(0, at.y(), self.width(), at.y())
        painter.drawLine(at.x(), 0, at.x(), self.height())

    def _draw_magnifier(self, painter: QPainter, at: QPoint,
                        rgb: Tuple[int, int, int]) -> None:
        # 커서 오른쪽 아래에 두되, 화면 밖으로 나가면 반대쪽으로
        box = QRect(at.x() + MAG_GAP, at.y() + MAG_GAP, MAG_SIZE, MAG_SIZE + 34)
        if box.right() > self.width():
            box.moveLeft(at.x() - MAG_GAP - box.width())
        if box.bottom() > self.height():
            box.moveTop(at.y() - MAG_GAP - box.height())

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRoundedRect(box, 8, 8)

        # 확대된 픽셀
        view = QRect(box.x() + 1, box.y() + 1, MAG_SIZE - 2, MAG_SIZE - 2)
        half = ZOOM_PIXELS // 2
        ratio = self.shot.devicePixelRatio()
        source = QRect(int((at.x() - half) * ratio), int((at.y() - half) * ratio),
                       int(ZOOM_PIXELS * ratio), int(ZOOM_PIXELS * ratio))

        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawPixmap(view, self.shot, source)

        # 가운데 한 픽셀 표시
        cell = view.width() / ZOOM_PIXELS
        center = QRect(int(view.x() + cell * half), int(view.y() + cell * half),
                       int(cell), int(cell))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(196, 69, 61), 1.5))
        painter.drawRect(center)

        painter.setPen(QPen(QColor(211, 214, 221), 1))
        painter.drawRect(view)

        # 좌표와 색
        text_box = QRect(box.x(), box.y() + MAG_SIZE, box.width(), 34)
        painter.setPen(QColor(27, 30, 35))
        font = QFont(painter.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)

        swatch = QRect(text_box.x() + 8, text_box.y() + 11, 12, 12)
        painter.setBrush(QColor(*rgb))
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.drawRect(swatch)

        painter.setPen(QColor(27, 30, 35))
        global_at = at + self.origin
        painter.drawText(
            QRect(swatch.right() + 7, text_box.y(), text_box.width() - 34, 34),
            Qt.AlignVCenter | Qt.AlignLeft,
            f"{global_at.x()}, {global_at.y()}\n"
            f"RGB {rgb[0]}, {rgb[1]}, {rgb[2]}",
        )

    def _draw_hint(self, painter: QPainter) -> None:
        text = "클릭해서 이 지점 선택  ·  Esc 취소"
        font = QFont(painter.font())
        font.setPointSizeF(10)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 28
        box = QRect((self.width() - width) // 2, 28, width, 38)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(27, 30, 35, 220))
        painter.drawRoundedRect(box, 19, 19)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(box, Qt.AlignCenter, text)

    # ------------------------------------------------------------ 입력

    def mouseMoveEvent(self, event):
        self.cursor_at = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        at = event.position().toPoint()
        global_at = at + self.origin
        self.result = PickResult(global_at.x(), global_at.y(),
                                 self.color_at(global_at))
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.cursor_at = self._local(QCursor.pos())   # 지금 커서 자리에서 시작
        self.activateWindow()
        self.setFocus()


def pick_from_screen(parent=None) -> Optional[PickResult]:
    """주 모니터를 덮어 좌표·색을 고르게 한다. 취소하면 None."""
    picker = ScreenPicker(parent)
    if picker.exec() == QDialog.Accepted:
        return picker.result
    return None


# ---------------------------------------------------------------- 영역 고르기


class RegionPicker(ScreenPicker):
    """끌어서 네모난 영역을 고른다. 주 모니터만 다루는 것도 같다."""

    MIN_SIDE = 4             # 이보다 작으면 잘못 누른 것으로 본다

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_from: Optional[QPoint] = None
        self.region: Optional[Tuple[int, int, int, int]] = None

    def _selection(self) -> Optional[QRect]:
        if self.drag_from is None:
            return None
        return QRect(self.drag_from, self.cursor_at).normalized()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.shot)

        box = self._selection()
        # 고른 밖은 어둡게 덮어 범위를 또렷하게
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(27, 30, 35, 110))
        if box is None:
            painter.drawRect(self.rect())
        else:
            for part in (QRect(0, 0, self.width(), box.top()),
                         QRect(0, box.bottom() + 1, self.width(),
                               self.height() - box.bottom() - 1),
                         QRect(0, box.top(), box.left(), box.height()),
                         QRect(box.right() + 1, box.top(),
                               self.width() - box.right() - 1, box.height())):
                painter.drawRect(part)

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(58, 91, 199), 1))
            painter.drawRect(box)
            self._draw_size(painter, box)

        if box is None:
            self._draw_crosshair(painter, self.cursor_at)
        self._draw_hint(painter)

    def _draw_size(self, painter: QPainter, box: QRect) -> None:
        text = f"{box.width()} × {box.height()}"
        font = QFont(painter.font())
        font.setPointSizeF(10)
        painter.setFont(font)

        width = painter.fontMetrics().horizontalAdvance(text) + 18
        # 위쪽에 자리가 없으면 네모 안쪽에 붙인다
        top = box.top() - 30 if box.top() > 34 else box.top() + 6
        tag = QRect(box.left(), top, width, 24)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(27, 30, 35, 220))
        painter.drawRoundedRect(tag, 6, 6)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(tag, Qt.AlignCenter, text)

    def _draw_hint(self, painter: QPainter) -> None:
        text = ("끌어서 영역을 고르세요  ·  Esc 취소"
                if self.drag_from is None
                else "손을 떼면 정해집니다  ·  Esc 취소")
        font = QFont(painter.font())
        font.setPointSizeF(10)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 28
        box = QRect((self.width() - width) // 2, 28, width, 38)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(27, 30, 35, 220))
        painter.drawRoundedRect(box, 19, 19)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(box, Qt.AlignCenter, text)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.drag_from = event.position().toPoint()
        self.cursor_at = self.drag_from
        self.update()

    def mouseReleaseEvent(self, event):
        box = self._selection()
        if box is None:
            return
        self.drag_from = None
        if box.width() < self.MIN_SIDE or box.height() < self.MIN_SIDE:
            self.update()               # 잘못 누른 것 — 다시 고르게 둔다
            return

        # 화면 캡처 쪽이 두 모서리를 받으므로 그 꼴로 돌려준다
        top_left = box.topLeft() + self.origin
        self.region = (top_left.x(), top_left.y(),
                       top_left.x() + box.width(), top_left.y() + box.height())
        self.accept()


def pick_region(parent=None) -> Optional[Tuple[int, int, int, int]]:
    """주 모니터를 덮어 영역을 고르게 한다. (x1, y1, x2, y2) 또는 None."""
    picker = RegionPicker(parent)
    if picker.exec() == QDialog.Accepted:
        return picker.region
    return None
