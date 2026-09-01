# ui_qt/editor_panels.py
"""편집기의 좌우 패널 — 노드 팔레트와 속성 패널.

팔레트 항목은 눌러서 더하거나 캔버스로 끌어다 놓는다. 속성 패널은 고른
노드의 값을 보여주고 고친다.
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PySide6.QtCore import QEvent, QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.graph import Graph, Node
from ui_qt import theme as T
from ui_qt.fields import DEFAULTS, FIELDS, build_widget
from ui_qt.node_view import CATEGORY, LABEL, SKIN

PALETTE_W = 220
INSPECTOR_W = 296

# 창이 좁을 때 쓰는 폭 — 캔버스가 너무 눌리지 않게 양옆을 먼저 줄인다
PALETTE_W_NARROW = 176
INSPECTOR_W_NARROW = 236
BP_NARROW_PANELS = 1040

# 칩 배경 — node_view.SKIN 의 테두리/강조와 짝이 되는 연한 색
CHIP_BG = {
    "input": "#EDF1FB",
    "wait": "#F1F2F5",
    "condition": "#FBF3E3",
    "loop": "#F1ECFA",
    "flow": "#F7E7E6",
}


def _hex(rgb: Tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def accent_of(node_type: str) -> str:
    return _hex(SKIN[CATEGORY.get(node_type, "wait")]["accent"])


def chip_bg_of(node_type: str) -> str:
    return CHIP_BG[CATEGORY.get(node_type, "wait")]


def icon_chip(node_type: str, ratio: float, box: int = 22, glyph: int = 13,
              radius: int = 6) -> QFrame:
    holder = QFrame()
    holder.setFixedSize(box, box)
    holder.setStyleSheet(f"background: {chip_bg_of(node_type)}; border-radius: {radius}px;")

    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)

    label = QLabel()
    label.setPixmap(T.icon_pixmap(node_type, glyph, accent_of(node_type), 1.4, ratio))
    label.setFixedSize(glyph, glyph)
    lay.addWidget(label, 0, Qt.AlignCenter)
    return holder


def section_label(text: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(4, 10, 4, 5)
    lay.setSpacing(6)

    label = QLabel(text)
    label.setObjectName("SectionLabel")
    lay.addWidget(label)

    rule = QFrame()
    rule.setFixedHeight(1)
    rule.setStyleSheet(f"background: {T.RULE_1};")
    lay.addWidget(rule, 1)
    return row


# ---------------------------------------------------------------- 팔레트

# 시작·종료는 매크로를 만들 때부터 있고 지울 수도 없으므로 팔레트에 두지 않는다.
PALETTE_GROUPS: List[Tuple[str, List[str]]] = [
    ("입력", ["mouse_click", "mouse_move", "mouse_down", "mouse_up",
              "key_press", "key_down", "key_up"]),
    ("대기", ["delay"]),
    ("조건", ["rgb_match", "image_match"]),
    ("반복", ["loop"]),
]


#: 팔레트에서 캔버스로 끌 때 실어 보내는 표시. 뷰어가 text/plain 을 받아준다.
DRAG_PREFIX = "clikey/node:"

CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅ"            "ㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def choseong(text: str) -> str:
    """한글에서 첫 자음만 뽑는다. 한글이 아닌 글자는 그대로 둔다."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        out.append(CHOSEONG[code // 588] if 0 <= code <= 11171 else ch)
    return "".join(out)


def matches(node_type: str, needle: str) -> bool:
    """이름·초성·영문 타입 중 어느 것으로도 찾을 수 있게 한다.

    한글 이름을 치려면 IME 를 오가야 하니 "delay" 같은 타입 이름도 받고,
    "ㅁㅇ" 처럼 초성만 쳐도 "마우스 이동" 이 걸리게 한다.
    """
    if not needle:
        return True
    needle = needle.replace(" ", "")
    label = LABEL.get(node_type, node_type)
    for hay in (label.lower(), node_type.lower(), choseong(label)):
        if needle in hay.replace(" ", ""):
            return True
    return False


