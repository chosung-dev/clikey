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

import math
import os
import queue
import shutil
import tempfile
import threading
import time
from typing import List, Optional

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, Signal
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

#: PNG 압축 세기(0~9). 올려봐야 크기는 조금 줄고 시간은 몇 배가 된다.
PNG_LEVEL = 1

#: 인코딩을 기다리는 장을 몇 개까지 쌓아둘지. 한 장이 2560x1440 에서 11MB 라
#: 무작정 쌓으면 메모리가 그만큼 불어난다. 넘치면 그 박자는 아예 찍지 않는다 —
#: 어차피 뒤에서 소화하지 못하는 속도다.
QUEUE_MAX = 3


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

    def drop_last(self) -> None:
        """마지막 한 장을 목록에서 뺀다.

        파일은 지우지 않는다. 앞 장과 같은 화면이면 여러 자리가 같은 파일을
        가리키므로, 지웠다가는 멀쩡한 앞 장이 함께 사라진다.
        """
        if self._paths:
            self._paths.pop()
            self._cached = None
            self._at = -1

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

    PNG 로 만드는 데 2560x1440 한 장이 200ms 를 넘게 먹는다. 담는 간격보다 긴
    일이라 UI 스레드에서 하면 화면이 그동안 멈춘다 — 깜박임도 초도 뚝뚝 끊기고,
    정작 5fps 도 못 낸다. 그래서 화면을 떠오는 것만 여기서 하고(화면은 UI
    스레드에서만 뜰 수 있다), 견주고 만들어 쓰는 일은 뒷일꾼에게 넘긴다.
    """

    #: 0.0 ~ 1.0. 게이지를 채우는 쪽에서 받는다.
    progress = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store: Optional[FrameStore] = None
        self._queue: Optional[queue.Queue] = None
        self._worker: Optional[threading.Thread] = None
        #: 떠온 장수. 뒷일꾼이 아직 소화하지 못했어도 이만큼은 담긴 것으로 센다.
        self._taken = 0
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------ 뒷일꾼

    @staticmethod
    def _work(store: FrameStore, jobs: "queue.Queue") -> None:
        """떠온 장을 견주고 PNG 로 만들어 쓴다. 이 스레드만 store 를 건드린다."""
        last: Optional[np.ndarray] = None
        while True:
            bgr = jobs.get()
            if bgr is None:              # 그만하라는 신호
                jobs.task_done()
                return
            if last is not None and np.array_equal(bgr, last):
                store.repeat_last()      # 멈춘 화면 — 파일을 늘리지 않는다
            elif store.write(bgr):
                last = bgr
            jobs.task_done()

    def start(self) -> None:
        self.discard()
        _sweep_stale()
        try:
            folder = tempfile.mkdtemp(prefix=TMP_PREFIX)
        except OSError:
            folder = None
        self._store = FrameStore(folder)
        self._queue = queue.Queue(maxsize=QUEUE_MAX)
        self._taken = 0
        self._worker = threading.Thread(
            target=self._work, args=(self._store, self._queue),
            daemon=True, name="clikey-rewind")
        self._worker.start()
        self._tick()            # 누른 그 순간을 놓치지 않는다
        self._timer.start()

    def _tick(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None or self._store is None or self._queue is None:
            return
        # 뒷일꾼이 밀려 있으면 이 박자는 건너뛴다. 떠와 봐야 쌓이기만 하고
        # 그만큼 메모리를 먹는다.
        if self._queue.full():
            return

        bgr = _pixels(screen.grabWindow(0))
        if bgr is None:
            return
        self._queue.put(bgr)
        self._taken += 1

        self.progress.emit(self._taken / MAX_FRAMES)
        if self._taken >= MAX_FRAMES:
            self._timer.stop()

    def recapture_last(self) -> None:
        """마지막 한 장을 지금 화면으로 다시 찍는다.

        담기는 글씨가 바뀌기 전에 이루어지므로, 마지막 장에는 한 박자 전의
        버튼이 찍혀 있다. 그 장으로 피커가 열리면 다 담아놓고도 "9.8초 담는 중"
        이 멈춰 있는 꼴이라, 마무리 모습으로 한 번 갈아 끼운다.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None or self._store is None:
            return
        bgr = _pixels(screen.grabWindow(0))
        if bgr is None:
            return
        self._drain()                      # 뒷일꾼이 밀려 있으면 먼저 비운다
        self._store.drop_last()
        if not self._store.write(bgr):
            self._store.repeat_last()      # 못 썼으면 있던 것으로 되돌린다

    def _drain(self, patience: float = 10.0) -> None:
        """뒷일꾼이 밀린 것을 다 소화할 때까지 기다린다.

        넘기기 전에 반드시 거친다. 아직 만들지 못한 장이 남은 채로 넘기면
        되감을 때 그 자리가 비어 있다.

        버릴 때는 결과가 필요 없으니 오래 붙들지 않는다. 파일을 쓰는 중에
        폴더를 지워도 rmtree 가 그냥 넘어간다.
        """
        if self._queue is None or self._worker is None:
            return
        self._queue.put(None)              # 다 하면 그만두라고 일러둔다
        self._worker.join(patience)
        self._queue = None
        self._worker = None

    def stop(self) -> FrameStore:
        """멈추고 담아둔 묶음을 넘긴다. 넘긴 뒤로는 여기서 들고 있지 않는다.

        지우는 몫도 함께 넘어간다 — 받은 쪽이 다 쓰고 discard() 해야 한다.
        """
        self._timer.stop()
        self._drain()
        store = self._store or FrameStore()
        self._store = None
        self._taken = 0
        return store

    def discard(self) -> None:
        """담아둔 것을 버린다. 임시 폴더까지 지운다."""
        self._timer.stop()
        self._drain(1.0)
        if self._store is not None:
            self._store.discard()
            self._store = None
        self._taken = 0


