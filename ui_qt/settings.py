# ui_qt/settings.py
"""환경 설정 창."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import hotkeys, prefs
from ui_qt import theme as T
from ui_qt.dialogs import BaseDialog
from ui_qt.fields import HotkeyField, NumberField


def _section(text: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 8, 0, 2)
    lay.setSpacing(7)

    label = QLabel(text)
    label.setObjectName("SectionLabel")
    lay.addWidget(label)

    rule = QFrame()
    rule.setFixedHeight(1)
    rule.setStyleSheet(f"background: {T.RULE_1};")
    lay.addWidget(rule, 1)
    return row


def _row(label_text: str, widget: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)

    label = QLabel(label_text)
    label.setObjectName("DialogLabel")
    lay.addWidget(label)
    lay.addWidget(widget)

    if hint:
        note = QLabel(hint)
        note.setObjectName("DialogHint")
        note.setWordWrap(True)
        lay.addWidget(note)
    return box


class SettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "환경 설정", 440)
        self.values = prefs.load()

        self.body.addWidget(_section("새 매크로 기본 설정"))

        self.body.addWidget(_row(
            "실행", HotkeyField(self.values["default_start_key"],
                              lambda v: self._set("default_start_key", v))))
        self.body.addWidget(_row(
            "종료", HotkeyField(self.values["default_stop_key"],
                              lambda v: self._set("default_stop_key", v)),
            "매크로를 새로 만들 때 시작·종료 노드에 이 키가 들어갑니다. "
            "이미 만든 매크로는 각 노드에서 따로 바꿉니다.",
        ))

        self.body.addWidget(_section("실행"))

        self.body.addWidget(_row(
            "노드 사이 간격",
            NumberField(self.values["step_delay"],
                        lambda v: self._set("step_delay", v),
                        decimals=2, minimum=0, maximum=10, suffix="초"),
            "노드를 하나 실행한 뒤 쉬는 시간 (초)",
        ))
        self.body.addWidget(_row(
            "마우스 이동 시간",
            NumberField(self.values["mouse_move_duration"],
                        lambda v: self._set("mouse_move_duration", v),
                        decimals=2, minimum=0, maximum=5, suffix="초"),
            "0 이면 좌표로 즉시 이동, 값을 올리면 부드럽게 이동합니다",
        ))

        self.add_buttons([
            ("취소", "ghost", self.reject),
            ("저장", "primary", self._save),
        ])
        self.center_on_parent()

    def _set(self, key: str, value) -> None:
        self.values[key] = value

    def _save(self) -> None:
        for key in ("default_start_key", "default_stop_key"):
            self.values[key] = hotkeys.normalize(self.values.get(key) or "")
        prefs.save(self.values)
        self.accept()


def open_settings(parent=None) -> bool:
    """설정 창을 연다. 저장했으면 True."""
    from PySide6.QtWidgets import QDialog

    return SettingsDialog(parent).exec() == QDialog.Accepted