class PaletteItem(QFrame):
    def __init__(self, node_type: str, ratio: float, on_add=None):
        super().__init__()
        self.node_type = node_type
        self.on_add = on_add
        self._press_at = None
        self.setObjectName("PaletteItem")
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            f"{LABEL.get(node_type, node_type)} — 눌러서 추가하거나 캔버스로 끌어다 놓기")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(8)
        lay.addWidget(icon_chip(node_type, ratio, 20, 12, 5))

        label = QLabel(LABEL.get(node_type, node_type))
        label.setStyleSheet("font-size: 12px;")
        lay.addWidget(label)
        lay.addStretch(1)

        plus = QLabel()
        plus.setPixmap(T.icon_pixmap("plus", 11, T.INK_4, 1.6, ratio))
        plus.setFixedSize(11, 11)
        lay.addWidget(plus)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_at = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """조금이라도 끌면 드래그로 넘긴다 — 클릭 추가와 자연스럽게 갈린다."""
        if self._press_at is None or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if (event.pos() - self._press_at).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        self._press_at = None
        self._start_drag()

    def mouseReleaseEvent(self, event):
        was_pressed, self._press_at = self._press_at, None
        if (was_pressed is not None and event.button() == Qt.LeftButton
                and self.rect().contains(event.pos()) and self.on_add):
            self.on_add(self.node_type)
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        mime = QMimeData()
        mime.setText(DRAG_PREFIX + self.node_type)

        drag = QDrag(self)
        drag.setMimeData(mime)
        # 끌고 다니는 동안 실제 항목 모습을 그대로 보여준다
        preview = self.grab()
        drag.setPixmap(preview)
        drag.setHotSpot(preview.rect().center() / preview.devicePixelRatio())
        drag.exec(Qt.CopyAction)


class SearchBox(QWidget):
    """돋보기를 겹쳐 놓은 검색칸. 패널 폭이 바뀌면 따라 늘었다 줄었다 한다."""

    def __init__(self, ratio: float, placeholder: str):
        super().__init__()
        self.setFixedHeight(30)
        self.edit = QLineEdit(self)
        self.edit.setObjectName("Search")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.glass = QLabel(self)
        self.glass.setPixmap(T.icon_pixmap("search", 13, T.INK_4, 1.5, ratio))

    def resizeEvent(self, event):
        self.edit.setGeometry(0, 0, self.width(), self.height())
        self.glass.setGeometry(9, (self.height() - 13) // 2, 13, 13)
        super().resizeEvent(event)


class Palette(QWidget):
    def __init__(self, ratio: float, on_add=None):
        super().__init__()
        self.on_add = on_add
        self.setObjectName("Panel")
        self.setFixedWidth(PALETTE_W)

        #: [(구역 제목, [그 아래 항목])] — 검색할 때 함께 숨긴다
        self._sections: List[Tuple[QWidget, List[PaletteItem]]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        search_wrap = QWidget()
        sw = QHBoxLayout(search_wrap)
        sw.setContentsMargins(10, 10, 10, 10)
        box = SearchBox(ratio, "노드 검색")
        self.search = box.edit
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._add_first)
        self.search.installEventFilter(self)
        sw.addWidget(box)
        root.addWidget(search_wrap)

        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {T.RULE_1};")
        root.addWidget(rule)

        body = QWidget()
        bodylay = QVBoxLayout(body)
        bodylay.setContentsMargins(8, 0, 8, 8)
        bodylay.setSpacing(1)

        for title, types in PALETTE_GROUPS:
            head = section_label(title)
            bodylay.addWidget(head)
            items = []
            for node_type in types:
                item = PaletteItem(node_type, ratio, on_add=self.on_add)
                bodylay.addWidget(item)
                items.append(item)
            self._sections.append((head, items))

        self.empty = QLabel("맞는 노드가 없습니다")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"font-size: 12px; color: {T.INK_4}; padding: 28px 0;")
        self.empty.hide()
        bodylay.addWidget(self.empty)

        bodylay.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(body)
        root.addWidget(area, 1)

    def set_narrow(self, narrow: bool) -> None:
        self.setFixedWidth(PALETTE_W_NARROW if narrow else PALETTE_W)

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def eventFilter(self, obj, event):
        """검색 중 Esc 는 창을 닫지 말고 검색어만 비운다."""
        if (obj is self.search and event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape and self.search.text()):
            self.search.clear()
            return True
        return super().eventFilter(obj, event)

    def visible_types(self) -> List[str]:
        return [item.node_type
                for _, items in self._sections for item in items
                if not item.isHidden()]

    def _filter(self, text: str = "") -> None:
        # 항목이 열 몇 개뿐이라 보이고 숨기는 것으로 충분하다. 홈 목록처럼
        # 디스크를 다시 읽지 않으므로 입력을 늦출 이유도 없다.
        needle = text.strip().lower()
        found = False
        for head, items in self._sections:
            shown = 0
            for item in items:
                ok = matches(item.node_type, needle)
                item.setVisible(ok)
                shown += ok
            head.setVisible(shown > 0)
            found = found or shown > 0
        self.empty.setVisible(not found)

    def _add_first(self) -> None:
        """엔터를 치면 맨 위에 걸린 것을 더한다 — 손을 옮기지 않아도 되게."""
        types = self.visible_types()
        if types and self.on_add:
            self.on_add(types[0])


