# ui_qt/rewind.py
"""좌표를 집기 직전 몇 초를 되감아 볼 수 있게 화면을 담아두는 장치.

화면이 멈춘 뒤에야 "조금 전 그 순간" 이 필요했다는 것을 알게 되는 일이 잦다.
그렇다고 편집기를 열어둔 내내 화면을 찍으면 컴퓨터가 쉴 틈이 없다. 그래서
버튼을 누르고 있는 동안에만 담는다 — 누른 만큼만 남고, 손을 떼면 멈춘다.

끝을 10초로 잡았다. 짧게 잘라두면 필요한 순간이 그 밖으로 밀려나 손쓸 데가
없지만, 넉넉히 두면 필요한 만큼만 누르고 떼면 그만이다. 끊는 몫은 손에 있다.

담은 것을 그대로 들고 있으면 1080p 쉰 장이 400MB 다. 그래서 세 가지를 한다.

1. 앞 장과 화면이 똑같으면 새로 쓰지 않고 같은 파일을 다시 가리킨다. 화면이
   멈춰 있으면 쉰 장이 파일 몇 개로 끝난다.
2. PNG 로 담는다. 무손실이라 집는 좌표와 색이 조금도 달라지지 않는다.
   글자와 단색이 많은 화면은 400MB 가 1MB 아래로, 잡음이 많은 게임 화면도
   절반으로 줄어든다.
3. 임시 폴더에 두고 메모리에는 지금 보는 한 장만 둔다. 그래서 화면 내용과
   상관없이 15MB 안팎으로 일정하다.

담아둔 것은 좌표를 고르고 나면 폴더째 지운다.

    button = HoldToRecordButton("화면에서 좌표 집기")
    button.recorded.connect(self._capture)      # store: FrameStore
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from typing import List, Optional

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QPushButton

from ui_qt import theme as T

FPS = 5
MAX_SECONDS = 10.0
MAX_FRAMES = int(FPS * MAX_SECONDS)      # 50 장
INTERVAL_MS = int(1000 / FPS)            # 200ms 마다 한 장

TMP_PREFIX = "clikey-rewind-"
#: 앱이 갑자기 꺼지면 임시 폴더가 남는다. 다음에 담을 때 이보다 오래된 것을 쓸어낸다.
STALE_SECONDS = 3600

#: PNG 압축 세기(0~9). 1 이면 한 장에 40ms 안쪽이라 5fps 예산에 든다. 올려봐야
#: 크기는 조금 줄고 시간은 몇 배가 되어, 담는 쪽에서는 남는 장사가 아니다.
PNG_LEVEL = 1


def _pixels(pixmap: QPixmap) -> Optional[np.ndarray]:
    """QPixmap 을 (높이, 너비, 3) BGR 배열로 옮긴다. cv2 가 바로 받는 꼴이다.

    BGR888 로 바꿔 받으면 알파가 떨어져 나가 셀 것이 4분의 3으로 준다. 줄마다
    남는 자리(bytesPerLine)가 있을 수 있어 그만큼 잘라낸다.
    """
    if pixmap.isNull():
        return None
    image = pixmap.toImage().convertToFormat(QImage.Format_BGR888)
    height, width, stride = image.height(), image.width(), image.bytesPerLine()
    flat = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride * height)
    return flat.reshape(height, stride)[:, :width * 3].reshape(height, width, 3).copy()


def _sweep_stale() -> None:
    """지난번에 남은 임시 폴더를 쓸어낸다. 우리 것만, 충분히 오래된 것만."""
    root = tempfile.gettempdir()
    now = time.time()
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        if not name.startswith(TMP_PREFIX):
            continue
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) > STALE_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


class FrameStore:
    """담아둔 화면 묶음.

    장마다 임시 파일 하나를 가리킨다. 앞 장과 화면이 같으면 새로 쓰지 않고 같은
    파일을 다시 가리키므로, 목록의 길이는 "담은 장수" 이고 파일 수는 그보다
    적거나 같다.

    꺼내 본 한 장만 메모리에 둔다. 되감기는 한 장씩 오가는 일이라 그것으로 넉넉하다.
    """

    def __init__(self, folder: Optional[str] = None):
        self._folder = folder
        self._paths: List[str] = []
        #: 파일 없이 들고 있는 한 장. 담지 않고 지금 화면만 볼 때 쓴다.
        self._live: Optional[QPixmap] = None
        self._at = -1
        self._cached: Optional[QPixmap] = None

    @classmethod
    def of(cls, pixmap: QPixmap) -> "FrameStore":
        """한 장짜리 묶음. 파일을 만들지 않는다."""
        store = cls()
        store._live = pixmap
        return store

    def __len__(self) -> int:
        if self._live is not None:
            return 0 if self._live.isNull() else 1
        return len(self._paths)

    def pixmap(self, index: int) -> Optional[QPixmap]:
        if self._live is not None:
            return self._live
        if not self._paths:
            return None
        index = min(max(index, 0), len(self._paths) - 1)
        if index != self._at or self._cached is None:
            self._cached = QPixmap(self._paths[index])
            self._at = index
        return self._cached

    # ------------------------------------------------------------ 담기

    def write(self, bgr: np.ndarray) -> bool:
        """새 화면을 파일로 남긴다."""
        if self._folder is None:
            return False
        ok, encoded = cv2.imencode(
            ".png", bgr, [int(cv2.IMWRITE_PNG_COMPRESSION), PNG_LEVEL])
        if not ok:
            return False
        path = os.path.join(self._folder, f"{len(self._paths):04d}.png")
        try:
            with open(path, "wb") as out:
                out.write(encoded.tobytes())
        except OSError:
            return False
        self._paths.append(path)
        return True

    def repeat_last(self) -> bool:
        """앞 장과 같은 화면 — 파일을 새로 쓰지 않고 그것을 다시 가리킨다."""
        if not self._paths:
            return False
        self._paths.append(self._paths[-1])
        return True

    # ------------------------------------------------------------ 버리기

    def discard(self) -> None:
        """들고 있던 것과 임시 폴더를 지운다. 두 번 불러도 탈이 없다."""
        self._cached = None
        self._live = None
        self._at = -1
        self._paths = []
        if self._folder is not None:
            shutil.rmtree(self._folder, ignore_errors=True)
            self._folder = None


class FrameRecorder(QObject):
    """주 모니터를 일정 간격으로 담는다. 정해진 장수를 채우면 스스로 멈춘다.

    피커가 주 모니터만 다루므로(ui_qt.picker) 여기서도 주 모니터만 담는다.
    """

    #: 0.0 ~ 1.0. 게이지를 채우는 쪽에서 받는다.
    progress = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store: Optional[FrameStore] = None
        #: 앞 장의 픽셀. 같은 화면인지 견주려고 한 장만 들고 있는다.
        self._last: Optional[np.ndarray] = None
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.discard()
        _sweep_stale()
        try:
            folder = tempfile.mkdtemp(prefix=TMP_PREFIX)
        except OSError:
            folder = None
        self._store = FrameStore(folder)
        self._tick()            # 누른 그 순간을 놓치지 않는다
        self._timer.start()

    def _tick(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None or self._store is None:
            return

        bgr = _pixels(screen.grabWindow(0))
        if bgr is None:
            return

        if self._last is not None and np.array_equal(bgr, self._last):
            self._store.repeat_last()       # 멈춘 화면 — 파일을 늘리지 않는다
        elif self._store.write(bgr):
            self._last = bgr

        kept = len(self._store)
        self.progress.emit(kept / MAX_FRAMES)
        if kept >= MAX_FRAMES:
            self._timer.stop()

    def stop(self) -> FrameStore:
        """멈추고 담아둔 묶음을 넘긴다. 넘긴 뒤로는 여기서 들고 있지 않는다.

        지우는 몫도 함께 넘어간다 — 받은 쪽이 다 쓰고 discard() 해야 한다.
        """
        self._timer.stop()
        store = self._store or FrameStore()
        self._store = None
        self._last = None
        return store

    def discard(self) -> None:
        """담아둔 것을 버린다. 임시 폴더까지 지운다."""
        self._timer.stop()
        if self._store is not None:
            self._store.discard()
            self._store = None
        self._last = None


class HoldToRecordButton(QPushButton):
    """꾹 누르고 있는 동안 화면을 담고, 손을 떼면 그 묶음을 넘기는 버튼.

    누르는 동안 얼마나 담겼는지 버튼 자체에 게이지로 채워 보여준다 — 화면은
    그대로인데 무언가 돌고 있으면 사람은 멈춘 줄로 안다.

    툭 누르고 떼면 한 장만 담긴다. 그때는 되감을 것이 없으니 예전처럼 지금
    화면 하나로 고르게 된다. 끝까지 누르고 있을 일은 드물다 — 필요한 데까지만
    담고 떼면 된다.
    """

    #: FrameStore — 담은 화면. 받은 쪽이 다 쓰고 discard() 해야 한다.
    recorded = Signal(object)

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
        store = self._recorder.stop()
        self.setText(self._label)
        self._ratio = 0.0
        self.update()
        self.recorded.emit(store)

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
