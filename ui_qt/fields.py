# ui_qt/fields.py
"""속성 패널의 입력 위젯과 노드 종류별 필드 정의."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator, QKeySequence

from core import hotkeys
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui_qt import theme as T

Setter = Callable[[Any], None]


# ---------------------------------------------------------------- 기본 위젯


class TextField(QLineEdit):
    def __init__(self, value: str, on_change: Setter, placeholder: str = ""):
        super().__init__(str(value or ""))
        self.setObjectName("Field")
        self.setFixedHeight(32)
        self.setPlaceholderText(placeholder)
        self.editingFinished.connect(lambda: on_change(self.text()))


class NumberField(QLineEdit):
    """숫자 입력. 비우거나 잘못 쓰면 직전 값으로 되돌린다."""

    def __init__(self, value, on_change: Setter, decimals: int = 0,
                 minimum: float = 0.0, maximum: float = 1e9, suffix: str = ""):
        self.decimals = decimals
        self.minimum = minimum
        self.maximum = maximum
        super().__init__(self._format(value))
        self.setObjectName("Field")
        self.setFixedHeight(32)
        self.setAlignment(Qt.AlignLeft)

        if decimals:
            self.setValidator(QDoubleValidator(minimum, maximum, decimals, self))
        else:
            self.setValidator(QIntValidator(int(minimum), int(maximum), self))

        if suffix:
            self.setPlaceholderText(suffix)

        self._last = self.text()
        self.editingFinished.connect(lambda: self._commit(on_change))

    def _format(self, value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        if self.decimals:
            text = f"{number:.{self.decimals}f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(int(number))

    def _commit(self, on_change: Setter) -> None:
        try:
            number = float(self.text())
        except ValueError:
            self.setText(self._last)
            return
        number = max(self.minimum, min(self.maximum, number))
        value = round(number, self.decimals) if self.decimals else int(number)
        self.setText(self._format(value))
        self._last = self.text()
        on_change(value)


class ChoiceField(QFrame):
    """두세 개짜리 선택 — 시안의 분절 버튼."""

    def __init__(self, options: List[Tuple[str, str]], value, on_change: Setter):
        super().__init__()
        self.setObjectName("Segmented")
        self.setFixedHeight(32)
        self.buttons = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)

        for key, label in options:
            btn = QPushButton(label)
            btn.setObjectName("Segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k, on_change))
            lay.addWidget(btn, 1)
            self.buttons[key] = btn

        self._select(value if value in self.buttons else options[0][0])

    def _select(self, key) -> None:
        for name, btn in self.buttons.items():
            btn.setChecked(name == key)

    def _pick(self, key, on_change: Setter) -> None:
        self._select(key)
        on_change(key)


class PointField(QWidget):
    """좌표. 앞선 조건이 찾은 좌표를 참조 중이면 그 사실을 보여준다."""

    def __init__(self, pos, on_change: Setter):
        super().__init__()
        self.pos = dict(pos) if isinstance(pos, dict) else {"x": 0, "y": 0}
        self.on_change = on_change

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        x, y = self.pos.get("x"), self.pos.get("y")
        self.is_ref = isinstance(x, dict) or isinstance(y, dict)

        if self.is_ref:
            ref = (x if isinstance(x, dict) else y).get("ref")
            chip = QFrame()
            chip.setObjectName("ValueBox")
            chip.setFixedHeight(32)
            cl = QHBoxLayout(chip)
            cl.setContentsMargins(9, 0, 9, 0)
            label = QLabel(f"{ref} 이(가) 찾은 좌표")
            label.setStyleSheet(f"font-size: 12px; color: {T.ACCENT};")
            cl.addWidget(label)
            cl.addStretch(1)
            lay.addWidget(chip)

            switch = QPushButton("직접 좌표 입력으로 바꾸기")
            switch.setObjectName("GhostBtn")
            switch.setFixedHeight(28)
            switch.setCursor(Qt.PointingHandCursor)
            switch.clicked.connect(self._to_literal)
            lay.addWidget(switch)
            return

        row = QHBoxLayout()
        row.setSpacing(6)
        self.edits = {}
        for axis in ("x", "y"):
            wrap = QFrame()
            wrap.setObjectName("ValueBox")
            wrap.setFixedHeight(32)
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(9, 0, 4, 0)
            wl.setSpacing(4)

            tag = QLabel(axis.upper())
            tag.setStyleSheet(f"font-size: 10px; color: {T.INK_4};")
            wl.addWidget(tag)

            edit = NumberField(self.pos.get(axis, 0), lambda v, a=axis: self._set(a, v),
                               minimum=-100000, maximum=100000)
            edit.setObjectName("BareField")
            self.edits[axis] = edit
            wl.addWidget(edit, 1)
            row.addWidget(wrap, 1)
        lay.addLayout(row)

        capture = QPushButton("화면에서 좌표 집기")
        capture.setObjectName("GhostBtn")
        capture.setFixedHeight(30)
        capture.setCursor(Qt.PointingHandCursor)
        capture.clicked.connect(self._capture)
        lay.addWidget(capture)

    def _set(self, axis: str, value) -> None:
        self.pos[axis] = int(value)
        self.on_change(dict(self.pos))

    def _capture(self) -> None:
        from ui_qt.picker import pick_from_screen

        picked = pick_from_screen(self.window())
        if picked is None:
            return
        self.pos = {"x": picked.x, "y": picked.y}
        for axis in ("x", "y"):
            edit = self.edits[axis]
            edit.setText(edit._format(self.pos[axis]))
            edit._last = edit.text()
        self.on_change(dict(self.pos))

    def _to_literal(self) -> None:
        self.on_change({"x": 0, "y": 0})


class HotkeyField(QWidget):
    """키를 눌러 단축키를 정한다."""

    def __init__(self, value, on_change: Setter):
        super().__init__()
        self.on_change = on_change
        self.value = hotkeys.normalize(value or "")
        self.listening = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.box = QFrame()
        self.box.setObjectName("ValueBox")
        self.box.setFixedHeight(32)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(9, 0, 9, 0)

        self.label = QLabel()
        bl.addWidget(self.label)
        bl.addStretch(1)
        lay.addWidget(self.box, 1)

        self.button = QPushButton("변경")
        self.button.setObjectName("GhostBtn")
        self.button.setFixedHeight(32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._toggle)
        lay.addWidget(self.button)

        self.clear_btn = QPushButton("해제")
        self.clear_btn.setObjectName("GhostBtn")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear)
        lay.addWidget(self.clear_btn)

        self._refresh()

    def _refresh(self) -> None:
        if self.listening:
            self.label.setText("키를 누르세요…")
            self.label.setStyleSheet(f"font-size: 12px; color: {T.ACCENT};")
            self.box.setProperty("listening", True)
        else:
            self.label.setText(hotkeys.display(self.value))
            self.label.setStyleSheet(
                f"font-family: '{T.mono_stack()}'; font-size: 12px;")
            self.box.setProperty("listening", False)
        self.button.setText("취소" if self.listening else "변경")
        self.box.style().unpolish(self.box)
        self.box.style().polish(self.box)

    def _toggle(self) -> None:
        self.listening = not self.listening
        if self.listening:
            self.setFocus(Qt.OtherFocusReason)
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
        self._refresh()

    def _clear(self) -> None:
        if self.listening:
            self._toggle()
        self.value = ""
        self._refresh()
        self.on_change("")

    def keyPressEvent(self, event):
        if not self.listening:
            return super().keyPressEvent(event)

        key = event.key()
        if key == Qt.Key_Escape:
            self._toggle()
            return
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            return          # 수정키만으론 확정하지 않는다

        combo = QKeySequence(event.keyCombination()).toString()
        normalized = hotkeys.normalize(combo)
        if not normalized or hotkeys.is_bare_modifier(normalized):
            return

        self.value = normalized
        self.listening = False
        self.releaseKeyboard()
        self._refresh()
        self.on_change(self.value)


class ColorField(QWidget):
    def __init__(self, color, on_change: Setter):
        super().__init__()
        self.on_change = on_change
        self.color = list(color) if isinstance(color, (list, tuple)) and len(color) == 3 \
            else [255, 255, 255]

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.box = QFrame()
        self.box.setObjectName("ValueBox")
        self.box.setFixedHeight(32)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(9, 0, 9, 0)
        bl.setSpacing(8)

        self.chip = QFrame()
        self.chip.setFixedSize(14, 14)
        bl.addWidget(self.chip)

        self.text = QLabel()
        self.text.setStyleSheet(f"font-family: '{T.mono_stack()}'; font-size: 12px;")
        bl.addWidget(self.text)
        bl.addStretch(1)
        lay.addWidget(self.box, 1)

        screen = QPushButton("화면에서")
        screen.setObjectName("GhostBtn")
        screen.setFixedHeight(32)
        screen.setCursor(Qt.PointingHandCursor)
        screen.setToolTip("화면에서 색을 집습니다")
        screen.clicked.connect(self._from_screen)
        lay.addWidget(screen)

        pick = QPushButton("고르기")
        pick.setObjectName("GhostBtn")
        pick.setFixedHeight(32)
        pick.setCursor(Qt.PointingHandCursor)
        pick.clicked.connect(self._pick)
        lay.addWidget(pick)

        self._refresh()

    def _from_screen(self) -> None:
        from ui_qt.picker import pick_from_screen

        picked = pick_from_screen(self.window())
        if picked is None:
            return
        self.color = list(picked.rgb)
        self._refresh()
        self.on_change(list(self.color))

    def _refresh(self) -> None:
        r, g, b = self.color
        self.chip.setStyleSheet(
            f"background: rgb({r},{g},{b});"
            "border: 1px solid rgba(27,30,35,0.15); border-radius: 3px;"
        )
        self.text.setText(f"{r}, {g}, {b}")

    def _pick(self) -> None:
        from PySide6.QtGui import QColor

        chosen = QColorDialog.getColor(QColor(*self.color), self, "색상 고르기")
        if chosen.isValid():
            self.color = [chosen.red(), chosen.green(), chosen.blue()]
            self._refresh()
            self.on_change(list(self.color))


class FileField(QWidget):
    def __init__(self, path: str, on_change: Setter):
        super().__init__()
        self.on_change = on_change

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.edit = TextField(path, on_change, "이미지 파일 경로")
        lay.addWidget(self.edit, 1)

        browse = QPushButton("찾기")
        browse.setObjectName("GhostBtn")
        browse.setFixedHeight(32)
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "템플릿 이미지 고르기", "", "이미지 (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.edit.setText(path)
            self.on_change(path)


# ---------------------------------------------------------------- 노드별 필드

BUTTONS = [("left", "좌클릭"), ("right", "우클릭")]

# (파라미터 키, 라벨, 종류, 옵션, 도움말)
Spec = Tuple[str, str, str, Dict[str, Any], str]

FIELDS: Dict[str, List[Spec]] = {
    # 시작 노드는 이 매크로의 실행 설정을 함께 담는다
    "start": [
        ("hotkey", "실행 단축키", "hotkey", {},
         "이 폴더를 보고 있을 때 이 키로 매크로를 실행합니다"),
        ("step_delay", "노드 사이 간격", "number",
         {"decimals": 2, "minimum": 0, "maximum": 10, "suffix": "초"},
         "노드를 하나 실행한 뒤 쉬는 시간"),
        ("mouse_move_duration", "마우스 이동 시간", "number",
         {"decimals": 2, "minimum": 0, "maximum": 5, "suffix": "초"},
         "0 이면 좌표로 즉시 이동, 값을 올리면 부드럽게 이동합니다"),
    ],
    "stop": [
        ("hotkey", "종료 단축키", "hotkey", {},
         "실행 중인 이 매크로를 이 키로 멈춥니다"),
    ],
    "mouse_click": [
        ("button", "버튼", "choice", {"options": BUTTONS}, ""),
        ("pos", "좌표", "point", {}, ""),
    ],
    "mouse_move": [
        ("pos", "좌표", "point", {}, ""),
    ],
    "mouse_down": [("button", "버튼", "choice", {"options": BUTTONS}, "")],
    "mouse_up": [("button", "버튼", "choice", {"options": BUTTONS}, "")],

    "key_press": [("key", "키", "text", {"placeholder": "예: enter, esc, a"}, "")],
    "key_down": [("key", "키", "text", {"placeholder": "예: shift, ctrl"}, "")],
    "key_up": [("key", "키", "text", {"placeholder": "예: shift, ctrl"}, "")],

    "delay": [
        ("seconds", "대기 시간", "number",
         {"decimals": 2, "minimum": 0, "maximum": 3600, "suffix": "초"}, "초 단위"),
    ],
    "loop": [
        ("max", "최대 반복", "number", {"minimum": 0, "maximum": 1000000},
         "0 이면 중지할 때까지 반복합니다"),
    ],
    "rgb_match": [
        ("pos", "좌표", "point", {}, ""),
        ("color", "색상", "color", {}, ""),
        ("tolerance", "허용 오차", "number", {"minimum": 0, "maximum": 255},
         "0 이면 색이 정확히 같아야 합니다"),
    ],
    "image_match": [
        ("template", "템플릿 이미지", "file", {}, ""),
        ("threshold", "일치율", "number",
         {"decimals": 2, "minimum": 0.1, "maximum": 1.0}, "1 에 가까울수록 엄격합니다"),
    ],
}

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "start": {"hotkey": "", "step_delay": 0.03, "mouse_move_duration": 0.0},
    "stop": {"hotkey": ""},
    "mouse_click": {"button": "left", "pos": {"x": 0, "y": 0}},
    "mouse_move": {"pos": {"x": 0, "y": 0}},
    "mouse_down": {"button": "left"},
    "mouse_up": {"button": "left"},
    "key_press": {"key": "enter"},
    "key_down": {"key": "shift"},
    "key_up": {"key": "shift"},
    "delay": {"seconds": 0.5},
    "loop": {"max": 10},
    "rgb_match": {"pos": {"x": 0, "y": 0}, "color": [255, 255, 255], "tolerance": 0},
    "image_match": {"template": "", "threshold": 0.9},
}


def build_widget(kind: str, value, options: Dict[str, Any], on_change: Setter) -> QWidget:
    if kind == "text":
        return TextField(value, on_change, options.get("placeholder", ""))
    if kind == "number":
        return NumberField(
            value, on_change,
            decimals=options.get("decimals", 0),
            minimum=options.get("minimum", 0),
            maximum=options.get("maximum", 1e9),
            suffix=options.get("suffix", ""),
        )
    if kind == "choice":
        return ChoiceField(options["options"], value, on_change)
    if kind == "point":
        return PointField(value, on_change)
    if kind == "color":
        return ColorField(value, on_change)
    if kind == "file":
        return FileField(str(value or ""), on_change)
    if kind == "hotkey":
        return HotkeyField(value, on_change)
    return TextField(value, on_change)