# ---------------------------------------------------------------- 속성 패널


def field(label_text: str, value_widget: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)

    label = QLabel(label_text)
    label.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {T.INK_2};")
    lay.addWidget(label)
    lay.addWidget(value_widget)

    if hint:
        note = QLabel(hint)
        note.setStyleSheet(f"font-size: 10px; color: {T.INK_4};")
        note.setWordWrap(True)
        lay.addWidget(note)
    return box


def value_box(text: str, mono: bool = False) -> QWidget:
    box = QFrame()
    box.setObjectName("ValueBox")
    box.setFixedHeight(32)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(9, 0, 9, 0)

    label = QLabel(text or "—")
    family = f"font-family: '{T.mono_stack()}'; " if mono else ""
    label.setStyleSheet(f"{family}font-size: 12px;")
    lay.addWidget(label)
    lay.addStretch(1)
    return box


def swatch_box(rgb, mono_text: str) -> QWidget:
    box = QFrame()
    box.setObjectName("ValueBox")
    box.setFixedHeight(32)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(9, 0, 9, 0)
    lay.setSpacing(8)

    if rgb:
        chip = QFrame()
        chip.setFixedSize(14, 14)
        chip.setStyleSheet(
            f"background: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
            "border: 1px solid rgba(27,30,35,0.15); border-radius: 3px;"
        )
        lay.addWidget(chip)

    label = QLabel(mono_text)
    label.setStyleSheet(f"font-family: '{T.mono_stack()}'; font-size: 12px;")
    lay.addWidget(label)
    lay.addStretch(1)
    return box


def port_glyph(port: str, ratio: float) -> QWidget:
    """참/거짓을 캔버스와 같은 기호로."""
    truthy = port in ("true", "loop")
    color = T.RUN if truthy else T.INK_4
    glyph = "check" if truthy else "cross"

    holder = QFrame()
    holder.setFixedSize(16, 16)
    holder.setStyleSheet(
        f"background: #FFFFFF; border: 1px solid {color}; border-radius: 8px;"
    )
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    icon = QLabel()
    icon.setPixmap(T.icon_pixmap(glyph, 9, T.RUN if truthy else T.INK_3, 2.4, ratio))
    icon.setFixedSize(9, 9)
    lay.addWidget(icon, 0, Qt.AlignCenter)
    return holder


PORT_NAME = {"next": "다음", "true": "참", "false": "거짓",
             "loop": "반복", "done": "빠져나감"}


