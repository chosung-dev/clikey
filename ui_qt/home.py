# ui_qt/home.py
"""홈 화면 — 매크로 목록.

지금은 표시용 샘플 데이터를 쓴다. 실제 저장소가 정해지면 `load_macros()` 만
바꾸면 되도록 화면과 데이터를 갈라놨다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from PySide6.QtCore import QEvent, QTimer, Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import hotkeys, library, prefs, runlog
from core.persistence import load_app_state, save_app_state
from core.graph import Graph
from ui_qt import dialogs, theme as T
from ui_qt.frameless import FramelessWindow
from ui_qt.runner import MacroRunner


# ---------------------------------------------------------------- 데이터

WAITING, RUNNING, DISABLED = "waiting", "running", "disabled"

ALL_FOLDERS = "\x00all"          # 사이드바 "전체" 를 가리키는 표시값

# 행을 한 번에 다 만들면 개수가 많을 때 창이 멈춘다(레이아웃에 위젯을 더할 때마다
# 기존 행이 다시 배치되어 비용이 제곱으로 는다). 화면에 들어올 만큼만 먼저 만들고,
# 나머지는 스크롤로 내려올 때 이어서 만든다 — 안 본 행은 만들지 않는다.
FIRST_CHUNK = 24
NEXT_CHUNK = 24
SCROLL_MARGIN = 240              # 바닥에서 이만큼 남으면 다음 묶음을 만든다


def clear_layout(layout) -> None:
    """레이아웃을 비운다 (안에 든 레이아웃까지).

    주의: 위젯을 먼저 변수에 담아야 한다. setParent(None) 을 하면 그 항목의
    widget() 이 None 이 되어, 곧바로 다시 쓰면 터진다.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            # deleteLater 는 다음 이벤트 루프에나 지우므로 먼저 떼어낸다
            widget.setParent(None)
            widget.deleteLater()
            continue
        inner = item.layout()
        if inner is not None:
            clear_layout(inner)


@dataclass
class Macro:
    name: str
    folder: str
    nodes: int
    last_run: str
    status: str = WAITING
    shortcut: str = ""          # 실행 단축키 (시작 노드)
    stop_shortcut: str = ""     # 종료 단축키 (종료 노드)
    progress: str = ""          # 실행 중일 때 "12/50"
    path: Optional[object] = None
    broken: bool = False
    enabled: bool = True        # 꺼두면 단축키를 걸지 않는다


@dataclass
class Folder:
    name: str
    count: int
    icon: str = "folder"


def load_macros() -> List[Macro]:
    """라이브러리를 스캔한다. 폴더에 담긴 것만 다룬다 (루트 파일은 제외)."""
    macros = []
    for entry in library.scan():
        if entry.folder == library.UNFILED:
            continue
        macros.append(Macro(
            name=entry.name,
            folder=entry.folder,
            nodes=entry.nodes,
            last_run=runlog.text(entry.path),
            shortcut=entry.start_key,
            stop_shortcut=entry.stop_key,
            path=entry.path,
            broken=entry.broken,
            enabled=entry.enabled,
            status=WAITING if entry.enabled else DISABLED,
        ))
    return macros


def load_folders(macros: List[Macro]) -> List[Folder]:
    counts = {}
    for m in macros:
        counts[m.folder] = counts.get(m.folder, 0) + 1
    return [Folder(name, counts.get(name, 0)) for name in library.folder_names()]


# ---------------------------------------------------------------- 작은 조각


def icon_label(name: str, size: int, color: str, width: float = 1.4,
               ratio: float = 1.0) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(T.icon_pixmap(name, size, color, width, ratio))
    lbl.setFixedSize(size, size)
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    return lbl


def chip(size: int, radius: int, bg: str) -> QFrame:
    box = QFrame()
    box.setFixedSize(size, size)
    box.setStyleSheet(f"background: {bg}; border-radius: {radius}px;")
    return box


def icon_chip(name: str, color: str, bg: str, box_size: int = 30,
              icon_size: int = 15, radius: int = 7, ratio: float = 1.0) -> QFrame:
    box = chip(box_size, radius, bg)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(icon_label(name, icon_size, color, ratio=ratio), 0, Qt.AlignCenter)
    return box


