# ui_qt/dialogs.py
"""앱 디자인에 맞춘 대화상자.

QMessageBox / QInputDialog 는 Windows 기본 모양이라 앱과 따로 논다.
쓰는 곳에서는 confirm() / prompt() / alert() 세 함수만 알면 된다.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui_qt import theme as T

SHADOW_PAD = 24          # 그림자가 잘리지 않도록 카드 둘레에 두는 여백


class BaseDialog(QDialog):
    """둥근 카드 + 그림자. 카드 아무 곳이나 끌어서 옮길 수 있다."""

    def __init__(self, parent, title: str, width: int = 400):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._drag_from: Optional[QPoint] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_PAD, SHADOW_PAD, SHADOW_PAD, SHADOW_PAD)

        self.card = QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setFixedWidth(width)
        outer.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(27, 30, 35, 60))
        self.card.setGraphicsEffect(shadow)

        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(20, 18, 20, 16)
        self.body.setSpacing(10)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        self.body.addWidget(self.title_label)

        self.setStyleSheet(T.stylesheet())

    # ------------------------------------------------------------ 버튼 줄

    def add_buttons(self, buttons: List[Tuple[str, str, object]]) -> None:
        """buttons: (라벨, 종류, 누를 때 할 일). 종류는 ghost/primary/danger."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        lay.addStretch(1)

        for label, kind, action in buttons:
            btn = QPushButton(label)
            btn.setObjectName({
                "primary": "DlgPrimary",
                "danger": "DlgDanger",
            }.get(kind, "DlgGhost"))
            btn.setFixedHeight(32)
            btn.setMinimumWidth(72)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(action)
            if kind in ("primary", "danger"):
                btn.setDefault(True)
            lay.addWidget(btn)

        self.body.addWidget(row)

    # ------------------------------------------------------------ 창 다루기

    def center_on_parent(self) -> None:
        self.adjustSize()
        anchor = self.parentWidget()
        if anchor is None:
            return
        area = anchor.frameGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.center().y() - self.height() // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event):
        self._drag_from = None


# ---------------------------------------------------------------- 확인


def confirm(parent, title: str, message: str, ok_text: str = "확인",
            cancel_text: str = "취소", danger: bool = False) -> bool:
    dialog = BaseDialog(parent, title)

    text = QLabel(message)
    text.setObjectName("DialogBody")
    text.setWordWrap(True)
    dialog.body.addWidget(text)

    dialog.add_buttons([
        (cancel_text, "ghost", dialog.reject),
        (ok_text, "danger" if danger else "primary", dialog.accept),
    ])
    dialog.center_on_parent()
    return dialog.exec() == QDialog.Accepted


def confirm_save(parent, title: str, message: str) -> str:
    """저장 / 저장 안 함 / 취소 — 셋 중 무엇을 골랐는지 문자열로."""
    dialog = BaseDialog(parent, title, 430)
    choice = {"value": "cancel"}

    text = QLabel(message)
    text.setObjectName("DialogBody")
    text.setWordWrap(True)
    dialog.body.addWidget(text)

    def pick(value):
        choice["value"] = value
        dialog.accept()

    dialog.add_buttons([
        ("취소", "ghost", dialog.reject),
        ("저장 안 함", "ghost", lambda: pick("discard")),
        ("저장", "primary", lambda: pick("save")),
    ])
    dialog.center_on_parent()
    if dialog.exec() != QDialog.Accepted:
        return "cancel"
    return choice["value"]


# ---------------------------------------------------------------- 알림


def alert(parent, title: str, message: str, ok_text: str = "확인") -> None:
    dialog = BaseDialog(parent, title)

    text = QLabel(message)
    text.setObjectName("DialogBody")
    text.setWordWrap(True)
    dialog.body.addWidget(text)

    dialog.add_buttons([(ok_text, "primary", dialog.accept)])
    dialog.center_on_parent()
    dialog.exec()


# ---------------------------------------------------------------- 입력


def prompt(parent, title: str, label: str, text: str = "",
           ok_text: str = "확인", hint: str = "", error: bool = False) -> Optional[str]:
    dialog = BaseDialog(parent, title)

    caption = QLabel(label)
    caption.setObjectName("DialogLabel")
    dialog.body.addWidget(caption)

    edit = QLineEdit(text)
    edit.setObjectName("Field")
    edit.setFixedHeight(34)
    edit.selectAll()
    dialog.body.addWidget(edit)

    if hint:
        note = QLabel(hint)
        note.setObjectName("DialogError" if error else "DialogHint")
        note.setWordWrap(True)
        dialog.body.addWidget(note)
        if error:
            edit.setProperty("invalid", True)

    edit.returnPressed.connect(dialog.accept)
    dialog.add_buttons([
        ("취소", "ghost", dialog.reject),
        (ok_text, "primary", dialog.accept),
    ])

    dialog.center_on_parent()
    edit.setFocus()

    if dialog.exec() != QDialog.Accepted:
        return None
    return edit.text().strip()