class Inspector(QWidget):
    """선택한 노드의 값을 보여주고 고친다."""

    def __init__(self, ratio: float):
        super().__init__()
        self.ratio = ratio
        self.setObjectName("Panel")
        self.setFixedWidth(INSPECTOR_W)
        self.tolerance = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.head = QWidget()
        self.head.setFixedHeight(40)
        self.head_lay = QHBoxLayout(self.head)
        self.head_lay.setContentsMargins(12, 0, 12, 0)
        self.head_lay.setSpacing(8)
        root.addWidget(self.head)

        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {T.RULE_1};")
        root.addWidget(rule)

        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(12, 14, 12, 14)
        self.body_lay.setSpacing(14)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(self.body)
        root.addWidget(area, 1)

        self.show_node(None, None)

    # ------------------------------------------------------------

    def set_narrow(self, narrow: bool) -> None:
        self.setFixedWidth(INSPECTOR_W_NARROW if narrow else INSPECTOR_W)

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            # deleteLater 는 다음 이벤트 루프에나 지운다. 그때까지 옛 위젯이
            # 부모에 남아 새 항목을 가리므로 부모에서 먼저 떼어낸다.
            widget.setParent(None)
            widget.deleteLater()

    def show_node(self, node: Optional[Node], graph: Optional[Graph],
                  on_change=None) -> None:
        self._clear(self.head_lay)
        self._clear(self.body_lay)
        self.on_change = on_change
        self.tolerance = None

        if node is None:
            title = QLabel("속성")
            title.setStyleSheet("font-size: 12px; font-weight: 600;")
            self.head_lay.addWidget(title)
            self.head_lay.addStretch(1)

            empty = QLabel("노드를 선택하면\n설정이 여기에 나타납니다.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"font-size: 12px; color: {T.INK_4};")
            self.body_lay.addStretch(1)
            self.body_lay.addWidget(empty)
            self.body_lay.addStretch(2)
            return

        # 머리말
        self.head_lay.addWidget(icon_chip(node.type, self.ratio, 20, 12, 5))
        title = QLabel(node.name or LABEL.get(node.type, node.type))
        title.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.head_lay.addWidget(title)
        self.head_lay.addStretch(1)
        nid = QLabel(node.id)
        nid.setStyleSheet(f"font-family: '{T.mono_stack()}'; font-size: 11px; color: {T.INK_4};")
        self.head_lay.addWidget(nid)

        for widget in self._fields_for(node, graph):
            self.body_lay.addWidget(widget)

        branches = self._branches(node, graph)
        if branches is not None:
            self.body_lay.addWidget(branches)

        self.body_lay.addStretch(1)

    # ------------------------------------------------------------

    def _locator_sources(self, node: Node, graph: Optional[Graph]):
        """좌표를 남기는 다른 노드들 — 좌표 칸에서 골라 따라갈 수 있다."""
        if graph is None:
            return []
        return [(nid, f"{LABEL.get(graph.nodes[nid].type, nid)} ({nid})")
                for nid in graph.locators(exclude=node.id)]

    def _fields_for(self, node: Node, graph: Optional[Graph] = None) -> List[QWidget]:
        specs = FIELDS.get(node.type, [])
        if not specs:
            note = {"start": "여기서 실행이 시작됩니다.",
                    "stop": "여기서 실행을 끝냅니다."}.get(node.type, "설정할 값이 없습니다.")
            label = QLabel(note)
            label.setWordWrap(True)
            label.setStyleSheet(f"font-size: 12px; color: {T.INK_3};")
            return [label]

        out: List[QWidget] = []
        self.tolerance = None
        for key, label, kind, options, hint in specs:
            if kind == "point":
                options = dict(options,
                               sources=self._locator_sources(node, graph))
            elif kind == "tolerance":
                options = dict(options, base=node.params.get("color"))
            widget = build_widget(
                kind,
                node.params.get(key, DEFAULTS.get(node.type, {}).get(key)),
                options,
                lambda value, k=key: self._changed(node, k, value),
            )
            if kind == "tolerance":
                self.tolerance = widget
            out.append(field(label, widget, hint))
        return out

    def _changed(self, node: Node, key: str, value) -> None:
        # 기준 색이 바뀌면 허용 오차 견본도 따라가야 한다
        if key == "color" and self.tolerance is not None:
            self.tolerance.set_base(value)
        if self.on_change:
            self.on_change(node, key, value)

    def _branches(self, node: Node, graph: Optional[Graph]) -> Optional[QWidget]:
        if graph is None or not node.ports:
            return None

        card = QFrame()
        card.setObjectName("ListCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for index, port in enumerate(node.ports):
            row = QWidget()
            row.setFixedHeight(34)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(9, 0, 9, 0)
            rl.setSpacing(8)

            if len(node.ports) > 1:
                rl.addWidget(port_glyph(port, self.ratio))
                name = QLabel(PORT_NAME.get(port, port))
                truthy = port in ("true", "loop")
                name.setStyleSheet(
                    f"font-size: 11px; font-weight: 500;"
                    f"color: {T.RUN if truthy else T.INK_3};"
                )
                rl.addWidget(name)

            arrow = QLabel()
            arrow.setPixmap(T.icon_pixmap("arrow_right", 12, T.RULE_4, 1.5, self.ratio))
            arrow.setFixedSize(12, 12)
            rl.addWidget(arrow)

            target_id = graph.next_id(node.id, port)
            target = graph.node(target_id)
            if target is not None:
                text = target.name or LABEL.get(target.type, target.type)
                color = T.INK
            else:
                text, color = "연결 없음", T.INK_4
            label = QLabel(text)
            label.setStyleSheet(f"font-size: 12px; color: {color};")
            rl.addWidget(label)
            rl.addStretch(1)

            if target_id:
                tid = QLabel(target_id)
                tid.setStyleSheet(
                    f"font-family: '{T.mono_stack()}'; font-size: 10px; color: {T.INK_4};")
                rl.addWidget(tid)

            lay.addWidget(row)
            if index < len(node.ports) - 1:
                rule = QFrame()
                rule.setFixedHeight(1)
                rule.setStyleSheet(f"background: {T.RULE_1};")
                lay.addWidget(rule)

        return field("출력 분기", card)
