# ui_qt/editor.py
"""매크로 편집기 창.

가운데 캔버스에 노드를 놓고 잇는다. 왼쪽 팔레트에서 노드를 더하고, 오른쪽
패널에서 고른 노드의 값을 고친다. 되돌리기는 그래프 전체를 찍어 두는 방식.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import hotkeys, prefs, runlock, runlog
from core.graph import Graph
from core.graph import layout as auto_layout
from ui_qt import dialogs, node_view, theme as T
from ui_qt.editor_panels import BP_NARROW_PANELS, DRAG_PREFIX, Inspector, Palette
from ui_qt.fields import DEFAULTS
from ui_qt.frameless import FramelessWindow
from ui_qt.runner import MacroRunner, describe


HISTORY_LIMIT = 60          # 되돌리기 단계 수


class StateIconButton(QPushButton):
    """아이콘 색이 버튼 상태를 따라가는 버튼.

    QSS 는 글자·테두리만 바꿀 수 있고 아이콘(픽스맵) 색은 못 바꾼다. 그래서
    비활성·호버일 때 아이콘을 다시 그려 끼운다.
    """

    def __init__(self, text: str, glyph: str, ratio: float,
                 normal: str, hover: str, disabled: str,
                 size: int = 12, stroke: float = 1.4):
        super().__init__(text)
        self.ratio = ratio
        self.glyph = glyph
        self.size = size
        self.stroke = stroke
        self.colors = {"normal": normal, "hover": hover, "disabled": disabled}

        self.setIconSize(QSize(size, size))
        self.setCursor(Qt.PointingHandCursor)
        self._apply()

    def _apply(self, hovered: bool = False) -> None:
        if not self.isEnabled():
            key = "disabled"
        elif hovered:
            key = "hover"
        else:
            key = "normal"
        self.setIcon(T.icon_pixmap(
            self.glyph, self.size, self.colors[key], self.stroke, self.ratio))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._apply(hovered=True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._apply(hovered=False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._apply(hovered=self.underMouse())


class EditorWindow(FramelessWindow):
    # 단축키 콜백은 keyboard 라이브러리의 다른 스레드에서 온다. Qt 신호로
    # 넘겨야 UI 스레드에서 실행된다 (홈 화면과 같은 이유).
    hotkey_run = Signal()
    hotkey_stop = Signal()
    #: 창이 실제로 닫혔을 때. destroyed 는 C++ 쪽을 허무는 중에 오므로,
    #: 그때 홈 화면을 건드리면 이미 지워진 위젯을 만질 수 있다.
    closed = Signal()
    #: 파일에 저장했을 때. 목록 쪽이 단축키·노드 수를 다시 읽게 한다.
    saved = Signal()
    """매크로 하나를 여는 창."""

    def __init__(self, path: Path, ratio: float = 1.0, parent=None):
        super().__init__()
        self.path = Path(path)
        self.ratio = ratio
        self.dirty = False

        self.setObjectName("Root")
        self.setWindowTitle(f"{self.path.stem} — Clikey")
        self.setWindowIcon(QIcon(T.APP_ICON))
        self.resize(1280, 860)
        # 캔버스가 사라질 만큼 작아지지는 않게 바닥을 정해둔다
        self.setMinimumSize(760, 520)

        self.model = self._load()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())

        self.ng = node_view.make_graph_widget()
        self.made = node_view.populate(self.model, self.ng)
        self._dropped_edges = self._undrawn_edges()
        self._pick_targets = set()      # 좌표를 가져올 후보 (고르는 중일 때만)
        self._pick_done = None
        self.binder = hotkeys.HotkeyBinder()
        self.hotkey_run.connect(self.run_macro)
        self.hotkey_stop.connect(self.stop_macro)
        self.by_ui_name = {ui.name(): nid for nid, ui in self.made.items()}

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)

        self.palette = Palette(ratio, on_add=self.add_node)
        middle.addWidget(self.palette)
        middle.addWidget(self._vrule())

        middle.addWidget(self.ng.widget, 1)

        middle.addWidget(self._vrule())
        self.inspector = Inspector(ratio)
        self.inspector.on_pick_coord = self.begin_pick_coord
        middle.addWidget(self.inspector)

        middle_holder = QWidget()
        middle_holder.setLayout(middle)
        root.addWidget(middle_holder, 1)

        self.status = QLabel()
        root.addWidget(self._status_bar())

        self.ng.node_selection_changed.connect(self._on_selection)

        # 되돌리기: 통째 스냅샷을 쌓는다. 이동·연결·값 수정·추가·삭제를
        # 한 방식으로 덮을 수 있고, 되살릴 때 모델과 화면이 어긋나지 않는다.
        self._restoring = False
        self._history = [self.model.to_dict()]
        self._hist_at = 0
        self.ng.viewer().moved_nodes.connect(self._after_change)
        # 가운데 버튼은 Delete 와 같게. 화면 끌기는 우클릭이 맡는다.
        self.ng.viewer().viewport().installEventFilter(self)
        self.ng.port_connected.connect(self._after_change)
        self.ng.port_disconnected.connect(self._after_change)
        self.ng.data_dropped.connect(self.drop_node)

        self.refresh_macro_keys()

        self._active_node = None
        self.runner = MacroRunner(self)
        self.runner.node_entered.connect(self._on_node_entered)
        self.runner.finished.connect(self._on_run_finished)

        self.setStyleSheet(T.stylesheet())
        self._refresh_status()

        # 열었을 때 전체가 보이도록
        self.ng.select_all()
        self.ng.fit_to_selection()
        self.ng.clear_selection()

        # 편집이 일어나면 신호로 즉시 표시하고, 신호가 없는 변경(끌어서 이동 등)은
        # 느린 주기 검사로 잡는다. 400ms 마다 전체를 비교하면 가만히 둬도 계속 돈다.
        self._baseline = self._signature()
        for signal in (self.ng.node_created, self.ng.nodes_deleted,
                       self.ng.port_connected, self.ng.port_disconnected,
                       self.ng.property_changed):
            signal.connect(lambda *_: self._check_dirty())

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check_dirty)
        self._watch.start(1500)

        QShortcut(QKeySequence.Save, self, self.save)
        QShortcut(QKeySequence.Delete, self, self.delete_selected)
        QShortcut(QKeySequence("Backspace"), self, self.delete_selected)
        QShortcut(QKeySequence("Ctrl+0"), self, self.fit_view)
        QShortcut(QKeySequence("F"), self, self.fit_view)
        QShortcut(QKeySequence("Ctrl+A"), self, self.ng.select_all)
        QShortcut(QKeySequence("Ctrl+D"), self, self.duplicate_selected)
        QShortcut(QKeySequence("Ctrl+L"), self, self.tidy_layout)
        QShortcut(QKeySequence("Ctrl+F"), self, self.palette.focus_search)
        QShortcut(QKeySequence("Escape"), self, self.end_pick_coord)
        # Windows 에서 QKeySequence.Redo 는 Ctrl+Y 다. 같은 키를 두 번 걸면
        # Qt 가 모호하다고 보고 아무것도 실행하지 않으므로 직접 지정한다.
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.redo)

    # ------------------------------------------------------------ 파일

    def _load(self) -> Graph:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return Graph.from_dict(json.load(f))
        except Exception as exc:
            dialogs.alert(self, "열 수 없음",
                          f"{self.path.name} 을(를) 읽지 못했습니다.\n\n{exc}")
            return Graph()

    def sync_from_canvas(self) -> None:
        """캔버스가 진실인 것들(위치·연결)을 모델로 되읽는다."""
        self.model.layout = node_view.read_layout(self.made)
        self.model.edges = node_view.read_edges(self.made)
        self.model.reindex()

    def save(self) -> None:
        self.sync_from_canvas()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.model.to_json())
        except OSError as exc:
            dialogs.alert(self, "저장 실패", f"{self.path.name}\n\n{exc}")
            return

        self._baseline = self._signature()
        self._set_dirty(False)
        self.saved.emit()

    # ------------------------------------------------------------ 변경 감지

    def _signature(self) -> str:
        """위치·연결·파라미터를 모두 담은 지문. 어떤 편집이든 여기서 잡힌다."""
        return json.dumps(
            {
                "layout": node_view.read_layout(self.made),
                "edges": [e.to_dict() for e in node_view.read_edges(self.made)],
                "nodes": {nid: n.to_dict() for nid, n in self.model.nodes.items()},
                "entry": self.model.entry,
            },
            sort_keys=True, ensure_ascii=False,
        )

    def _check_dirty(self) -> None:
        self._set_dirty(self._signature() != self._baseline)

    def _set_dirty(self, dirty: bool) -> None:
        if dirty == self.dirty:
            return
        self.dirty = dirty
        self.dot.setVisible(dirty)

    # ------------------------------------------------------------ 되돌리기

    def _snapshot(self) -> dict:
        self.sync_from_canvas()
        return self.model.to_dict()

    def record_history(self) -> None:
        """바뀐 뒤의 상태를 기록한다.

        '바꾸기 직전'을 잡으려면 모든 편집 경로에 훅이 필요한데, 연결처럼
        NodeGraphQt 안에서 일어나는 변경은 그럴 자리가 없다. 그래서 변경된
        결과만 차곡차곡 쌓고, 되돌리기는 한 칸 앞 상태로 돌아가는 식으로 한다.
        """
        if self._restoring:
            return
        state = self._snapshot()
        if self._history[self._hist_at] == state:
            return

        del self._history[self._hist_at + 1:]      # 되돌린 뒤 편집하면 앞쪽은 버린다
        self._history.append(state)
        if len(self._history) > HISTORY_LIMIT:
            self._history.pop(0)
        self._hist_at = len(self._history) - 1

    @property
    def can_undo(self) -> bool:
        return self._hist_at > 0

    @property
    def can_redo(self) -> bool:
        return self._hist_at < len(self._history) - 1

    def undo(self) -> None:
        # 아직 기록되지 않은 편집이 있으면 먼저 남긴다
        self.record_history()
        if not self.can_undo:
            return
        self._hist_at -= 1
        self._restore(self._history[self._hist_at])

    def redo(self) -> None:
        if not self.can_redo:
            return
        self._hist_at += 1
        self._restore(self._history[self._hist_at])

    def _restore(self, state: dict) -> None:
        """스냅샷으로 캔버스를 다시 만든다. 화면 위치·확대는 건드리지 않는다."""
        self._restoring = True
        try:
            selected = {self.by_ui_name.get(ui.name())
                        for ui in self.ng.selected_nodes()}

            self.model = Graph.from_dict(state)
            existing = self.ng.all_nodes()
            if existing:
                self.ng.delete_nodes(existing, push_undo=False)

            self.made = node_view.populate(self.model, self.ng)
            self.by_ui_name = {ui.name(): nid for nid, ui in self.made.items()}

            for node_id in selected:
                ui = self.made.get(node_id)
                if ui is not None:
                    ui.set_selected(True)
        finally:
            self._restoring = False

        self._refresh_status()
        self.inspector.show_node(None, None)
        self._check_dirty()

    def _after_change(self, *_) -> None:
        """연결·이동 등 캔버스에서 일어난 변경 뒤."""
        if self._restoring:
            return
        self.record_history()
        self._check_dirty()

    # ------------------------------------------------------------ 편집

    def drop_node(self, mime, scene_pos) -> None:
        """팔레트에서 캔버스로 끌어다 놓았을 때."""
        text = mime.text() if mime.hasText() else ""
        if not text.startswith(DRAG_PREFIX):
            return
        node_type = text[len(DRAG_PREFIX):]
        if node_type in node_view.LABEL:
            # 놓은 지점이 카드의 가운데가 되도록 살짝 당긴다
            self.add_node(node_type, at=(scene_pos.x() - 90, scene_pos.y() - 30))

    def add_node(self, node_type: str, at=None) -> None:
        """팔레트에서 고른 노드를 놓는다.

        `at` 이 주어지면 그 자리에, 아니면 고른 노드 아래에 이어 붙이고,
        그것도 없으면 화면 가운데에 둔다.
        """
        if node_type in node_view.FIXED_TYPES and any(
                n.type == node_type for n in self.model.nodes.values()):
            label = node_view.LABEL[node_type]
            dialogs.alert(self, f"{label} 노드", f"{label} 노드는 하나만 둘 수 있습니다.")
            return

        node = self.model.add_node(node_type, dict(DEFAULTS.get(node_type, {})))
        if at is not None:
            pos, after = at, None
        else:
            pos, after = self._placement_for_new_node()

        ui = node_view.add_node(node, self.ng, pos)
        self.made[node.id] = ui
        self.by_ui_name[ui.name()] = node.id

        # 고른 노드의 빈 출력에 자동으로 이어 준다 — 매번 손으로 잇지 않게
        if after is not None:
            source, port = after
            try:
                source.get_output(port).connect_to(ui.get_input("in"), push_undo=False)
            except Exception:
                pass

        self.ng.clear_selection()
        ui.set_selected(True)
        self._show_in_inspector(node.id)
        self._refresh_status()
        self.record_history()
        self._check_dirty()

    def _placement_for_new_node(self):
        """(놓을 좌표, 이어붙일 (화면노드, 포트) 또는 None)."""
        selected = self.ng.selected_nodes()
        if len(selected) == 1:
            source = selected[0]
            source_id = self.by_ui_name.get(source.name())
            model_node = self.model.node(source_id)
            if model_node is not None:
                x, y = source.pos()
                free = next((p for p in model_node.ports
                             if self.model.next_id(source_id, p) is None), None)
                if free is not None:
                    offset = 0 if free in ("next", "true", "loop") else 300
                    return (x + offset, y + 170), (source, free)
                return (x + 300, y), None

        viewer = self.ng.viewer()
        center = viewer.mapToScene(viewer.viewport().rect().center())
        step = (len(self.made) % 6) * 28          # 연속 추가 시 겹치지 않게
        return (center.x() - 80 + step, center.y() - 30 + step), None

    def tidy_layout(self) -> None:
        """노드를 흐름대로 다시 앉힌다.

        자리는 캔버스가 진실이므로 모델을 먼저 맞춘 뒤 계산하고, 결과를
        다시 캔버스에 돌려준다. 되돌리기 한 번으로 원래대로 돌아간다.
        """
        if not self.made:
            return

        self.sync_from_canvas()
        placed = auto_layout.arrange(self.model, node_view.read_sizes(self.made))
        if not node_view.set_positions(self.made, placed):
            self.fit_view()               # 이미 정렬돼 있어도 눌린 티는 나게
            return

        self.model.layout = node_view.read_layout(self.made)
        self.record_history()
        self._check_dirty()
        self.fit_view()

    def fit_view(self) -> None:
        """전체가 보이도록 화면을 맞춘다. 넓은 그래프에서 길을 잃지 않게.

        NodeGraphQt 는 '선택한 것에 맞추기'만 제공하므로 잠깐 전체를 선택했다가
        원래 선택으로 되돌린다.
        """
        keep = list(self.ng.selected_nodes())
        self.ng.select_all()
        self.ng.fit_to_selection()

        self.ng.clear_selection()
        for ui in keep:
            ui.set_selected(True)

    def duplicate_selected(self) -> None:
        """고른 노드를 값까지 그대로 복제한다 (연결은 잇지 않는다)."""
        selected = self.ng.selected_nodes()
        if not selected:
            return

        made = []
        for ui in selected:
            source = self.model.node(self.by_ui_name.get(ui.name()))
            if source is None or source.type in node_view.FIXED_TYPES:
                continue

            copy = self.model.add_node(source.type, dict(source.params), source.name)
            x, y = ui.pos()
            new_ui = node_view.add_node(copy, self.ng, (x + 40, y + 40))
            self.made[copy.id] = new_ui
            self.by_ui_name[new_ui.name()] = copy.id
            made.append(new_ui)

        if not made:
            return

        self.ng.clear_selection()
        for ui in made:
            ui.set_selected(True)
        if len(made) == 1:
            self._show_in_inspector(self.by_ui_name[made[0].name()])
        self._refresh_status()
        self.record_history()
        self._check_dirty()

    def _delete_selected_pipes(self, record: bool = True) -> bool:
        """고른 연결선을 끊는다. 하나라도 끊었으면 True.

        `record=False` 는 곧이어 노드도 지울 때 — 되돌리기 기록은 한 번만
        남기려는 것이다.
        """
        pipes = self.ng.viewer().selected_pipes()
        if not pipes:
            return False

        by_view = {ui.view: node_id for node_id, ui in self.made.items()}
        cut = 0
        for pipe in pipes:
            out_item, in_item = pipe.output_port, pipe.input_port
            if out_item is None or in_item is None:
                continue

            source = self.made.get(by_view.get(out_item.node))
            target = self.made.get(by_view.get(in_item.node))
            if source is None or target is None:
                continue
            try:
                source.get_output(out_item.name).disconnect_from(
                    target.get_input(in_item.name), push_undo=False)
                cut += 1
            except Exception:
                pass

        if not cut:
            return False

        if record:
            self._refresh_status()
            self.record_history()
            self._check_dirty()
        return True

    def delete_selected(self) -> None:
        selected = self.ng.selected_nodes()
        if not selected:
            # 선만 골랐을 때
            self._delete_selected_pipes()
            return

        removing = [self.by_ui_name.get(ui.name()) for ui in selected]
        removing = [nid for nid in removing if nid]

        fixed = [self.model.nodes[nid].type for nid in removing
                 if nid in self.model.nodes
                 and self.model.nodes[nid].type in node_view.FIXED_TYPES]
        if fixed:
            names = " · ".join(sorted({node_view.LABEL[t] for t in fixed}))
            dialogs.alert(self, "지울 수 없음",
                          f"{names} 노드는 매크로에 항상 있어야 합니다.")
            return

        # 노드와 선을 함께 골랐으면 한 번에 지운다. 선부터 끊고 멈추면
        # 노드가 남아 두 번 눌러야 했다.
        self._delete_selected_pipes(record=False)

        for node_id in removing:
            self.model.remove_node(node_id)
            ui = self.made.pop(node_id, None)
            if ui is not None:
                self.by_ui_name.pop(ui.name(), None)
                self.ng.delete_node(ui, push_undo=False)

        self.inspector.show_node(None, None)
        self._refresh_status()
        self.record_history()
        self._check_dirty()

    def _on_param_changed(self, node, key: str, value) -> None:
        node.params[key] = value
        cut = []
        ui = self.made.get(node.id)
        if ui is not None:
            node_view.refresh_card(ui, node)

            # 선택지가 곧 출력 포트다. 바뀌면 포트를 다시 만들어야 하고,
            # 사라진 선택지에 걸려 있던 흐름은 갈 곳이 없어 끊긴다.
            if key == "choices":
                cut = node_view.rebuild_ports(ui, node)

        # 시작·종료의 단축키를 바꿨으면 버튼과 안내도 따라간다
        if key == "hotkey" and node.type in node_view.FIXED_TYPES:
            self.refresh_macro_keys()

        self.record_history()
        self._check_dirty()

        # 상태줄은 _check_dirty 가 다시 쓴다. 끊긴 연결은 그 뒤에 얹어야
        # 사용자 눈에 남는다.
        if cut:
            self.status.setText(
                f"선택지를 지워 연결이 끊겼습니다 — {', '.join(cut)}")

    # ------------------------------------------------------------ 매크로 단축키

    def macro_keys(self):
        """(실행 키, 종료 키) — 시작·종료 노드에 적힌 값."""
        start = self.model.start_node()
        stop = next((n for n in self.model.nodes.values() if n.type == "stop"), None)
        return (str((start.params if start else {}).get("hotkey") or ""),
                str((stop.params if stop else {}).get("hotkey") or ""))

    def refresh_macro_keys(self) -> None:
        """버튼 글자와 단축키를 매크로에 적힌 키로 맞춘다."""
        run_key, stop_key = self.macro_keys()

        self.run_btn.setText(f"  실행  {hotkeys.display(run_key)}"
                             if run_key else "  실행")
        self.stop_btn.setText(f"  중지  {hotkeys.display(stop_key)}"
                              if stop_key else "  중지")

        # 창에만 거는 단축키로는 편집기가 앞에 있을 때만 먹는다. 매크로를
        # 돌려보는 동안에는 대개 다른 창을 보고 있으므로 전역으로 건다.
        entries = []
        if run_key:
            entries.append((run_key, "실행", self.hotkey_run.emit))
        if stop_key:
            entries.append((stop_key, "중지", self.hotkey_stop.emit))
        self.binder.bind(entries)

        # 실행·중지 키는 상단 버튼에 이미 적혀 있으므로 여기서 되풀이하지 않는다

    # ------------------------------------------------------------ 실행

    # ------------------------------------------------------------ 창 크기

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 창이 좁아지면 양옆 패널을 먼저 줄인다 — 캔버스가 마지막까지 남게
        narrow = self.width() < BP_NARROW_PANELS
        self.palette.set_narrow(narrow)
        self.inspector.set_narrow(narrow)

    def _undrawn_edges(self) -> list:
        """파일에는 있는데 캔버스에 그려지지 않은 연결.

        NodeGraphQt 는 잇지 못해도 예외를 내지 않고 조용히 넘어가거나 기존
        연결을 갈아치우기도 한다. 그래서 실패를 붙잡는 대신, 그려진 결과와
        원래 모델을 견줘 본다.
        """
        drawn = {(e.src, e.dst, e.port) for e in node_view.read_edges(self.made)}
        return [e for e in self.model.edges
                if (e.src, e.dst, e.port) not in drawn]

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.MiddleButton):
            self._delete_under_cursor(event.position().toPoint())
            return True         # 여기서 멈춘다 (기본 동작인 화면 끌기 대신)
        return super().eventFilter(obj, event)

    def _delete_under_cursor(self, spot) -> None:
        """가운데 버튼 아래 있는 것을 지운다.

        먼저 고르고 누르게 하면 손이 두 번 간다. 커서 밑에 노드나 선이 있으면
        그것을 고른 것으로 치고, 빈 곳이면 이미 골라둔 것을 지운다.
        """
        viewer = self.ng.viewer()
        node, pipe = node_view.item_at(viewer, viewer.mapToScene(spot))

        if node is not None or pipe is not None:
            self.ng.clear_selection()
            for old in viewer.selected_pipes():
                old.setSelected(False)
            if node is not None:
                node.selected = True
            else:
                pipe.setSelected(True)

        self.delete_selected()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dropped_edges:
            dropped, self._dropped_edges = self._dropped_edges, []
            QTimer.singleShot(0, lambda n=len(dropped): self._warn_dropped(n))

    def _warn_dropped(self, count: int) -> None:
        """그리지 못한 연결이 있으면 저장 전에 알린다.

        저장할 때는 캔버스가 진실이라, 알리지 않고 두면 다음 저장에서 그
        연결이 소리 없이 사라진다.
        """
        dialogs.alert(
            self, "그리지 못한 연결",
            f"이 매크로의 연결 {count}개를 캔버스에 그릴 수 없었습니다.\n"
            "한 출력에서 두 갈래로 나가는 등 지금 규칙에 맞지 않는 연결입니다.\n\n"
            "이대로 저장하면 그 연결은 사라집니다.")

    def run_macro(self) -> None:
        if self.runner.running:
            return

        # 버튼은 이미 잠겨 있다. 단축키로도 들어올 수 있으므로 여기서도
        # 막되 알림까지 띄우지는 않는다 — 까닭은 버튼에 올리면 나온다.
        if self.model.mcp_only:
            self.status.setText(self.MCP_ONLY_WHY)
            return

        # 실행권은 대시보드·Claude 와 함께 본다. 둘이 동시에 돌면 마우스를
        # 서로 뺏어 어느 쪽도 제대로 돌지 않는다.
        busy = runlock.holder()
        if busy is not None:
            dialogs.alert(self, "지금은 실행할 수 없음",
                          "‘" + busy + "’ 가 돌고 있습니다.")
            return

        problems = self.model.validate()
        if problems:
            dialogs.alert(self, "실행할 수 없음",
                          "먼저 아래 문제를 고쳐주세요.\n\n• " + "\n• ".join(problems[:6]))
            return

        # 실행 설정은 이 매크로(시작 노드)의 값을 쓴다
        settings = self.model.run_settings(prefs.load())
        _, stop_key = self.macro_keys()
        if not runlock.acquire(self.path.stem):
            return

        started = self.runner.start(
            self.model,
            step_delay=settings["step_delay"],
            mouse_move_duration=settings["mouse_move_duration"],
            bind_stop_hotkey=bool(stop_key),
            stop_hotkey=stop_key,
        )
        if not started:
            runlock.release()
            return

        # 편집기에서 돌린 것도 실행이다 — 목록의 마지막 실행에 남긴다
        runlog.mark(self.path)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status.setText(
            f"실행 중…  {hotkeys.display(stop_key)} 로 중지" if stop_key
            else "실행 중…  중지 버튼으로 멈춥니다")

    def stop_macro(self) -> None:
        self.runner.stop()
        self.status.setText("중지하는 중…")

    def _on_node_entered(self, node_id: str) -> None:
        if self._active_node and self._active_node in self.made:
            self.made[self._active_node].view.running = False
            self.made[self._active_node].view.update()

        ui = self.made.get(node_id)
        if ui is not None:
            ui.view.running = True
            ui.view.update()
        self._active_node = node_id

    def _on_run_finished(self, result) -> None:
        runlock.release()
        if self._active_node and self._active_node in self.made:
            self.made[self._active_node].view.running = False
            self.made[self._active_node].view.update()
        self._active_node = None

        self.stop_btn.setEnabled(False)
        self._refresh_run_button()
        self.status.setText(describe(result))
        QTimer.singleShot(6000, self._refresh_status)

    # ------------------------------------------------------------ 선택

    # ------------------------------------------------------------ 좌표 가져오기

    def begin_pick_coord(self, candidates, on_pick) -> None:
        """좌표를 가져올 노드를 캔버스에서 직접 고르게 한다.

        목록에 노드 id 를 늘어놓아도 그게 어느 노드인지 알 방법이 없다.
        고를 수 있는 노드만 남기고 나머지는 흐리게 해서 눈으로 고르게 한다.
        """
        self._pick_targets = set(candidates)
        self._pick_done = on_pick
        if not self._pick_targets:
            return

        self.ng.clear_selection()
        self._set_scene_picking(True)
        for node_id, ui in self.made.items():
            can = node_id in self._pick_targets
            ui.view.dimmed = not can
            ui.view.set_pickable(can)
        self.status.setText("좌표를 가져올 노드를 클릭하세요  ·  Esc 취소")

    def end_pick_coord(self) -> None:
        if not self._pick_targets:
            return
        self._pick_targets = set()
        self._pick_done = None
        self._set_scene_picking(False)
        for ui in self.made.values():
            ui.view.dimmed = False
            ui.view.set_pickable(False)
        self._refresh_status()

    def _set_scene_picking(self, on: bool) -> None:
        """선이 마우스에 반응하지 않도록 캔버스에 표시해 둔다."""
        viewer = self.ng.viewer()
        scene = viewer.scene()
        scene._clikey_picking = on
        if on:
            # 이미 켜져 있던 선은 꺼둔다
            for pipe in viewer.all_pipes():
                if not pipe.isSelected():
                    pipe.reset()

    def _picking(self) -> bool:
        return bool(self._pick_targets)

    def _on_selection(self, selected=None, deselected=None) -> None:
        """캔버스에서 고른 노드를 속성 패널에 보여준다.

        신호가 실어 보내는 것은 '이번에 새로 골라진 노드' 라, 이미 골라둔
        노드를 다시 누르거나 끌면 빈 목록이 온다. 그것을 지금 선택으로
        믿으면 속성 패널이 꺼져 버린다. 그래서 캔버스에 직접 물어본다.
        """
        nodes = self.ng.selected_nodes()

        if self._picking():
            # 고르는 중에는 선택이 곧 "이 노드의 좌표를 쓰겠다" 는 뜻이다
            if len(nodes) == 1:
                node_id = self.by_ui_name.get(nodes[0].name())
                if node_id in self._pick_targets:
                    done = self._pick_done
                    self.end_pick_coord()
                    if done:
                        done(node_id)
                    return
            return

        if len(nodes) != 1:
            self.inspector.show_node(None, None)
            return
        self._show_in_inspector(self.by_ui_name.get(nodes[0].name()))

    def _show_in_inspector(self, node_id) -> None:
        # 분기 목록이 캔버스와 맞도록 연결을 먼저 되읽는다
        self.sync_from_canvas()
        self.inspector.show_node(
            self.model.node(node_id), self.model, on_change=self._on_param_changed)

    # ------------------------------------------------------------ 화면

    @staticmethod
    def _vrule() -> QWidget:
        rule = QFrame()
        rule.setFixedWidth(1)
        rule.setStyleSheet(f"background: {T.RULE_2};")
        return rule

    def _top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        # 선택자를 반드시 붙인다. 선택자 없이 쓰면 이 규칙이 자식 위젯까지
        # 내려가고, 가까운 조상의 스타일이 앱 전역 스타일을 이겨서
        # 버튼 테두리 아랫변이 회색으로 덮인다.
        bar.setObjectName("EditorTopBar")
        bar.setStyleSheet(f"QWidget#EditorTopBar {{ border-bottom: 1px solid {T.RULE_2}; }}")
        self._caption_bar = bar

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(T.logo_pixmap(22, self.ratio))
        logo.setFixedSize(22, 22)
        lay.addWidget(logo)

        name = QLabel(self.path.stem)
        name.setStyleSheet("font-size: 13px; font-weight: 500;")
        lay.addWidget(name)

        suffix = QLabel(self.path.suffix)
        suffix.setStyleSheet(f"font-family: '{T.mono_stack()}'; font-size: 11px; color: {T.INK_4};")
        lay.addWidget(suffix)

        self.dot = QFrame()
        self.dot.setFixedSize(5, 5)
        self.dot.setStyleSheet("background: #C07818; border-radius: 2px;")
        self.dot.setVisible(False)
        lay.addWidget(self.dot)

        lay.addStretch(1)

        self.tidy_btn = StateIconButton(
            "  정렬", "tidy", self.ratio,
            normal=T.INK_2, hover=T.INK, disabled=T.INK_4, size=T.ICON_SM,
        )
        self.tidy_btn.setObjectName("TidyBtn")
        self.tidy_btn.setFixedHeight(32)
        self.tidy_btn.setToolTip("노드를 흐름대로 자동 정렬 (Ctrl+L)")
        self.tidy_btn.clicked.connect(self.tidy_layout)
        lay.addWidget(self.tidy_btn)

        # 실행 / 중지
        self.run_btn = StateIconButton(
            "  실행", "play", self.ratio,
            normal="#FFFFFF", hover="#FFFFFF", disabled=T.INK_4, size=T.ICON_SM,
        )
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setFixedHeight(32)
        self.run_btn.clicked.connect(self.run_macro)
        lay.addWidget(self.run_btn)

        self.stop_btn = StateIconButton(
            "  중지", "stop", self.ratio,
            normal=T.DANGER, hover="#FFFFFF", disabled=T.INK_4, size=T.ICON_SM,
        )
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setFixedHeight(32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_macro)
        lay.addWidget(self.stop_btn)

        spacer = QWidget()
        spacer.setFixedWidth(10)
        lay.addWidget(spacer)

        from ui_qt.home import CaptionButton      # 순환 import 를 피해 여기서

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
            btn.setFixedSize(46, 48)
            btn.clicked.connect(slot)
            bl.addWidget(btn)
            if icon == "maximize":
                self._max_btn = btn
        lay.addWidget(buttons)
        return bar

    def _status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setObjectName("EditorStatusBar")
        bar.setStyleSheet(f"QWidget#EditorStatusBar {{ border-top: 1px solid {T.RULE_2}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.PAGE_PAD, 0, T.PAGE_PAD, 0)
        lay.setSpacing(14)

        self.status.setObjectName("StatusBar")
        lay.addWidget(self.status)
        lay.addStretch(1)

        hint = QLabel("F 전체 보기 · Ctrl+L 정렬 · Ctrl+Z 되돌리기 · "
                      "Ctrl+D 복제 · Del 삭제 · Ctrl+S 저장")
        hint.setObjectName("StatusBar")
        lay.addWidget(hint)
        return bar

    #: 여기서는 실행할 수 없는 까닭. 버튼에 마우스를 올리면 이것이 보인다.
    MCP_ONLY_WHY = ("AI 판단 노드는 판단해 줄 상대가 필요합니다. "
                    "Claude Code 에서 실행하세요.")

    def _refresh_run_button(self) -> None:
        """AI 판단이 든 매크로는 실행 버튼을 잠근다.

        눌러 놓고 알림으로 막으면 손이 한 번 더 간다. 애초에 눌리지 않게 하고
        까닭은 마우스를 올렸을 때만 보여준다.
        """
        blocked = self.model.mcp_only
        self.run_btn.setEnabled(not blocked and not self.runner.running)
        self.run_btn.setToolTip(self.MCP_ONLY_WHY if blocked else "")

    def _refresh_status(self) -> None:
        self.sync_from_canvas()
        self._refresh_run_button()
        problems = self.model.validate()
        text = f"노드 {len(self.model.nodes)} · 연결 {len(self.model.edges)}"
        if problems:
            text += f"  ·  문제 {len(problems)}건"

        # 시작에서 닿지 않는 노드는 아무리 잘 만들어도 실행되지 않는다.
        # 검사에는 걸리지 않으므로(틀린 그래프는 아니다) 여기서 알려준다.
        stranded = self.model.unreachable_ids()
        if stranded:
            text += f"  ·  실행되지 않는 노드 {len(stranded)}개"
        self.status.setText(text)

    # ------------------------------------------------------------ 창 조작

    def changeEvent(self, event):
        super().changeEvent(event)
        # 설정은 대시보드에서 연다. 창을 다시 잡을 때 연동 여부를 다시 본다.
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.palette.refresh_gates()
        if event.type() == QEvent.WindowStateChange and hasattr(self, "_max_btn"):
            self._max_btn.set_glyph("restore" if self.isMaximized() else "maximize")

    def closeEvent(self, event):
        if self.runner.running:
            _, stop_key = self.macro_keys()
            how = f"{hotkeys.display(stop_key)} 로" if stop_key else "중지 버튼으로"
            dialogs.alert(self, "실행 중",
                          f"매크로가 실행 중입니다. {how} 먼저 중지해주세요.")
            event.ignore()
            return

        if not self.dirty:
            self.binder.clear()
            event.accept()
            self.closed.emit()
            return

        answer = dialogs.confirm_save(
            self, "저장하지 않은 변경",
            f"‘{self.path.stem}’ 의 변경 내용을 저장할까요?",
        )
        if answer == "cancel":
            event.ignore()
            return
        if answer == "save":
            self.save()
        event.accept()
        self.binder.clear()
        self.closed.emit()
