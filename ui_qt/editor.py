# ui_qt/editor.py
"""매크로 편집기 창.

가운데 캔버스에 노드를 놓고 잇는다. 왼쪽 팔레트에서 노드를 더하고, 오른쪽
패널에서 고른 노드의 값을 고친다. 되돌리기는 그래프 전체를 찍어 두는 방식.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import hotkeys, prefs, runlog
from core.graph import Graph
from ui_qt import dialogs, node_view, theme as T
from ui_qt.editor_panels import DRAG_PREFIX, Inspector, Palette
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

        self.model = self._load()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())

        self.ng = node_view.make_graph_widget()
        self.made = node_view.populate(self.model, self.ng)
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
        self.ng.port_connected.connect(self._after_change)
        self.ng.port_disconnected.connect(self._after_change)
        self.ng.data_dropped.connect(self.drop_node)

        self._macro_shortcuts = []
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
        QShortcut(QKeySequence("Ctrl+F"), self, self.palette.focus_search)
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

    def _delete_selected_pipes(self) -> bool:
        """고른 연결선을 끊는다. 하나라도 끊었으면 True."""
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

        self._refresh_status()
        self.record_history()
        self._check_dirty()
        return True

    def delete_selected(self) -> None:
        # 선을 골랐으면 선만 끊는다
        if self._delete_selected_pipes():
            return

        selected = self.ng.selected_nodes()
        if not selected:
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
        ui = self.made.get(node.id)
        if ui is not None:
            node_view.refresh_card(ui, node)

        # 시작·종료의 단축키를 바꿨으면 버튼과 안내도 따라간다
        if key == "hotkey" and node.type in node_view.FIXED_TYPES:
            self.refresh_macro_keys()

        self.record_history()
        self._check_dirty()

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

        for shortcut in self._macro_shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._macro_shortcuts = []

        for key, action in ((run_key, self.run_macro), (stop_key, self.stop_macro)):
            sequence = hotkeys.qt_sequence(key)
            if not sequence:
                continue
            try:
                self._macro_shortcuts.append(QShortcut(QKeySequence(sequence), self, action))
            except Exception:
                pass

        # 실행·중지 키는 상단 버튼에 이미 적혀 있으므로 여기서 되풀이하지 않는다

    # ------------------------------------------------------------ 실행

    def run_macro(self) -> None:
        if self.runner.running:
            return

        problems = self.model.validate()
        if problems:
            dialogs.alert(self, "실행할 수 없음",
                          "먼저 아래 문제를 고쳐주세요.\n\n• " + "\n• ".join(problems[:6]))
            return

        # 실행 설정은 이 매크로(시작 노드)의 값을 쓴다
        settings = self.model.run_settings(prefs.load())
        _, stop_key = self.macro_keys()
        started = self.runner.start(
            self.model,
            step_delay=settings["step_delay"],
            mouse_move_duration=settings["mouse_move_duration"],
            bind_stop_hotkey=bool(stop_key),
            stop_hotkey=stop_key,
        )
        if not started:
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
        if self._active_node and self._active_node in self.made:
            self.made[self._active_node].view.running = False
            self.made[self._active_node].view.update()
        self._active_node = None

        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status.setText(describe(result))
        QTimer.singleShot(6000, self._refresh_status)

    # ------------------------------------------------------------ 선택

    def _on_selection(self, selected, deselected=None) -> None:
        """캔버스에서 고른 노드를 속성 패널에 보여준다."""
        nodes = selected if isinstance(selected, (list, tuple)) else []
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

        hint = QLabel("F 전체 보기 · Ctrl+Z 되돌리기 · "
                      "Ctrl+D 복제 · Del 삭제 · Ctrl+S 저장")
        hint.setObjectName("StatusBar")
        lay.addWidget(hint)
        return bar

    def _refresh_status(self) -> None:
        problems = self.model.validate()
        text = f"노드 {len(self.model.nodes)} · 연결 {len(self.model.edges)}"
        if problems:
            text += f"  ·  문제 {len(problems)}건"
        self.status.setText(text)

    # ------------------------------------------------------------ 창 조작

    def changeEvent(self, event):
        super().changeEvent(event)
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
            event.accept()
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