class Pill(QFrame):
    """상태 표시 알약 — 점/아이콘 + 글자."""

    def __init__(self, text: str, fg: str, bg: str, *, dot: Optional[str] = None,
                 icon: Optional[str] = None, icon_color: str = "", ratio: float = 1.0):
        super().__init__()
        self.setFixedHeight(24)
        self.setStyleSheet(f"background: {bg}; border-radius: 12px;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 9, 0)
        lay.setSpacing(6)

        if dot == "solid":
            marker = QFrame()
            marker.setFixedSize(6, 6)
            marker.setStyleSheet(f"background: {fg}; border-radius: 3px;")
            lay.addWidget(marker)
        elif dot == "hollow":
            marker = QFrame()
            marker.setFixedSize(6, 6)
            marker.setStyleSheet(
                f"background: transparent; border: 1px solid {T.INK_4}; border-radius: 3px;"
            )
            lay.addWidget(marker)
        elif icon:
            lay.addWidget(icon_label(icon, 11, icon_color or fg, 2.0, ratio))

        label = QLabel(text)
        label.setStyleSheet(f"font-size: 11px; color: {fg};")
        lay.addWidget(label)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


def status_pill(macro: Macro, ratio: float) -> QWidget:
    if macro.status == RUNNING:
        text = f"실행 중 · {macro.progress}" if macro.progress else "실행 중"
        return Pill(text, T.RUN_DEEP, T.RUN_BG, dot="solid")
    if macro.status == DISABLED:
        return Pill("사용 안 함", T.INK_3, T.CHIP_NEUTRAL,
                    icon="pause", icon_color=T.INK_4, ratio=ratio)
    return Pill("대기 중", T.INK_2, T.CHIP_NEUTRAL, dot="hollow")


# ---------------------------------------------------------------- 사이드바


class InlineEdit(QLineEdit):
    """제목 자리에서 바로 고치는 입력칸. Esc 로 취소."""

    def __init__(self, on_commit, on_cancel):
        super().__init__()
        self.setObjectName("TitleEdit")
        self.on_commit = on_commit
        self.on_cancel = on_cancel
        self._settled = False
        self.returnPressed.connect(self._commit)
        self.editingFinished.connect(self._commit)   # 포커스를 잃어도 저장

    def start(self, text: str) -> None:
        self._settled = False
        self.setText(text)
        self.setProperty("invalid", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()
        self.setFocus()
        self.selectAll()

    def finish(self) -> None:
        """편집을 접는다. hide() 는 editingFinished 를 부르므로 먼저 잠가야
        취소·화면 전환이 뜻하지 않게 저장으로 이어지지 않는다."""
        self._settled = True
        self.hide()

    def mark_invalid(self) -> None:
        """저장에 실패했으니 계속 고치게 둔다."""
        self._settled = False
        self.setProperty("invalid", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setFocus()
        self.selectAll()

    def _commit(self) -> None:
        # returnPressed 와 editingFinished 가 함께 오므로 한 번만 처리
        if self._settled:
            return
        self._settled = True
        self.on_commit(self.text().strip())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._settled = True
            self.on_cancel()
            return
        super().keyPressEvent(event)


class ClickableTitle(QLabel):
    """폴더 화면에서는 제목을 눌러 이름을 바꾼다."""

    def __init__(self, on_click=None):
        super().__init__("")
        self.on_click = on_click
        self.editable = False

    def set_editable(self, editable: bool) -> None:
        self.editable = editable
        self.setCursor(Qt.PointingHandCursor if editable else Qt.ArrowCursor)
        self.setToolTip("눌러서 폴더 이름 바꾸기" if editable else "")

    def mouseReleaseEvent(self, event):
        if (self.editable and event.button() == Qt.LeftButton
                and self.rect().contains(event.pos()) and self.on_click):
            self.on_click()
        super().mouseReleaseEvent(event)


class CaptionButton(QPushButton):
    """창 조작 버튼. 닫기는 호버 시 배경이 붉어지므로 아이콘도 흰색으로 바꾼다."""

    def __init__(self, icon: str, ratio: float, danger: bool = False):
        super().__init__()
        self.ratio = ratio
        self.danger = danger
        self.setObjectName("WinBtnClose" if danger else "WinBtn")
        self.setFixedSize(46, 40)
        self.setIconSize(QSize(13, 13))
        self.set_glyph(icon)

    def set_glyph(self, icon: str) -> None:
        self._icon = icon
        self._paint(hovered=self.underMouse())

    def _paint(self, hovered: bool) -> None:
        color = "#FFFFFF" if (self.danger and hovered) else T.INK_2
        self.setIcon(T.icon_pixmap(self._icon, 13, color, 1.4, self.ratio))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._paint(hovered=True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._paint(hovered=False)


class NavItem(QFrame):
    def __init__(self, icon: str, text: str, count: Optional[int] = None,
                 selected: bool = False, height: int = 34, ratio: float = 1.0,
                 on_click=None, on_menu=None):
        super().__init__()
        self.ratio = ratio
        self.icon_name = icon
        self.on_click = on_click
        self.on_menu = on_menu
        self.setFixedHeight(height)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)

        self.glyph = icon_label(icon, 16, T.INK_2, ratio=ratio)
        lay.addWidget(self.glyph)

        self.label = QLabel(text)
        lay.addWidget(self.label)
        lay.addStretch(1)

        self.count = QLabel(str(count)) if count is not None else None
        if self.count is not None:
            lay.addWidget(self.count)

        self.set_selected(selected)

    def set_selected(self, selected: bool) -> None:
        self.setObjectName("NavItemOn" if selected else "NavItem")
        self.label.setObjectName("NavTextOn" if selected else "NavText")
        if self.count is not None:
            self.count.setObjectName("NavCountOn" if selected else "NavCount")
        self.glyph.setPixmap(T.icon_pixmap(
            self.icon_name, 16, T.ACCENT if selected else T.INK_2, 1.4, self.ratio))
        # objectName 을 바꾼 뒤에는 스타일을 다시 물려야 반영된다
        for widget in (self, self.label, self.count):
            if widget is not None:
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.on_click:
            self.on_click()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        if self.on_menu:
            self.on_menu(event.globalPos())


class Sidebar(QWidget):
    def __init__(self, folders: List[Folder], total: int, ratio: float,
                 on_select=None, on_menu=None, on_new_folder=None,
                 on_settings=None):
        super().__init__()
        self.ratio = ratio
        self.on_select = on_select
        self.on_menu = on_menu
        self.on_new_folder = on_new_folder
        self.on_settings = on_settings or (lambda: None)
        self.nav_items = {}
        self.setObjectName("Sidebar")
        self.setFixedWidth(T.SIDEBAR_W)
        # 목록 위에 겹쳐 띄울 때 뒤가 비쳐 보이지 않도록 배경을 직접 칠하게 한다
        self.setAttribute(Qt.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 브랜드
        brand = QWidget()
        brand.setFixedHeight(56)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(T.logo_pixmap(26, ratio))
        logo.setFixedSize(26, 26)
        bl.addWidget(logo)

        name = QLabel("Clikey")
        name.setObjectName("Brand")
        bl.addWidget(name)
        bl.addStretch(1)
        root.addWidget(brand)

        # 폴더 머리
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 6, 18, 6)
        section = QLabel("폴더")
        section.setObjectName("SectionLabel")
        hl.addWidget(section)
        hl.addStretch(1)

        add_btn = QPushButton()
        add_btn.setObjectName("TinyBtn")
        add_btn.setFixedSize(20, 20)
        add_btn.setIcon(T.icon_pixmap("plus", 12, T.INK_4, 1.6, ratio))
        add_btn.setIconSize(QSize(12, 12))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setToolTip("새 폴더")
        if on_new_folder:
            add_btn.clicked.connect(on_new_folder)
        hl.addWidget(add_btn)
        root.addWidget(head)

        # 폴더 목록
        self.folder_box = QWidget()
        self.folder_lay = QVBoxLayout(self.folder_box)
        self.folder_lay.setContentsMargins(10, 0, 10, 0)
        self.folder_lay.setSpacing(1)
        root.addWidget(self.folder_box)
        self.set_folders(folders, ALL_FOLDERS)

        root.addStretch(1)

        # 설정
        settings_box = QWidget()
        sl = QVBoxLayout(settings_box)
        sl.setContentsMargins(10, 0, 10, 4)
        sl.addWidget(NavItem("gear", "설정", height=36, ratio=ratio,
                             on_click=self.on_settings))
        root.addWidget(settings_box)

    def set_folders(self, folders: List[Folder], selected_key: str) -> None:
        """폴더가 바뀌었을 때 목록을 다시 만든다."""
        while self.folder_lay.count():
            item = self.folder_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.nav_items = {}

        def add(key, icon, text, count, menu_name=None):
            item = NavItem(
                icon, text, count, selected=(key == selected_key), ratio=self.ratio,
                on_click=lambda k=key: self._choose(k),
                on_menu=(lambda pos, n=menu_name: self.on_menu(n, pos))
                if (self.on_menu and menu_name) else None,
            )
            self.nav_items[key] = item
            self.folder_lay.addWidget(item)

        add(ALL_FOLDERS, "all", "전체", None)
        for f in folders:
            add(f.name, f.icon, f.name, f.count, menu_name=f.name)

    def _choose(self, key: str) -> None:
        for name, item in self.nav_items.items():
            item.set_selected(name == key)
        if self.on_select:
            self.on_select(key)


# ---------------------------------------------------------------- 표


def column_widths():
    return (T.COL_SHORTCUT, T.COL_NODES, T.COL_LASTRUN, T.COL_STATUS)


#: 창이 좁아질 때 감출 순서 — 뒤로 갈수록 오래 남는다
COLUMNS = ("nodes", "last", "shortcut", "status")


def visible_columns(width: int) -> set:
    """창 폭에 맞춰 남길 열. 이름과 상태는 어떤 폭에서도 남는다."""
    shown = set(COLUMNS)
    if width < T.BP_HIDE_NODES:
        shown.discard("nodes")
    if width < T.BP_HIDE_LASTRUN:
        shown.discard("last")
    if width < T.BP_HIDE_SHORTCUT:
        shown.discard("shortcut")
    return shown


class SearchBox(QWidget):
    """돋보기를 겹쳐 놓은 검색칸. 창 폭에 맞춰 늘었다 줄었다 한다.

    돋보기를 레이아웃에 넣지 않고 입력칸 위에 겹쳐 두므로, 크기가 바뀔 때마다
    직접 자리를 잡아준다.
    """

    def __init__(self, ratio: float, on_text, placeholder: str = "이름으로 검색"):
        super().__init__()
        self.setFixedHeight(34)
        self.setMinimumWidth(150)
        self.setMaximumWidth(300)

        self.edit = QLineEdit(self)
        self.edit.setObjectName("Search")
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(on_text)

        self.glass = QLabel(self)
        self.glass.setPixmap(T.icon_pixmap("search", 14, T.INK_4, 1.5, ratio))

    def resizeEvent(self, event):
        self.edit.setGeometry(0, 0, self.width(), self.height())
        self.glass.setGeometry(10, (self.height() - 14) // 2, 14, 14)
        super().resizeEvent(event)


class HeaderRow(QFrame):
    def __init__(self, columns=None):
        super().__init__()
        self.setObjectName("HeadRow")
        self.setFixedHeight(34)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 0)
        lay.setSpacing(T.COL_GAP)

        name = QLabel("이름")
        name.setObjectName("ColHead")
        lay.addWidget(name, 1)

        self.cells = {}
        if columns is None:
            columns = list(zip(("shortcut", "nodes", "last", "status"),
                               ("단축키", "노드", "마지막 실행", "상태"),
                               column_widths()))
        else:
            columns = [(None, text, width) for text, width in columns]

        for key, text, width in columns:
            label = QLabel(text)
            label.setObjectName("ColHead")
            label.setFixedWidth(width)
            lay.addWidget(label)
            if key:
                self.cells[key] = label

    def apply_columns(self, shown: set) -> None:
        for key, widget in self.cells.items():
            widget.setVisible(key in shown)


class FolderRow(QFrame):
    """'전체' 화면에서 폴더 하나."""

    def __init__(self, folder: Folder, ratio: float, on_open=None, on_menu=None):
        super().__init__()
        self.folder = folder
        self.on_open = on_open
        self.on_menu = on_menu
        self.setObjectName("Row")
        self.setFixedHeight(T.ROW_H)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 0)
        lay.setSpacing(T.COL_GAP)

        left = QHBoxLayout()
        left.setSpacing(11)
        left.addWidget(icon_chip("folder", "#6B7280", T.CHIP_NEUTRAL, 30, 16, 7, ratio))

        name = QLabel(folder.name)
        name.setObjectName("RowName")
        left.addWidget(name)
        left.addStretch(1)

        holder = QWidget()
        holder.setLayout(left)
        lay.addWidget(holder, 1)

        count = QLabel(f"{folder.count}개" if folder.count else "비어 있음")
        count.setObjectName("Cell" if folder.count else "CellMuted")
        count.setFixedWidth(T.COL_LASTRUN)
        self.cells = {"last": count}
        lay.addWidget(count)

        arrow = QLabel()
        arrow.setPixmap(T.icon_pixmap("arrow_right", 13, T.INK_4, 1.5, ratio))
        arrow.setFixedWidth(24)
        lay.addWidget(arrow)

    def apply_columns(self, shown: set) -> None:
        for key, widget in self.cells.items():
            widget.setVisible(key in shown)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            if self.on_open:
                self.on_open(self.folder.name)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.on_menu:
            self.on_menu(self.folder.name, event.globalPos())


class MacroRow(QFrame):
    def __init__(self, macro: Macro, ratio: float, on_open=None, on_menu=None):
        super().__init__()
        running = macro.status == RUNNING
        dimmed = macro.status == DISABLED

        self.macro = macro
        self.ratio = ratio
        self.on_open = on_open
        self.on_menu = on_menu
        self.setObjectName("RowOn" if running else "Row")
        self.setFixedHeight(T.ROW_H)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 0)
        lay.setSpacing(T.COL_GAP)

        # 이름 + 폴더
        left = QHBoxLayout()
        left.setSpacing(11)
        if running:
            left.addWidget(icon_chip("play", T.RUN, T.RUN_BG, 30, 12, 7, ratio))
        else:
            left.addWidget(icon_chip(
                "graph", T.INK_4 if dimmed else "#6B7280", T.CHIP_NEUTRAL, 30, 15, 7, ratio))

        text = QVBoxLayout()
        text.setSpacing(2)
        text.setContentsMargins(0, 0, 0, 0)
        title = QLabel(macro.name)
        title.setObjectName("RowNameMuted" if dimmed else "RowName")
        folder = QLabel(macro.folder)
        folder.setObjectName("RowFolder")
        text.addWidget(title)
        text.addWidget(folder)
        left.addLayout(text)
        left.addStretch(1)

        holder = QWidget()
        holder.setLayout(left)
        lay.addWidget(holder, 1)

        # 단축키
        if macro.shortcut:
            kbd = QLabel(hotkeys.display(macro.shortcut))
            kbd.setObjectName("KbdMuted" if dimmed else "Kbd")
            kbd.setFixedHeight(22)
            kbd.setAlignment(Qt.AlignCenter)
            cell = self._cell(kbd, T.COL_SHORTCUT)
        else:
            dash = QLabel("—")
            dash.setObjectName("CellEmpty")
            cell = self._cell(dash, T.COL_SHORTCUT)
        self.cells = {"shortcut": cell}
        lay.addWidget(cell)

        # 노드 수
        nodes = QLabel(str(macro.nodes))
        nodes.setObjectName("CellMuted" if dimmed else "Cell")
        self.cells["nodes"] = self._cell(nodes, T.COL_NODES)
        lay.addWidget(self.cells["nodes"])

        # 마지막 실행
        last = QLabel(macro.last_run)
        last.setObjectName("Cell")
        if running:
            last.setStyleSheet(f"font-size: 12px; color: {T.RUN};")
        elif dimmed:
            last.setObjectName("CellMuted")
        self.last_cell = last
        self.cells["last"] = self._cell(last, T.COL_LASTRUN)
        lay.addWidget(self.cells["last"])

        # 상태 — 실행 중에는 바꿔 끼울 수 있어야 하므로 자리를 들고 있는다
        self.status_slot = QWidget()
        slot_lay = QHBoxLayout(self.status_slot)
        slot_lay.setContentsMargins(0, 0, 0, 0)
        slot_lay.addWidget(status_pill(macro, ratio), 0,
                           Qt.AlignVCenter | Qt.AlignLeft)
        slot_lay.addStretch(1)
        self.status_slot.setFixedWidth(T.COL_STATUS)
        self.cells["status"] = self.status_slot
        lay.addWidget(self.status_slot)

        self.icon_slot = None

    def apply_columns(self, shown: set) -> None:
        for key, widget in self.cells.items():
            widget.setVisible(key in shown)

    def set_running(self, running: bool) -> None:
        """실행 상태에 맞춰 행 모습을 바꾼다."""
        if running:
            self.macro.status = RUNNING
        else:
            self.macro.status = WAITING if self.macro.enabled else DISABLED
        self.setObjectName("RowOn" if running else "Row")
        self.style().unpolish(self)
        self.style().polish(self)

        # 실행을 시작하면 "방금" 으로 바뀐다
        self.last_cell.setText(self.macro.last_run)
        self.last_cell.setStyleSheet(
            f"font-size: 12px; color: {T.RUN};" if running else "")

        lay = self.status_slot.layout()
        old = lay.itemAt(0).widget()
        if old is not None:
            lay.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        lay.insertWidget(0, status_pill(self.macro, self.ratio), 0,
                         Qt.AlignVCenter | Qt.AlignLeft)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            if self.on_open and self.macro.path:
                self.on_open(self.macro)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.on_menu:
            self.on_menu(self.macro, event.globalPos())

    @staticmethod
    def _cell(widget: QWidget, width: int) -> QWidget:
        wrap = QWidget()
        wrap.setFixedWidth(width)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget, 0, Qt.AlignVCenter | Qt.AlignLeft)
        lay.addStretch(1)
        return wrap


