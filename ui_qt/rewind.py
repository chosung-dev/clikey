# ui_qt/rewind.py
"""좌표를 집기 직전 몇 초를 되감아 볼 수 있게 화면을 담아두는 장치.

화면이 멈춘 뒤에야 "조금 전 그 순간" 이 필요했다는 것을 알게 되는 일이 잦다.
그렇다고 편집기를 열어둔 내내 화면을 찍으면 컴퓨터가 쉴 틈이 없다. 그래서
버튼을 누르고 있는 동안에만 담는다 — 누른 만큼만 남고, 손을 떼면 멈춘다.

끝을 10초로 잡았다. 짧게 잘라두면 필요한 순간이 그 밖으로 밀려나 손쓸 데가
없지만, 넉넉히 두면 필요한 만큼만 누르고 떼면 그만이다. 끊는 몫은 손에 있다.

담아둔 것은 좌표를 고르고 나면 곧바로 버린다. 1080p 한 장이 8MB 가까이 되어
쓸 일이 끝난 뒤에도 들고 있을 이유가 없다.

    button = HoldToRecordButton("화면에서 좌표 집기")
    button.recorded.connect(self._capture)      # frames: list[QPixmap]
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QPushButton

from ui_qt import theme as T

FPS = 5
MAX_SECONDS = 10.0
MAX_FRAMES = int(FPS * MAX_SECONDS)      # 50 장
INTERVAL_MS = int(1000 / FPS)             # 200ms 마다 한 장


class FrameRecorder(QObject):
    """주 모니터를 일정 간격으로 담는다. 정해진 장수를 채우면 스스로 멈춘다.

    피커가 주 모니터만 다루므로(ui_qt.picker) 여기서도 주 모니터만 담는다.
    """

    #: 0.0 ~ 1.0. 게이지를 채우는 쪽에서 받는다.
    progress = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: List[QPixmap] = []
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.discard()
        self._tick()            # 누른 그 순간을 놓치지 않는다
        self._timer.start()

    def _tick(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self._frames.append(screen.grabWindow(0))
        self.progress.emit(len(self._frames) / MAX_FRAMES)
        if len(self._frames) >= MAX_FRAMES:
            self._timer.stop()

    def stop(self) -> List[QPixmap]:
        """멈추고 담아둔 것을 넘긴다. 넘긴 뒤로는 여기서 들고 있지 않는다."""
        self._timer.stop()
        frames = self._frames
        self._frames = []
        return frames

    def discard(self) -> None:
        """담아둔 것을 버린다. 참조가 끊기면 그 자리에서 풀려난다."""
        self._timer.stop()
        self._frames = []


class HoldToRecordButton(QPushButton):
    """꾹 누르고 있는 동안 화면을 담고, 손을 떼면 그 묶음을 넘기는 버튼.

    누르는 동안 얼마나 담겼는지 버튼 자체에 게이지로 채워 보여준다 — 화면은
    그대로인데 무언가 돌고 있으면 사람은 멈춘 줄로 안다.

    툭 누르고 떼면 한 장만 담긴다. 그때는 되감을 것이 없으니 예전처럼 지금
    화면 하나로 고르게 된다. 끝까지 누르고 있을 일은 드물다 — 필요한 데까지만
    담고 떼면 된다.
    """

    #: list[QPixmap] — 담은 화면. 오래된 것이 앞, 가장 최근이 뒤.
    recorded = Signal(list)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._label = text
        self._ratio = 0.0
        self._holding = False
        self._recorder = FrameRecorder(self)
        self._recorder.progress.connect(self._on_progress)

    # ------------------------------------------------------------ 담기

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._holding:
            self._holding = True
            self._ratio = 0.0
            self.setText("담는 중 — 손을 떼면 멈춤")
            self._recorder.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton or not self._holding:
            return
        self._holding = False
        frames = self._recorder.stop()
        self.setText(self._label)
        self._ratio = 0.0
        self.update()
        self.recorded.emit(frames)

    def _on_progress(self, ratio: float) -> None:
        self._ratio = ratio
        if ratio >= 1.0:
            self.setText(f"{MAX_SECONDS:g}초를 다 담았습니다")
        self.update()

    def hideEvent(self, event):
        # 패널이 다시 그려지며 사라질 때 담다 만 것을 들고 가지 않는다
        self._holding = False
        self._recorder.discard()
        super().hideEvent(event)

    # ------------------------------------------------------------ 게이지

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._ratio <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 버튼 모서리 밖으로 새지 않게 가둔다
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), T.RADIUS_CTRL, T.RADIUS_CTRL)
        painter.setClipPath(path)

        width = self.width() * min(self._ratio, 1.0)

        tint = QColor(T.ACCENT)
        tint.setAlpha(34)
        painter.fillRect(QRectF(0, 0, width, self.height()), tint)

        # 아래쪽 한 줄. 옅은 칠만으로는 얼마나 찼는지 눈에 잘 안 들어온다.
        painter.fillRect(QRectF(0, self.height() - 3, width, 3), QColor(T.ACCENT))