class HoldToRecordButton(QPushButton):
    """꾹 누르고 있는 동안 화면을 담고, 손을 떼면 그 묶음을 넘기는 버튼.

    담기는 동안에는 붉은 점이 숨 쉬듯 깜박이고 몇 초가 쌓였는지 센다. 차오르는
    막대를 두었더니 끝까지 눌러야 하는 것처럼 읽혔다 — 채울 목표가 있는 모양이라
    그렇다. 녹화는 목표가 없다. 필요한 데까지 담고 떼면 그만이라, 지금 담기고
    있다는 것과 얼마나 쌓였는지만 보여준다.

    끝(10초)은 다다랐을 때에만 말한다. 미리 내걸면 그것이 다시 목표가 된다.
    그리고 다 차면 손을 떼기를 기다리지 않고 그대로 넘어간다 — 더 담기지도
    않는데 붙들고 있으면 멈춘 것처럼 보인다.

    툭 누르고 떼면 한 장만 담겨, 예전처럼 지금 화면 하나로 고르게 된다.
    """

    #: FrameStore — 담은 화면. 받은 쪽이 다 쓰고 discard() 해야 한다.
    recorded = Signal(object)

    DOT_R = 4               # 붉은 점 반지름
    DOT_LEFT = 14           # 왼쪽에서 띄우는 만큼
    PULSE_MS = 16           # 다시 그리는 간격 — 60fps 라야 매끄럽다
    PULSE_SECONDS = 1.1     # 한 번 숨 쉬는 데 걸리는 시간
    NEAR_END = 2.0          # 끝이 이만큼 남았을 때부터 알려준다
    FULL_PAUSE_MS = 320     # 다 찼다고 보여주고 넘어가기까지 두는 틈

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._label = text
        self._frames = 0
        self._holding = False
        self._since = 0.0
        self._recorder = FrameRecorder(self)
        self._recorder.progress.connect(self._on_progress)

        # 담는 간격(200ms)으로는 깜박임도 초도 뚝뚝 끊긴다. 그리는 것만 따로,
        # 훨씬 촘촘히 돌린다.
        self._pulse = QTimer(self)
        self._pulse.setInterval(self.PULSE_MS)
        self._pulse.timeout.connect(self._animate)

    # ------------------------------------------------------------ 담기

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._holding:
            self._holding = True
            self._frames = 0
            self._since = time.monotonic()
            self._recorder.start()
            self._pulse.start()
            self._retitle()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._finish()

    def _finish(self) -> None:
        """담기를 마치고 묶음을 넘긴다. 손을 떼서든, 다 차서든 여기로 온다."""
        if not self._holding:
            return
        self._rest()
        self.setDown(False)         # 다 차서 왔으면 아직 눌려 있다
        store = self._recorder.stop()
        # 받는 쪽이 곧바로 피커를 띄운다. 마우스 사건이나 타이머 안에서 창을
        # 열면 그 자리에 이벤트 루프가 하나 더 얹히므로, 여기서 빠져나온 뒤에
        # 넘긴다.
        QTimer.singleShot(0, lambda: self.recorded.emit(store))

    def _animate(self) -> None:
        """깜박임과 초를 한 박자에 굴린다."""
        self._retitle()
        self.update()

    def _on_progress(self, ratio: float) -> None:
        self._frames = round(ratio * MAX_FRAMES)
        self._retitle()
        if self._frames >= MAX_FRAMES:
            # 곧바로 넘기면 마지막 장에 한 박자 전 글씨(9.8초)가 찍혀 있다.
            # 다 찼다고 그려진 뒤 그 모습으로 마지막 장을 다시 찍고 넘어간다.
            self.repaint()
            self._recorder.recapture_last()
            QTimer.singleShot(self.FULL_PAUSE_MS, self._finish)

    def _elapsed(self) -> float:
        """보여줄 초. 시계로 세되 실제 담긴 것보다 앞서지는 않는다.

        장수로만 세면 0.2초씩 건너뛰어 뚝뚝 끊긴다. 시계로 세면 매끄럽지만,
        담는 것이 밀리는 화면에서는 있지도 않은 길이를 말하게 된다. 그래서
        시계로 세되 담긴 데까지로 묶는다 — 평소에는 시계가 앞서지 않아 그대로
        흐르고, 밀릴 때만 붙잡힌다.
        """
        wall = time.monotonic() - self._since
        return max(0.0, min(wall, (self._frames + 1) / FPS, MAX_SECONDS))

    def _retitle(self) -> None:
        if self._frames >= MAX_FRAMES:
            text = f"{MAX_SECONDS:g}초를 다 담았습니다"
        else:
            seconds = self._elapsed()
            text = f"{seconds:.1f}초 담는 중"
            if MAX_SECONDS - seconds <= self.NEAR_END:
                text += f" · {MAX_SECONDS:g}초까지"
        # 60fps 로 불리지만 글자는 0.1초에 한 번만 바뀐다. 같은 글을 다시
        # 넣으면 버튼이 그때마다 다시 자리를 잡는다.
        if text != self.text():
            self.setText(text)

    def _rest(self) -> None:
        self._holding = False
        self._frames = 0
        self._pulse.stop()
        self.setText(self._label)
        self.update()

    def hideEvent(self, event):
        # 패널이 다시 그려지며 사라질 때 담다 만 것을 들고 가지 않는다
        if self._holding:
            self._rest()
        self._recorder.discard()
        super().hideEvent(event)

    # ------------------------------------------------------------ 붉은 점

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._holding:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 버튼 모서리 밖으로 새지 않게 가둔다
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), T.RADIUS_CTRL, T.RADIUS_CTRL)
        painter.setClipPath(path)

        # 담기고 있다는 것을 아주 옅은 바탕으로도 한 번 더 말해둔다. 칠은
        # 버튼 전체에 고르게 — 어디까지 찼다는 뜻으로 읽히지 않게 한다.
        wash = QColor(T.DANGER)
        wash.setAlpha(16)
        painter.fillRect(QRectF(self.rect()), wash)

        full = self._frames >= MAX_FRAMES
        if full:
            # 다 담겼으면 깜박임을 멈춘다 — 더 눌러도 늘지 않는다는 뜻이다
            alpha = 255
        else:
            phase = ((time.monotonic() - self._since) % self.PULSE_SECONDS
                     / self.PULSE_SECONDS)
            alpha = int(120 + 135 * (0.5 + 0.5 * math.cos(2 * math.pi * phase)))

        dot = QColor(T.DANGER)
        dot.setAlpha(alpha)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(
            QPointF(self.DOT_LEFT, self.height() / 2), self.DOT_R, self.DOT_R)
