# ui_qt/fields.py
"""속성 패널의 입력 위젯과 노드 종류별 필드 정의."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QDoubleValidator,
    QGuiApplication,
    QIntValidator,
    QKeySequence,
    QPixmap,
)

from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import hotkeys
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


class UnitField(QWidget):
    """숫자 칸 옆에 단위를 붙인다.

    NumberField 의 suffix 는 placeholder 로만 쓰여 값이 있으면 사라졌다.
    "0.03" 만 놓여 있으면 초인지 밀리초인지 알 수 없다.
    """

    def __init__(self, value, on_change: Setter, unit: str, **number_kwargs):
        super().__init__()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.edit = NumberField(value, on_change, **number_kwargs)
        lay.addWidget(self.edit, 1)

        tag = QLabel(unit)
        tag.setStyleSheet(f"font-size: 12px; color: {T.INK_4};")
        lay.addWidget(tag)


class PercentField(QWidget):
    """0~1 로 담기는 값을 백분율로 보여준다. 0.9 보다 90% 가 읽기 쉽다."""

    def __init__(self, value, on_change: Setter,
                 minimum: int = 0, maximum: int = 100):
        super().__init__()
        self.on_change = on_change

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        try:
            percent = round(float(value) * 100)
        except (TypeError, ValueError):
            percent = maximum

        self.edit = NumberField(percent, self._commit,
                                minimum=minimum, maximum=maximum)
        lay.addWidget(self.edit, 1)

        tag = QLabel("%")
        tag.setStyleSheet(f"font-size: 12px; color: {T.INK_4};")
        lay.addWidget(tag)

    def _commit(self, percent) -> None:
        self.on_change(round(int(percent) / 100, 2))


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
    """좌표. 직접 적거나, 앞선 조건 노드가 찾아낸 자리를 가리킬 수 있다.

    "이미지를 찾아서 그 자리를 클릭" 은 매크로에서 가장 흔한 짜임인데,
    찾은 자리는 실행해봐야 알 수 있어 숫자로 적어둘 수가 없다. 그래서 값
    대신 "그 노드가 찾은 곳" 이라고 적어둔다.
    """

    def __init__(self, pos, on_change: Setter, sources=None):
        super().__init__()
        self.pos = dict(pos) if isinstance(pos, dict) else {"x": 0, "y": 0}
        self.on_change = on_change
        #: [(노드 id, 보여줄 이름)] — 좌표를 남기는 앞선 노드들
        self.sources = list(sources or [])

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
            label = QLabel(f"{self._name_of(ref)} 이(가) 찾은 좌표")
            label.setWordWrap(True)
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

        if self.sources:
            follow = QPushButton("찾은 좌표 따라가기")
            follow.setObjectName("GhostBtn")
            follow.setFixedHeight(30)
            follow.setCursor(Qt.PointingHandCursor)
            follow.clicked.connect(lambda: self._pick_source(follow))
            lay.addWidget(follow)

    def _name_of(self, node_id: str) -> str:
        for nid, name in self.sources:
            if nid == node_id:
                return name
        return node_id or "?"

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

    def _pick_source(self, anchor: QWidget) -> None:
        menu = QMenu(self)
        for nid, name in self.sources:
            menu.addAction(name, lambda i=nid: self._to_ref(i))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _to_ref(self, node_id: str) -> None:
        self.on_change({"x": {"ref": node_id}, "y": {"ref": node_id}})

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


class KeyField(QWidget):
    """칸을 눌러 고른 뒤 키를 누르면 그 키가 잡힌다.

    이름을 외워 치게 하면 "엔터" 처럼 틀리게 적어도 저장되고, 실행할 때가
    되어서야 아무 일도 일어나지 않는다. 직접 눌러 잡게 하고, 매크로가 보낼
    수 없는 키면 그 자리에서 알린다.

    확정 버튼을 거치지 않으므로 Esc 도 그냥 잡힌다. 그만두려면 다른 곳을
    누르면 된다.

    조합키는 담지 않는다 — 누르고 있기 · 떼기 노드로 만들면 된다. 그래서
    Ctrl+C 를 누르면 C 만 잡힌다.
    """

    #: 이 키들은 혼자 눌러도 값이 된다 (Shift 를 누르고 있는 매크로 등)
    MODIFIERS = {
        Qt.Key_Control: "ctrl", Qt.Key_Alt: "alt",
        Qt.Key_Shift: "shift", Qt.Key_Meta: "win",
    }

    IDLE_NOTE = "칸을 누른 다음 원하는 키를 누르세요"
    ARMED_NOTE = "지금 누르는 키가 잡힙니다"

    def __init__(self, value, on_change: Setter):
        super().__init__()
        self.on_change = on_change
        self.value = hotkeys.single_key(value or "")
        self.armed = False
        # 클릭으로만 고른다. Tab 차례에 끼면 노드를 고르자마자 저절로
        # 골라져서, 누르는 키가 죄다 여기로 빨려 들어간다.
        self.setFocusPolicy(Qt.ClickFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        self.box = QFrame()
        self.box.setObjectName("ValueBox")
        self.box.setFixedHeight(32)
        self.box.setCursor(Qt.PointingHandCursor)
        self.box.installEventFilter(self)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(9, 0, 9, 0)
        self.label = QLabel()
        bl.addWidget(self.label)
        bl.addStretch(1)
        root.addWidget(self.box)

        self.note = QLabel()
        self.note.setWordWrap(True)
        root.addWidget(self.note)

        self._say(self.IDLE_NOTE)
        self._refresh()

    # ------------------------------------------------------------ 화면

    def _refresh(self) -> None:
        self.label.setText(hotkeys.display_key(self.value))
        self.label.setStyleSheet(
            f"font-family: '{T.mono_stack()}'; font-size: 12px;"
            + (f" color: {T.ACCENT};" if self.armed else ""))
        self.box.setProperty("listening", self.armed)
        self.box.style().unpolish(self.box)
        self.box.style().polish(self.box)

    def _say(self, text: str, bad: bool = False) -> None:
        self.note.setText(text)
        self.note.setStyleSheet(
            f"font-size: 11px; color: {T.DANGER if bad else T.INK_4};")

    # ------------------------------------------------------------ 잡기

    def eventFilter(self, obj, event):
        if obj is self.box and event.type() == QEvent.MouseButtonPress:
            self.setFocus(Qt.MouseFocusReason)
        return super().eventFilter(obj, event)

    def focusInEvent(self, event):
        self._arm(True)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._arm(False)
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self._arm(False)
        super().hideEvent(event)

    def _arm(self, on: bool) -> None:
        if on == self.armed:
            return
        self.armed = on
        self._say(self.ARMED_NOTE if on else self.IDLE_NOTE)
        self._refresh()

    def event(self, event):
        """잡는 동안에는 Tab 이나 편집기 단축키에 키를 빼앗기지 않는다.

        Tab 은 Qt 가 포커스 이동으로 먼저 가져가고, 편집기의 한 글자 단축키
        (F = 전체 보기)도 keyPressEvent 보다 앞서 돈다. 둘 다 여기서 막는다.
        """
        if self.armed:
            if event.type() == QEvent.ShortcutOverride:
                event.accept()
                return True
            if event.type() == QEvent.KeyPress:
                self.keyPressEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        if not self.armed:
            return super().keyPressEvent(event)

        code = event.key()
        if code in self.MODIFIERS:
            key = self.MODIFIERS[code]
        else:
            # 수정키는 떼고 바탕이 되는 키만 본다 — 조합키는 담지 않는다
            key = hotkeys.single_key(QKeySequence(code).toString())
        if not key:
            return

        if not hotkeys.is_sendable(key):
            self._say(f"‘{hotkeys.display_key(key)}’ 는 보낼 수 없는 키입니다.", bad=True)
            return

        self.value = key
        self._refresh()
        if code not in self.MODIFIERS and event.modifiers() & (
                Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier | Qt.MetaModifier):
            self._say("조합키는 담기지 않습니다 — 누르고 있기 · 떼기 노드로 만드세요.")
        else:
            self._say(self.ARMED_NOTE)
        self.on_change(self.value)


class ToleranceField(QWidget):
    """허용 오차. 그 폭이 실제로 어느 정도인지 색으로 보여준다.

    "12" 가 눈에 띄는 차이인지 아닌지는 숫자만 봐서는 알 수 없다. 기준 색을
    좌우로 그만큼 흔든 견본을 늘어놓으면 한눈에 가늠된다.
    """

    SWATCHES = 5
    SWATCH_H = 22

    def __init__(self, value, on_change: Setter, base=None,
                 minimum: int = 0, maximum: int = 255):
        super().__init__()
        self.on_change = on_change
        self.base = list(base) if isinstance(base, (list, tuple)) and len(base) == 3             else [255, 255, 255]
        try:
            self.value = int(value)
        except (TypeError, ValueError):
            self.value = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.edit = NumberField(self.value, self._changed,
                                minimum=minimum, maximum=maximum)
        root.addWidget(self.edit)

        self.strip = QWidget()
        self.strip.setFixedHeight(self.SWATCH_H)
        strip_lay = QHBoxLayout(self.strip)
        strip_lay.setContentsMargins(0, 0, 0, 0)
        strip_lay.setSpacing(2)
        self.cells = []
        for _ in range(self.SWATCHES):
            cell = QFrame()
            cell.setFixedHeight(self.SWATCH_H)
            strip_lay.addWidget(cell, 1)
            self.cells.append(cell)
        root.addWidget(self.strip)

        self._refresh()

    def set_base(self, rgb) -> None:
        """기준 색이 바뀌면 견본도 따라간다."""
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            self.base = list(rgb)
            self._refresh()

    def _changed(self, value) -> None:
        self.value = int(value)
        self._refresh()
        self.on_change(self.value)

    def _refresh(self) -> None:
        span = self.value
        middle = (self.SWATCHES - 1) / 2
        for i, cell in enumerate(self.cells):
            shift = round((i - middle) / middle * span) if middle else 0
            rgb = tuple(max(0, min(255, c + shift)) for c in self.base)
            # 가운데 칸이 기준 색 — 테두리를 조금 더 진하게
            edge = "rgba(27,30,35,0.35)" if i == middle else "rgba(27,30,35,0.12)"
            cell.setStyleSheet(
                f"background: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                f"border: 1px solid {edge}; border-radius: 3px;")
            cell.setToolTip(f"{rgb[0]}, {rgb[1]}, {rgb[2]}")


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


class ImageField(QWidget):
    """템플릿 이미지. 미리보기 · 파일 이름 · 없는 파일 경고를 함께 보여준다.

    경로 글자만 있으면 어떤 그림인지 알 수 없고, 파일을 옮기거나 지워도
    실행할 때가 되어서야 조용히 "못 찾음" 이 된다. 여기서 미리 알린다.
    """

    #: 미리보기 칸 높이. 찾을 대상은 대개 작은 버튼이라 원본보다 키우지는
    #: 않고, 칸만 넉넉히 잡아 가운데에 둔다.
    PREVIEW_H = 132

    def __init__(self, path: str, on_change: Setter):
        super().__init__()
        self.on_change = on_change
        self.path = str(path or "")
        self._shot = None          # 줄이기 전 원본

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        card = QFrame()
        card.setObjectName("ValueBox")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.setSpacing(8)

        self.thumb = QLabel()
        self.thumb.setMinimumHeight(self.PREVIEW_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.thumb)

        self.name = QLabel()
        self.name.setWordWrap(True)
        self.name.setAlignment(Qt.AlignCenter)
        self.name.setStyleSheet("font-size: 12px; font-weight: 500;")
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignCenter)
        self.detail.setStyleSheet(f"font-size: 11px; color: {T.INK_4};")
        cl.addWidget(self.name)
        cl.addWidget(self.detail)
        root.addWidget(card)
        self.card = card

        row = QHBoxLayout()
        row.setSpacing(6)
        for label, slot in (("파일 고르기", self._browse),
                            ("클립보드 이미지", self._paste)):
            btn = QPushButton(label)
            btn.setObjectName("GhostBtn")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            row.addWidget(btn, 1)
        root.addLayout(row)

        self._refresh()

    # ------------------------------------------------------------ 화면

    def _refresh(self) -> None:
        from pathlib import Path

        self._shot = None
        if not self.path:
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("이미지 없음")
            self.thumb.setStyleSheet(f"font-size: 11px; color: {T.INK_4};")
            self.name.setText("이미지를 고르세요")
            self._detail("파일을 고르거나 클립보드에서 붙여넣습니다")
            self.card.setToolTip("")
            return

        file = Path(self.path)
        self.name.setText(file.name)
        self.card.setToolTip(self.path)      # 전체 경로는 여기서 본다

        shot = QPixmap(self.path)
        if shot.isNull():
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("찾을 수 없음")
            self.thumb.setStyleSheet(f"font-size: 12px; color: {T.DANGER};")
            self._detail("파일을 찾을 수 없습니다" if not file.exists()
                         else "이미지로 읽을 수 없는 파일입니다", bad=True)
            return

        self.thumb.setStyleSheet("")
        self._shot = shot
        self._draw_preview()
        self._detail(f"{shot.width()} × {shot.height()}")

    def _draw_preview(self) -> None:
        """칸보다 큰 그림만 줄인다. 작은 그림을 늘리면 뭉개져 알아보기 어렵다."""
        if self._shot is None:
            return
        box_w = max(self.thumb.width(), 120)
        shot = self._shot
        if shot.width() > box_w or shot.height() > self.PREVIEW_H:
            shot = shot.scaled(box_w, self.PREVIEW_H,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb.setPixmap(shot)

    def resizeEvent(self, event):
        # 좁은 창에서는 속성 패널이 줄어든다 — 미리보기도 따라 줄인다
        super().resizeEvent(event)
        self._draw_preview()

    def _detail(self, text: str, bad: bool = False) -> None:
        self.detail.setText(text)
        self.detail.setStyleSheet(
            f"font-size: 11px; color: {T.DANGER if bad else T.INK_4};")

    def _set(self, path: str) -> None:
        self.path = path
        self._refresh()
        self.on_change(path)

    # ------------------------------------------------------------ 고르기

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "템플릿 이미지 고르기", "",
            "이미지 (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self._set(path)

    def _paste(self) -> None:
        """클립보드 이미지를 라이브러리에 저장하고 그것을 가리킨다."""
        from core import library

        shot = QGuiApplication.clipboard().image()
        if shot.isNull():
            self._detail("클립보드에 이미지가 없습니다", bad=True)
            return
        try:
            saved = library.save_image(QPixmap.fromImage(shot))
        except OSError as exc:
            self._detail(str(exc), bad=True)
            return
        self._set(str(saved))


class RegionField(QWidget):
    """화면에서 찾아볼 범위. 정하지 않으면 화면 전체를 뒤진다.

    범위를 좁히면 그만큼 빨라진다 — 반복 안에서 이미지를 찾을 때 차이가 크다.
    """

    def __init__(self, region, on_change: Setter):
        super().__init__()
        self.on_change = on_change
        self.region = list(region) if isinstance(region, (list, tuple))             and len(region) == 4 else None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.box = QFrame()
        self.box.setObjectName("ValueBox")
        self.box.setFixedHeight(32)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(9, 0, 9, 0)
        self.label = QLabel()
        bl.addWidget(self.label)
        bl.addStretch(1)
        root.addWidget(self.box)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.pick_btn = QPushButton("영역 지정")
        self.clear_btn = QPushButton("화면 전체로")
        for btn, slot in ((self.pick_btn, self._pick), (self.clear_btn, self._clear)):
            btn.setObjectName("GhostBtn")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            row.addWidget(btn, 1)
        root.addLayout(row)

        self._refresh()

    def _refresh(self) -> None:
        if self.region is None:
            self.label.setText("화면 전체")
            self.label.setStyleSheet(f"font-size: 12px; color: {T.INK_4};")
        else:
            x1, y1, x2, y2 = self.region
            self.label.setText(f"{x1}, {y1}  ·  {x2 - x1} × {y2 - y1}")
            self.label.setStyleSheet(
                f"font-family: '{T.mono_stack()}'; font-size: 12px;")
        self.clear_btn.setEnabled(self.region is not None)

    def _pick(self) -> None:
        from ui_qt.picker import pick_region

        picked = pick_region(self.window())
        if picked is None:
            return
        self.region = list(picked)
        self._refresh()
        self.on_change(list(self.region))

    def _clear(self) -> None:
        self.region = None
        self._refresh()
        self.on_change(None)


# ---------------------------------------------------------------- 노드별 필드

BUTTONS = [("left", "좌클릭"), ("right", "우클릭"), ("middle", "휠클릭")]

# (파라미터 키, 라벨, 종류, 옵션, 도움말)
Spec = Tuple[str, str, str, Dict[str, Any], str]

FIELDS: Dict[str, List[Spec]] = {
    # 시작 노드는 이 매크로의 실행 설정을 함께 담는다
    "start": [
        ("hotkey", "실행 단축키", "hotkey", {},
         "이 폴더를 보고 있을 때 이 키로 매크로를 실행합니다"),
        ("step_delay", "노드 사이 간격", "unit",
         {"decimals": 2, "minimum": 0, "maximum": 10, "unit": "초"},
         "노드를 하나 실행한 뒤 쉬는 시간"),
        ("mouse_move_duration", "마우스 이동 시간", "unit",
         {"decimals": 2, "minimum": 0, "maximum": 5, "unit": "초"},
         "0 초면 좌표로 곧바로 옮깁니다. 0.3 초쯤 주면 사람이 옮긴 것처럼 보입니다."),
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

    "key_press": [("key", "보낼 키", "key", {}, "")],
    "key_down": [("key", "누르고 있을 키", "key", {}, "")],
    "key_up": [("key", "뗄 키", "key", {}, "")],

    "delay": [
        ("seconds", "대기 시간", "unit",
         {"decimals": 2, "minimum": 0, "maximum": 3600, "unit": "초"}, ""),
    ],
    "loop": [
        ("max", "반복 횟수", "number", {"minimum": 0, "maximum": 1000000},
         "몸통을 이만큼 되풀이한 뒤 완료로 나갑니다. 0 이면 중지할 때까지."),
    ],
    "rgb_match": [
        ("pos", "좌표", "point", {}, ""),
        ("color", "색상", "color", {}, ""),
        ("tolerance", "허용 오차", "tolerance", {"minimum": 0, "maximum": 255},
         "아래 견본 범위 안이면 같은 색으로 봅니다"),
    ],
    "image_match": [
        ("template", "템플릿 이미지", "image", {}, ""),
        ("region", "찾아볼 범위", "region", {},
         "좁힐수록 빨라집니다. 반복 안에서 찾을 때 차이가 큽니다."),
        ("threshold", "일치율", "percent",
         {"minimum": 10, "maximum": 100},
         "낮추면 조금 달라도 찾고, 높이면 거의 같아야 찾습니다"),
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
    "image_match": {"template": "", "region": None, "threshold": 0.9},
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
        return PointField(value, on_change, options.get("sources"))
    if kind == "color":
        return ColorField(value, on_change)
    if kind == "image":
        return ImageField(str(value or ""), on_change)
    if kind == "region":
        return RegionField(value, on_change)
    if kind == "unit":
        return UnitField(
            value, on_change, options.get("unit", ""),
            decimals=options.get("decimals", 0),
            minimum=options.get("minimum", 0),
            maximum=options.get("maximum", 1e9),
        )
    if kind == "tolerance":
        return ToleranceField(
            value, on_change, base=options.get("base"),
            minimum=options.get("minimum", 0),
            maximum=options.get("maximum", 255),
        )
    if kind == "percent":
        return PercentField(
            value, on_change,
            minimum=options.get("minimum", 0),
            maximum=options.get("maximum", 100),
        )
    if kind == "hotkey":
        return HotkeyField(value, on_change)
    if kind == "key":
        return KeyField(value, on_change)
    return TextField(value, on_change)