# ---------------------------------------------------------------- 홈 화면


class HomeWindow(FramelessWindow):
    # 단축키 콜백은 keyboard 라이브러리의 다른 스레드에서 온다. QTimer 로는
    # 그 스레드에 이벤트 루프가 없어 아무 일도 일어나지 않으므로, Qt 가 알아서
    # UI 스레드로 넘겨주는 신호를 쓴다.
    hotkey_run = Signal(object)
    hotkey_stop = Signal(object)

    def __init__(self, ratio: float = 1.0):
        super().__init__()
        self.ratio = ratio
        self.setObjectName("Root")
        self.setWindowTitle("Clikey")
        self.setWindowIcon(QIcon(T.APP_ICON))
        self.resize(1440, 900)

        self.macros: List[Macro] = load_macros()
        self.folder_key = ALL_FOLDERS
        self.query = ""
        self._pending_query = ""
        self.editors = {}
        self._build_gen = 0
        self._pending_rows: List[Macro] = []
        self._stretch_added = False
        #: 지금 보이고 있는 표의 열 (창 폭에 따라 바뀐다)
        self._columns = visible_columns(1440)
        #: 넓은 창에서 사용자가 직접 접어둔 상태인가 (다음에 켤 때도 이어진다)
        self._sidebar_collapsed = bool(load_app_state().get("sidebar_collapsed"))
        #: 좁은 창에서 버튼으로 잠깐 펼쳐둔 상태인가 (폴더를 고르면 도로 접힌다)
        self._drawer_open = False
        #: 좁을 때는 목록을 밀어내지 않고 그 위에 겹쳐 띄운다
        self._sidebar_floating = False
        # 창이 아주 작아지면 알아볼 수 없으므로 바닥을 정해둔다
        self.setMinimumSize(560, 420)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_search)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._root_layout = root

        self.binder = hotkeys.HotkeyBinder()
        self.runners = {}
        self.running_paths = set()
        self.last_results = {}
        self._failed_keys = []

        self.hotkey_run.connect(self.run_macro)
        self.hotkey_stop.connect(self.stop_macro)

        self.sidebar = Sidebar(
            load_folders(self.macros), len(self.macros), ratio,
            on_select=self._on_folder,
            on_menu=self.folder_menu,
            on_new_folder=self.new_folder,
            on_settings=self.open_settings,
        )
        root.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._window_bar())
        right.addWidget(self._header())

        self.head_holder = QWidget()
        self.head_box = QVBoxLayout(self.head_holder)
        self.head_box.setContentsMargins(0, 0, 0, 0)
        self.head_box.setSpacing(0)
        right.addWidget(self.head_holder)

        self.rows_box = QVBoxLayout()
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(0)

        body = QWidget()
        body.setLayout(self.rows_box)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(body)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        right.addWidget(self.scroll, 1)

        right.addWidget(self._status_bar())

        holder = QWidget()
        holder.setLayout(right)
        root.addWidget(holder, 1)

        self.setStyleSheet(T.stylesheet())
        self._rebuild()
        self._update_status()

    # ------------------------------------------------------------ 목록 갱신

    def visible_macros(self) -> List[Macro]:
        items = self.macros
        if self.folder_key != ALL_FOLDERS:
            items = [m for m in items if m.folder == self.folder_key]
        if self.query:
            needle = self.query.lower()
            items = [m for m in items if needle in m.name.lower()]
        return items

    @staticmethod
    def _empty_layout(layout) -> None:
        clear_layout(layout)

    @property
    def in_folder_list(self) -> bool:
        """'전체' 화면 — 매크로 대신 폴더를 보여준다."""
        return self.folder_key == ALL_FOLDERS and not self.query

    def _rebuild(self) -> None:
        # 세대 번호를 올려 이전 목록을 채우던 작업을 무효화한다
        self._build_gen += 1
        self._pending_rows = []
        self._stretch_added = False

        self._empty_layout(self.rows_box)
        self._empty_layout(self.head_box)

        # 이름 편집 중이었다면 정리하고 오류 표시도 되돌린다
        if self.title_edit.isVisible():
            self._end_rename()
        self._set_meta_style("PageMeta")

        if self.in_folder_list:
            self._build_folder_list()
        else:
            self._build_macro_list()

        # 남은 행이 있으면 스크롤로 내려올 때 만든다. 창이 커서 아직 스크롤이
        # 안 생겼다면 생길 때까지만 더 채운다.
        if self._pending_rows:
            QTimer.singleShot(0, lambda gen=self._build_gen: self._fill_viewport(gen))
        else:
            self._finish_rows()

        # 폴더 목록에서는 새 매크로 버튼을 숨긴다 — 어느 폴더에 만들지 정해지지 않았다
        self.new_btn.setVisible(not self.in_folder_list)
        # 폴더 안에 있을 때만 제목을 눌러 이름을 바꿀 수 있다
        self.title_label.set_editable(
            not self.in_folder_list and not self.query
            and self.folder_key != ALL_FOLDERS
        )

    # ------------------------------------------------------------ 제목에서 바로 이름 바꾸기

    def _set_meta_style(self, name: str) -> None:
        """objectName 만 바꾸면 Qt 가 스타일을 다시 계산하지 않는다. 항상 함께 처리."""
        self.meta_label.setObjectName(name)
        self.meta_label.style().unpolish(self.meta_label)
        self.meta_label.style().polish(self.meta_label)

    def _show_rename_error(self, message: str) -> None:
        """알림창 대신 부제 자리에 이유를 띄우고 계속 고치게 둔다."""
        self.meta_label.setText(message)
        self._set_meta_style("PageError")
        self.title_edit.mark_invalid()

    def _begin_rename(self) -> None:
        self._rename_from = self.folder_key
        self.title_label.hide()
        self.title_edit.start(self.folder_key)

    def _end_rename(self) -> None:
        self.title_edit.finish()
        self.title_label.show()

    def _cancel_rename(self) -> None:
        self._end_rename()
        self._rebuild()

    def _commit_rename(self, name: str) -> None:
        old = getattr(self, "_rename_from", self.folder_key)

        if not name or name == old:
            self._cancel_rename()
            return

        problem = library.check_folder_name(name, allow=old)
        if problem:
            self._show_rename_error(problem)
            return

        try:
            library.rename_folder(old, name)
        except OSError as exc:
            self._show_rename_error(f"바꾸지 못했습니다 — {exc}")
            return

        self._end_rename()
        self.reload(select=name)

    def _build_folder_list(self) -> None:
        folders = load_folders(self.macros)
        self.head_box.addWidget(HeaderRow([("매크로", T.COL_LASTRUN), ("", 24)]))

        self.title_label.setText("전체")
        self.meta_label.setText(f"폴더 {len(folders)}개" if folders else "폴더 없음")

        for folder in folders:
            row = FolderRow(folder, self.ratio,
                            on_open=self._on_folder, on_menu=self.folder_menu)
            row.apply_columns(self._columns)
            self.rows_box.addWidget(row)

        if not folders:
            self.rows_box.addWidget(self._empty_state())

    def _build_macro_list(self) -> None:
        header = HeaderRow()
        header.apply_columns(self._columns)
        self.head_box.addWidget(header)

        shown = self.visible_macros()
        if self.query:
            self.title_label.setText("검색 결과")
        else:
            self.title_label.setText(self.folder_key)

        scope = len(self.macros) if self.folder_key == ALL_FOLDERS else sum(
            1 for m in self.macros if m.folder == self.folder_key)
        self.meta_label.setText(
            f"{len(shown)}개" if len(shown) == scope else f"{len(shown)}개 / {scope}개")

        if not shown:
            self.rows_box.addWidget(self._empty_state())
            return

        # 행을 한 번에 다 만들면 개수가 많을 때 창이 멈춘다. 화면에 들어올 만큼만
        # 먼저 만들고 나머지는 이벤트 루프에 양보해가며 채운다.
        self._add_rows(shown[:FIRST_CHUNK])
        self._pending_rows = shown[FIRST_CHUNK:]

    def _add_rows(self, macros: List[Macro]) -> None:
        """행을 뒤에 붙인다. 스트레치는 다 채운 뒤에야 붙이므로 항상 append."""
        body = self.rows_box.parentWidget()
        body.setUpdatesEnabled(False)          # 한 묶음을 그리는 동안 재배치를 미룬다
        try:
            for macro in macros:
                row = MacroRow(macro, self.ratio,
                               on_open=self.open_macro, on_menu=self.macro_menu)
                row.apply_columns(self._columns)
                self.rows_box.addWidget(row)
        finally:
            body.setUpdatesEnabled(True)

    def _finish_rows(self) -> None:
        """다 채웠으면 남는 공간을 밀어내는 스트레치를 붙인다."""
        if self._stretch_added:
            return
        self.rows_box.addStretch(1)
        self._stretch_added = True

    def _build_more(self) -> None:
        """다음 묶음을 만든다. 스크롤이 바닥에 가까워졌을 때 불린다."""
        if not self._pending_rows:
            self._finish_rows()
            return

        chunk = self._pending_rows[:NEXT_CHUNK]
        self._pending_rows = self._pending_rows[NEXT_CHUNK:]
        self._add_rows(chunk)

        if not self._pending_rows:
            self._finish_rows()

    # ------------------------------------------------------------ 창 크기

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_layout()

    def _apply_layout(self) -> None:
        """창 폭에 맞춰 사이드바를 좁히고 표에서 열을 덜어낸다."""
        width = self.width()

        self.sidebar.setFixedWidth(
            T.SIDEBAR_W_NARROW if width < T.BP_NARROW_SIDEBAR else T.SIDEBAR_W)

        # 아주 좁으면 자리를 아끼려 저절로 접는다. 버튼으로 잠깐 펼 수 있다.
        cramped = width < T.BP_HIDE_SIDEBAR
        if not cramped:
            self._drawer_open = False
        self._set_sidebar_floating(cramped)

        columns = visible_columns(width)
        if columns != self._columns:
            self._columns = columns
            for box in (self.head_box, self.rows_box):
                for i in range(box.count()):
                    widget = box.itemAt(i).widget()
                    if hasattr(widget, "apply_columns"):
                        widget.apply_columns(columns)

        # 창이 커지면 아래에 빈 자리가 생긴다 — 채울 행이 남았으면 더 만든다
        if self._pending_rows:
            self._fill_viewport(self._build_gen)

    def _set_sidebar_floating(self, floating: bool) -> None:
        """좁을 때는 사이드바를 레이아웃에서 빼내 목록 위에 겹쳐 띄운다.

        레이아웃에 둔 채로 펼치면 목록을 옆으로 밀어내 제목과 검색칸이 잘린다.
        겹쳐 띄우면 뒤쪽 목록은 폭을 그대로 유지한다.
        """
        if floating != self._sidebar_floating:
            self._sidebar_floating = floating
            if floating:
                self._root_layout.removeWidget(self.sidebar)
                self.sidebar.setParent(self)
            else:
                self.sidebar.setParent(None)
                self._root_layout.insertWidget(0, self.sidebar)

        shown = self._drawer_open if floating else not self._sidebar_collapsed
        self.sidebar.setVisible(shown)
        if floating and shown:
            self.sidebar.setGeometry(0, 0, self.sidebar.width(), self.height())
            self.sidebar.raise_()

        self.folder_btn.setToolTip(
            "폴더 목록 접기" if shown else "폴더 목록 펼치기")

    def _toggle_sidebar(self) -> None:
        """좁을 때는 잠깐 펼치는 서랍, 넓을 때는 계속 접어두는 설정."""
        if self._sidebar_floating:
            self._drawer_open = not self._drawer_open
        else:
            self._sidebar_collapsed = not self._sidebar_collapsed
            save_app_state({"sidebar_collapsed": self._sidebar_collapsed})
        self._set_sidebar_floating(self._sidebar_floating)

    def _collapse_sidebar_if_cramped(self) -> None:
        """좁은 창에서 폴더를 고르면 목록을 다시 보여준다."""
        if self._drawer_open and self._sidebar_floating:
            self._drawer_open = False
            self._set_sidebar_floating(True)      # 툴팁까지 함께 되돌린다

    def _on_scrolled(self, value: int) -> None:
        if not self._pending_rows:
            return
        bar = self.scroll.verticalScrollBar()
        if value >= bar.maximum() - SCROLL_MARGIN:
            self._build_more()

    def _fill_viewport(self, generation: int) -> None:
        """스크롤이 생길 때까지 채운다. 창이 크면 첫 묶음만으론 부족하다."""
        if generation != self._build_gen or not self._pending_rows:
            return
        if self.scroll.verticalScrollBar().maximum() <= 0:
            self._build_more()
            QTimer.singleShot(0, lambda: self._fill_viewport(generation))

    # ------------------------------------------------------------ 전역 단축키

    def _rebind_hotkeys(self) -> None:
        """지금 보고 있는 폴더의 매크로만 단축키를 걸어둔다.

        폴더를 옮기면 이전 폴더 키는 풀린다. 그래야 폴더마다 같은 키를 써도
        서로 부딪히지 않는다.
        """
        if self.folder_key == ALL_FOLDERS:
            self.binder.clear()
            self._update_status()
            return

        here = [m for m in self.macros
                if m.folder == self.folder_key and m.enabled]
        entries = []
        for macro in here:
            if macro.shortcut:
                entries.append((macro.shortcut, f"{macro.name} 실행",
                                lambda m=macro: self._hotkey_run(m)))
            if macro.stop_shortcut:
                entries.append((macro.stop_shortcut, f"{macro.name} 종료",
                                lambda m=macro: self._hotkey_stop(m)))

        # 같은 키에 여러 개가 걸리면 함께 실행된다 (겹침을 막지 않는다)
        self._failed_keys = self.binder.bind(entries)
        self._update_status()

    def _hotkey_run(self, macro: Macro) -> None:
        self.hotkey_run.emit(macro)      # 신호가 UI 스레드로 넘겨준다

    def _hotkey_stop(self, macro: Macro) -> None:
        self.hotkey_stop.emit(macro)

    # ------------------------------------------------------------ 실행

    def run_macro(self, macro: Macro) -> None:
        if not macro.enabled:
            return
        key = str(macro.path)
        if key in self.runners and self.runners[key].running:
            return

        try:
            graph = Graph.from_json(macro.path.read_text(encoding="utf-8"))
        except Exception as exc:
            dialogs.alert(self, "열 수 없음", f"{macro.name}\n\n{exc}")
            return

        problems = graph.validate()
        if problems:
            dialogs.alert(self, "실행할 수 없음",
                          f"‘{macro.name}’ 를 실행할 수 없습니다.\n\n• "
                          + "\n• ".join(problems[:5]))
            return

        runner = MacroRunner(self)
        runner.finished.connect(lambda result, k=key: self._on_run_finished(k, result))
        self.runners[key] = runner

        # 실행 설정은 매크로(시작 노드)에 있고, 없으면 앱 기본값으로 메운다
        settings = graph.run_settings(prefs.load())
        if not runner.start(graph,
                            step_delay=settings["step_delay"],
                            mouse_move_duration=settings["mouse_move_duration"],
                            bind_stop_hotkey=False):
            return

        self.running_paths.add(key)
        macro.last_run = library.humanize(runlog.mark(macro.path))
        self._mark_running(macro, True)

    def stop_macro(self, macro: Macro) -> None:
        runner = self.runners.get(str(macro.path))
        if runner is not None:
            runner.stop()

    def _on_run_finished(self, key: str, result) -> None:
        self.running_paths.discard(key)
        self.last_results[key] = result
        for macro in self.macros:
            if str(macro.path) == key:
                self._mark_running(macro, False)
                break

    def _mark_running(self, macro: Macro, running: bool) -> None:
        if running:
            macro.status = RUNNING
        else:
            macro.status = WAITING if macro.enabled else DISABLED
        for index in range(self.rows_box.count()):
            row = self.rows_box.itemAt(index).widget()
            if isinstance(row, MacroRow) and row.macro is macro:
                row.set_running(running)
                break

    # ------------------------------------------------------------ 폴더 관리

    def reload(self, select: Optional[str] = None) -> None:
        """디스크를 다시 읽고 사이드바·목록을 새로 그린다."""
        self.macros = load_macros()
        if select is not None:
            self.folder_key = select
        if self.folder_key != ALL_FOLDERS and \
                self.folder_key not in library.folder_names():
            self.folder_key = ALL_FOLDERS

        self.sidebar.set_folders(load_folders(self.macros), self.folder_key)
        self._rebuild()
        self._rebind_hotkeys()

    def _ask_name(self, title: str, label: str, validate, preset: str = "",
                  ok_text: str = "확인") -> Optional[str]:
        """이름을 묻고, 쓸 수 없으면 이유를 같은 자리에 보여주며 다시 묻는다.

        validate(name) 은 문제가 있으면 설명을, 없으면 None 을 돌려준다.
        """
        problem = ""
        while True:
            name = dialogs.prompt(self, title, label, text=preset,
                                  ok_text=ok_text, hint=problem, error=bool(problem))
            if name is None:
                return None
            problem = validate(name) or ""
            if not problem:
                return name
            preset = name

    def new_folder(self) -> None:
        name = self._ask_name("새 폴더", "폴더 이름",
                              library.check_folder_name, ok_text="만들기")
        if name is None:
            return
        try:
            library.create_folder(name)
        except OSError as exc:
            dialogs.alert(self, "만들 수 없음", f"{name}\n\n{exc}")
            return
        self.reload(select=name)

    def rename_folder(self, old: str) -> None:
        name = self._ask_name(
            "폴더 이름 바꾸기", "새 이름",
            lambda n: library.check_folder_name(n, allow=old),
            preset=old, ok_text="바꾸기",
        )
        if name is None or name == old:
            return
        try:
            library.rename_folder(old, name)
        except OSError as exc:
            dialogs.alert(self, "바꿀 수 없음", f"{old} → {name}\n\n{exc}")
            return
        self.reload(select=name)

    def duplicate_folder(self, name: str) -> None:
        try:
            made = library.duplicate_folder(name)
        except OSError as exc:
            dialogs.alert(self, "복제할 수 없음", f"{name}\n\n{exc}")
            return
        self.reload(select=made.name)

    def delete_folder(self, name: str) -> None:
        count = library.count_in_folder(name)
        detail = (f"‘{name}’ 폴더와 그 안의 매크로 {count}개를 지웁니다."
                  if count else f"‘{name}’ 폴더를 지웁니다.")

        if not dialogs.confirm(self, "폴더 삭제",
                               f"{detail}\n되돌릴 수 없습니다.",
                               ok_text="삭제", danger=True):
            return

        try:
            library.delete_folder(name)
        except (OSError, ValueError) as exc:
            dialogs.alert(self, "지울 수 없음", f"{name}\n\n{exc}")
            return
        self.reload(select=ALL_FOLDERS)

    def folder_menu(self, name: str, at) -> None:
        menu = QMenu(self)
        menu.addAction("이름 바꾸기", lambda: self.rename_folder(name))
        menu.addAction("복제", lambda: self.duplicate_folder(name))
        menu.addSeparator()
        menu.addAction("삭제", lambda: self.delete_folder(name))
        menu.exec(at)

    # ------------------------------------------------------------ 매크로 관리

    def _editor_open_for(self, macro: Macro) -> bool:
        """편집기에서 열려 있으면 파일을 건드리지 않는다."""
        editor = self.editors.get(str(macro.path))
        if editor is None or not editor.isVisible():
            return False
        dialogs.alert(
            self, "편집기에서 열려 있습니다",
            f"‘{macro.name}’ 을(를) 먼저 닫아주세요.",
        )
        editor.raise_()
        editor.activateWindow()
        return True

    def new_macro(self) -> None:
        folder = self.folder_key
        if folder == ALL_FOLDERS:
            return

        name = self._ask_name(
            "새 매크로", "매크로 이름",
            lambda n: library.check_macro_name(n, folder),
            ok_text="만들기",
        )
        if name is None:
            return

        # 매크로에는 시작과 종료가 항상 있다. 사이는 사용자가 채우므로 잇지 않는다.
        # 단축키는 환경 설정의 기본값을 박아둔다.
        defaults = prefs.load()
        graph = Graph()
        graph.add_node("start", {
            "hotkey": defaults["default_start_key"],
            "step_delay": defaults["step_delay"],
            "mouse_move_duration": defaults["mouse_move_duration"],
        }, node_id="start")
        graph.add_node("stop", {"hotkey": defaults["default_stop_key"]},
                       node_id="end")
        graph.layout["start"] = [0, 0]
        graph.layout["end"] = [0, 320]

        try:
            path = library.create_macro(folder, name, graph.to_json())
        except OSError as exc:
            dialogs.alert(self, "만들 수 없음", f"{name}\n\n{exc}")
            return

        self.reload()
        # 바로 편집기로 — 새로 만든 뒤엔 대개 곧장 손보게 된다
        self.open_macro(Macro(name=name, folder=folder, nodes=len(graph.nodes),
                              last_run="방금", path=path))

    def rename_macro(self, macro: Macro) -> None:
        if self._editor_open_for(macro):
            return

        name = self._ask_name(
            "매크로 이름 바꾸기", "새 이름",
            lambda n: library.check_macro_name(n, macro.folder, allow=macro.name),
            preset=macro.name, ok_text="바꾸기",
        )
        if name is None or name == macro.name:
            return

        try:
            runlog.rename(macro.path, library.rename_macro(macro.path, name))
        except OSError as exc:
            dialogs.alert(self, "바꿀 수 없음", f"{macro.name} → {name}\n\n{exc}")
            return
        self.reload()

    def duplicate_macro(self, macro: Macro) -> None:
        try:
            library.duplicate_macro(macro.path)
        except OSError as exc:
            dialogs.alert(self, "복제할 수 없음", f"{macro.name}\n\n{exc}")
            return
        self.reload()

    def move_macro(self, macro: Macro, folder: str) -> None:
        if self._editor_open_for(macro):
            return
        try:
            runlog.rename(macro.path, library.move_macro(macro.path, folder))
        except FileExistsError:
            dialogs.alert(self, "옮길 수 없음",
                          f"‘{folder}’ 에 같은 이름의 매크로가 이미 있습니다.")
            return
        except OSError as exc:
            dialogs.alert(self, "옮길 수 없음", f"{macro.name}\n\n{exc}")
            return
        self.reload()

    def delete_macro(self, macro: Macro) -> None:
        if self._editor_open_for(macro):
            return
        if not dialogs.confirm(
            self, "매크로 삭제",
            f"‘{macro.name}’ 을(를) 지웁니다.\n되돌릴 수 없습니다.",
            ok_text="삭제", danger=True,
        ):
            return

        try:
            library.delete_macro(macro.path)
            runlog.forget(macro.path)
        except (OSError, ValueError) as exc:
            dialogs.alert(self, "지울 수 없음", f"{macro.name}\n\n{exc}")
            return
        self.reload()

    def macro_menu(self, macro: Macro, at) -> None:
        menu = QMenu(self)
        menu.addAction("열기", lambda: self.open_macro(macro))
        menu.addSeparator()
        menu.addAction("이름 바꾸기", lambda: self.rename_macro(macro))
        menu.addAction("복제", lambda: self.duplicate_macro(macro))

        others = [f for f in library.folder_names() if f != macro.folder]
        move_menu = menu.addMenu("폴더로 이동")
        if others:
            for folder in others:
                move_menu.addAction(folder, lambda f=folder: self.move_macro(macro, f))
        else:
            move_menu.setEnabled(False)

        menu.addSeparator()
        toggle = menu.addAction(
            "다시 사용" if not macro.enabled else "사용 안 함",
            lambda: self.set_macro_enabled(macro, not macro.enabled))
        toggle.setEnabled(not macro.broken)

        menu.addSeparator()
        menu.addAction("삭제", lambda: self.delete_macro(macro))
        menu.exec(at)

    def set_macro_enabled(self, macro: Macro, enabled: bool) -> None:
        """매크로를 잠시 쉬게 한다. 꺼두면 단축키가 풀리고 행이 흐려진다."""
        if self._editor_open_for(macro):
            dialogs.alert(self, "편집 중",
                          f"‘{macro.name}’ 편집기를 닫은 뒤에 바꿔주세요.")
            return
        if not enabled:
            self.stop_macro(macro)

        try:
            library.set_enabled(macro.path, enabled)
        except (OSError, ValueError) as exc:
            dialogs.alert(self, "바꿀 수 없음", f"{macro.name}\n\n{exc}")
            return
        self.reload()

    # ------------------------------------------------------------ 편집기

    def open_macro(self, macro: Macro) -> None:
        """행을 누르면 편집기를 연다. 이미 열려 있으면 그 창을 앞으로."""
        from ui_qt.editor import EditorWindow

        key = str(macro.path)
        existing = self.editors.get(key)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        editor = EditorWindow(macro.path, ratio=self.ratio)
        editor.destroyed.connect(lambda *_: self.editors.pop(key, None))
        self.editors[key] = editor
        editor.show()

    def _on_folder(self, key: str) -> None:
        self.folder_key = key
        # 폴더 행에서도 들어오므로 사이드바 선택을 맞춰준다
        for name, item in self.sidebar.nav_items.items():
            item.set_selected(name == key)
        self._rebuild()
        self._rebind_hotkeys()
        self._collapse_sidebar_if_cramped()

    def _update_status(self) -> None:
        """아래 상태바에 지금 걸린 단축키 상황을 보여준다."""
        count = len(self.binder.bound)
        if self.folder_key == ALL_FOLDERS:
            text = "폴더를 고르면 그 폴더의 단축키가 걸립니다"
        elif count:
            text = f"전역 단축키 {count}개 활성"
        else:
            text = "이 폴더에 걸린 단축키 없음"

        if self._failed_keys:
            keys = ", ".join(hotkeys.display(k)
                             for k in dict.fromkeys(self._failed_keys))
            text += f"  ·  {keys} 는 걸지 못했습니다"

        self.status_text.setText(text)
        self.status_dot.setStyleSheet(
            f"background: {T.RUN if count else T.INK_4}; border-radius: 3px;")

    def open_settings(self) -> None:
        from ui_qt.settings import open_settings

        # 기본 단축키가 바뀌어도 이미 만든 매크로에는 영향이 없다
        open_settings(self)

    def closeEvent(self, event):
        self.binder.clear()
        for runner in self.runners.values():
            runner.stop()
        super().closeEvent(event)

    def _on_search(self, text: str) -> None:
        """타자마다 목록을 다시 그리면 항목이 많을 때 눈에 띄게 버벅인다.
        입력이 잠깐 멈춘 뒤에 한 번만 그린다."""
        self._pending_query = text.strip()
        self._search_timer.start()

    def _apply_search(self) -> None:
        if self._pending_query == self.query:
            return
        self.query = self._pending_query
        self._rebuild()

    def _empty_state(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 90, 0, 0)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        root = library.library_root()
        if self.in_folder_list:
            title = "아직 폴더가 없습니다"
            detail = f"{root} 아래에 폴더를 만들면 여기에 나타납니다."
        elif self.query:
            title, detail = "검색 결과가 없습니다", "다른 이름으로 찾아보세요."
        elif self.macros:
            title = "이 폴더는 비어 있습니다"
            detail = f"{root / self.folder_key} 에 매크로를 넣어보세요."
        else:
            title = "아직 매크로가 없습니다"
            detail = f"{root} 아래 폴더에 넣으면 여기에 나타납니다."

        head = QLabel(title)
        head.setStyleSheet(f"font-size: 14px; font-weight: 500; color: {T.INK_2};")
        head.setAlignment(Qt.AlignCenter)
        lay.addWidget(head)

        note = QLabel(detail)
        note.setStyleSheet(f"font-size: 12px; color: {T.INK_3};")
        note.setAlignment(Qt.AlignCenter)
        lay.addWidget(note)
        return box

    def _window_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        self._caption_bar = bar

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)

        buttons = QWidget()
        self._caption_buttons = buttons
        bl = QHBoxLayout(buttons)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        for icon, danger, slot in (
            ("minus", False, self.showMinimized),
            ("maximize", False, self.toggle_maximized),
            ("close", True, self.close),
        ):
            btn = CaptionButton(icon, self.ratio, danger)
            btn.clicked.connect(slot)
            bl.addWidget(btn)
            if icon == "maximize":
                self._max_btn = btn

        lay.addWidget(buttons)
        return bar

    # ------------------------------------------------------------ 창 조작

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "_max_btn"):
            self._max_btn.set_glyph("restore" if self.isMaximized() else "maximize")

    def _header(self) -> QWidget:
        head = QWidget()
        lay = QHBoxLayout(head)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 18)
        lay.setSpacing(14)

        self.folder_btn = QPushButton()
        self.folder_btn.setObjectName("WinBtn")
        self.folder_btn.setFixedSize(32, 32)
        self.folder_btn.setIcon(T.icon_pixmap("menu", 16, T.INK_2, 1.6, self.ratio))
        self.folder_btn.setIconSize(QSize(16, 16))
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.clicked.connect(self._toggle_sidebar)
        lay.addWidget(self.folder_btn, 0, Qt.AlignVCenter)

        left = QVBoxLayout()
        left.setSpacing(3)
        self.title_label = ClickableTitle(on_click=self._begin_rename)
        self.title_label.setObjectName("PageTitle")

        self.title_edit = InlineEdit(self._commit_rename, self._cancel_rename)
        self.title_edit.setFixedSize(300, 36)
        self.title_edit.hide()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.title_edit)
        title_row.addStretch(1)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("PageMeta")
        left.addLayout(title_row)
        left.addWidget(self.meta_label)
        lay.addLayout(left)
        lay.addStretch(1)
        # (아래 검색칸이 남는 폭을 가져가므로 이 stretch 는 최소 간격 노릇만 한다)

        # 검색 — 남는 자리를 나눠 가진다
        self.search_box = SearchBox(self.ratio, self._on_search)
        lay.addWidget(self.search_box, 1)

        self.new_btn = QPushButton()
        self.new_btn.setObjectName("NewMacro")
        self.new_btn.setFixedSize(34, 34)
        self.new_btn.setIcon(T.icon_pixmap("plus", 15, "#FFFFFF", 1.6, self.ratio))
        self.new_btn.setIconSize(QSize(15, 15))
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setToolTip("새 매크로")
        self.new_btn.clicked.connect(self.new_macro)
        lay.addWidget(self.new_btn)
        return head

    def _status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setObjectName("HomeStatusBar")
        bar.setStyleSheet(f"QWidget#HomeStatusBar {{ border-top: 1px solid {T.RULE_2}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 0)
        lay.setSpacing(7)

        self.status_dot = QFrame()
        self.status_dot.setFixedSize(6, 6)
        self.status_dot.setStyleSheet(f"background: {T.INK_4}; border-radius: 3px;")
        lay.addWidget(self.status_dot)

        self.status_text = QLabel()
        self.status_text.setObjectName("StatusBar")
        lay.addWidget(self.status_text)
        lay.addStretch(1)

        where = QLabel(str(library.library_root()))
        where.setObjectName("StatusBar")
        lay.addWidget(where)
        return bar
