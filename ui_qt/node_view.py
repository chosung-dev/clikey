# ui_qt/node_view.py
"""core.graph 그래프를 NodeGraphQt 캔버스에 그린다.

NodeGraphQt 기본 노드는 세로 모드에서 이름을 카드 밖에 그리고 본문이 빈
색 슬래브라, 시안의 카드 모양이 나오도록 QGraphicsItem 을 직접 그린다.
"""
from __future__ import annotations

import os
from typing import Dict

from NodeGraphQt import BaseNode, NodeGraph
from NodeGraphQt.constants import (
    LayoutDirectionEnum,
    PipeEnum,
    PipeLayoutEnum,
    ViewerEnum,
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.qgraphics.pipe import PipeItem
from NodeGraphQt.qgraphics.port import PortItem
from NodeGraphQt.widgets.viewer import NodeViewer
from Qt import QtCore, QtGui, QtWidgets

from core.graph import Graph
from ui_qt import theme as T

# ---------------------------------------------------------------- 노드 종류

CATEGORY = {
    "start": "flow", "stop": "flow",
    "mouse_click": "input", "mouse_move": "input",
    "mouse_down": "input", "mouse_up": "input",
    "key_press": "input", "key_down": "input", "key_up": "input",
    "delay": "wait",
    "image_match": "condition", "rgb_match": "condition",
    "loop": "loop",
}

#: 매크로마다 하나씩만 두고, 지울 수 없는 노드
FIXED_TYPES = ("start", "stop")

LABEL = {
    "start": "시작", "stop": "종료",
    "mouse_click": "마우스 클릭", "mouse_move": "마우스 이동",
    "mouse_down": "마우스 누르기", "mouse_up": "마우스 떼기",
    "key_press": "키 누르기", "key_down": "키 누르고 있기", "key_up": "키 떼기",
    "delay": "대기",
    "image_match": "이미지 있음", "rgb_match": "색상 일치",
    "loop": "반복",
}

def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


SKIN = {
    "input":     {"border": _rgb("#C5D3F0"), "accent": _rgb(T.ACCENT)},
    "wait":      {"border": _rgb("#D3D6DD"), "accent": _rgb("#6B7280")},
    "condition": {"border": _rgb("#EBD5AE"), "accent": _rgb("#C07818")},
    "loop":      {"border": _rgb("#D3C7EC"), "accent": _rgb("#7350B8")},
    "flow":      {"border": _rgb("#E8C4C1"), "accent": _rgb(T.DANGER)},
}

INK_RGB = _rgb(T.INK)
INK2_RGB = _rgb(T.INK_2)


# ---------------------------------------------------------------- 노드 카드


SNAP_DISTANCE = 8        # 이만큼 가까우면 달라붙는다 (씬 좌표)
GUIDE_REACH = 4000       # 안내선을 이 정도 길이로 그린다


class AlignGuides:
    """끌고 있는 노드가 다른 노드와 맞았을 때 보여주는 안내선.

    씬에 선 두 개(세로·가로)를 만들어두고 보였다 숨겼다 한다.
    """

    def __init__(self, scene):
        pen = QtGui.QPen(QtGui.QColor(*_rgb(T.ACCENT), 200), 0)
        pen.setStyle(QtCore.Qt.DashLine)

        self.lines = []
        for _ in range(2):
            line = QtWidgets.QGraphicsLineItem()
            line.setPen(pen)
            line.setZValue(10_000)
            line.setVisible(False)
            scene.addItem(line)
            self.lines.append(line)

    def show(self, vertical_x, horizontal_y, anchor):
        if vertical_x is None:
            self.lines[0].setVisible(False)
        else:
            self.lines[0].setLine(vertical_x, anchor.y() - GUIDE_REACH,
                                  vertical_x, anchor.y() + GUIDE_REACH)
            self.lines[0].setVisible(True)

        if horizontal_y is None:
            self.lines[1].setVisible(False)
        else:
            self.lines[1].setLine(anchor.x() - GUIDE_REACH, horizontal_y,
                                  anchor.x() + GUIDE_REACH, horizontal_y)
            self.lines[1].setVisible(True)

    def hide(self):
        for line in self.lines:
            line.setVisible(False)


def _guides(scene) -> AlignGuides:
    """씬마다 하나만 만들어 둔다."""
    found = getattr(scene, "_clikey_guides", None)
    if found is None:
        found = AlignGuides(scene)
        scene._clikey_guides = found
    return found


class ClikeyNodeItem(NodeItem):
    RADIUS = 10.0

    def __init__(self, name="node", parent=None):
        super().__init__(name, parent)
        self.title = name
        self.detail = ""
        self.accent = SKIN["wait"]["accent"]
        self.running = False                 # 실행 중 이 노드를 지나는 중
        self.text_item.setVisible(False)     # 내장 라벨은 카드 밖에 그려진다
        # 위치가 바뀔 때 알림을 받아야 끌면서 맞출 수 있다
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

    # ------------------------------------------------------------ 정렬 스냅

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self.scene():
            value = self._align(value)
        return super().itemChange(change, value)

    def _align(self, pos):
        """다른 노드의 변·중심과 가까우면 그 자리에 맞춘다."""
        rect = self.boundingRect()
        w, h = rect.width(), rect.height()

        # (내 기준선, 상대 기준선) 을 x·y 각각 비교한다
        mine_x = (pos.x(), pos.x() + w / 2, pos.x() + w)
        mine_y = (pos.y(), pos.y() + h / 2, pos.y() + h)

        best_x = best_y = None
        gap_x = gap_y = SNAP_DISTANCE + 1

        for other in self.scene().items():
            if other is self or not isinstance(other, ClikeyNodeItem):
                continue
            o_pos, o_rect = other.pos(), other.boundingRect()
            ow, oh = o_rect.width(), o_rect.height()

            for edge in (o_pos.x(), o_pos.x() + ow / 2, o_pos.x() + ow):
                for index, m in enumerate(mine_x):
                    gap = abs(m - edge)
                    if gap < gap_x:
                        gap_x, best_x = gap, (edge, index)

            for edge in (o_pos.y(), o_pos.y() + oh / 2, o_pos.y() + oh):
                for index, m in enumerate(mine_y):
                    gap = abs(m - edge)
                    if gap < gap_y:
                        gap_y, best_y = gap, (edge, index)

        guide_x = guide_y = None
        if best_x is not None:
            edge, index = best_x
            pos.setX(edge - (0, w / 2, w)[index])
            guide_x = edge
        if best_y is not None:
            edge, index = best_y
            pos.setY(edge - (0, h / 2, h)[index])
            guide_y = edge

        guides = _guides(self.scene())
        if guide_x is None and guide_y is None:
            guides.hide()
        else:
            guides.show(guide_x, guide_y,
                        QtCore.QPointF(pos.x() + w / 2, pos.y() + h / 2))
        return pos

    def mouseReleaseEvent(self, event):
        if self.scene():
            _guides(self.scene()).hide()
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        rect = self.boundingRect().adjusted(1.0, 1.0, -1.0, -1.0)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.setPen(QtCore.Qt.NoPen)
        painter.fillPath(path, QtGui.QColor(255, 255, 255))

        # 왼쪽 종류 색 띠
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(
            QtCore.QRectF(rect.left(), rect.top(), 6.0, rect.height()),
            QtGui.QColor(*self.accent),
        )
        painter.restore()

        if self.running:
            # 실행 중인 노드는 초록 테두리 + 바깥 발광으로 눈에 띄게
            glow = QtGui.QPainterPath()
            glow.addRoundedRect(
                self.boundingRect().adjusted(-2.5, -2.5, 2.5, 2.5),
                self.RADIUS + 2.5, self.RADIUS + 2.5)
            painter.setPen(QtGui.QPen(QtGui.QColor(*_rgb(T.RUN), 70), 3.0))
            painter.drawPath(glow)
            border = QtGui.QColor(*_rgb(T.RUN))
            weight = 2.0
        elif self.selected:
            border = QtGui.QColor(*_rgb(T.ACCENT))
            weight = 1.8
        else:
            border = QtGui.QColor(*self.border_color[:3])
            weight = 1.0

        painter.setPen(QtGui.QPen(border, weight))
        painter.drawPath(path)

        left = rect.left() + 16
        width = rect.width() - 24

        font = painter.font()
        font.setPointSizeF(9.5)
        font.setWeight(QtGui.QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(*INK_RGB))
        painter.drawText(
            QtCore.QRectF(left, rect.top() + 9, width, 18),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            self.title,
        )

        if self.detail:
            font.setPointSizeF(8.5)
            font.setWeight(QtGui.QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QtGui.QColor(*INK2_RGB))
            painter.drawText(
                QtCore.QRectF(left, rect.top() + 28, width, 16),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                self.detail,
            )

        painter.restore()


class ClikeyNode(BaseNode):
    __identifier__ = "clikey"
    NODE_NAME = "clikey"

    def __init__(self):
        super().__init__(qgraphics_item=ClikeyNodeItem)


# ---------------------------------------------------------------- 요약 문구


def summarize(node) -> str:
    p = node.params
    if node.type == "delay":
        return f"{p.get('seconds', 0)}초"
    if node.type == "image_match":
        return os.path.basename(str(p.get("template", "")))
    if node.type == "rgb_match":
        color = p.get("color")
        return f"RGB{tuple(color)}" if color else ""
    if node.type == "loop":
        limit = int(p.get("max", 0) or 0)
        return "무한 반복" if limit <= 0 else f"최대 {limit}회"
    if node.type in ("mouse_click", "mouse_move"):
        pos = p.get("pos") or {}
        x, y = pos.get("x"), pos.get("y")
        if isinstance(x, dict) or isinstance(y, dict):
            ref = (x if isinstance(x, dict) else y).get("ref")
            return f"@{ref} 좌표"
        return f"{x}, {y}"
    if node.type.startswith("key_"):
        return str(p.get("key", ""))
    if node.type in ("mouse_down", "mouse_up"):
        return "좌클릭" if p.get("button", "left") == "left" else "우클릭"
    return ""      # 시작·종료는 제목만으로 충분하다


# ---------------------------------------------------------------- 캔버스


def _tint_port(made_port, name: str) -> None:
    """포트 점도 같은 색으로 — 아직 잇지 않았을 때도 어느 쪽인지 알게."""
    tint = port_color(name)
    if tint is None or made_port is None:
        return
    try:
        made_port.view.color = tint
        made_port.view.border_color = tint
    except Exception:
        pass


def _theme_pipe_constants() -> None:
    """연결선 기본색·강조색을 시안 색으로.

    기본색은 초록이다 — 실행이 흘러가는 길이 곧 기본이고, 거기서 비껴가는
    갈래만 회색으로 물러난다.

    NodeGraphQt 는 이 값들을 Enum 상수에서 직접 읽는다. Enum 은 `.value` 대입을
    막으므로 내부 `_value_` 를 바꾼다. 기본 강조색(노랑)이 밝은 테마에서 튀어
    보여 어쩔 수 없이 쓰는 우회다.
    """
    for member, color in (
        (PipeEnum.COLOR, (*_rgb(T.RUN), 255)),
        (PipeEnum.HIGHLIGHT_COLOR, (*_rgb(T.ACCENT), 255)),
        (PipeEnum.ACTIVE_COLOR, (*_rgb(T.ACCENT), 255)),
    ):
        try:
            member._value_ = color
        except Exception:
            pass


# 되돌아가는 연결(목표가 출발보다 위) 을 옆으로 우회시킬 때 쓰는 값.
# 기준을 넉넉히 잡으면 촘촘히 붙여둔 앞방향 연결까지 우회해버리므로,
# 목표가 출발과 같은 높이이거나 위일 때만으로 좁힌다.
BACK_MIN_DROP = 12        # 목표가 이보다 아래면 평범한 앞방향 연결
BACK_STUB = 26            # 포트에서 곧장 빠져나오는 길이
BACK_LANE_GAP = 70        # 노드 오른쪽 바깥으로 비켜나는 거리
BACK_CORNER = 10          # 모서리를 둥글리는 반지름


def _rounded_polyline(path, points, radius: float) -> None:
    """직각으로 꺾이는 선을 모서리만 둥글려 그린다."""
    path.moveTo(points[0])
    for index in range(1, len(points) - 1):
        prev, corner, nxt = points[index - 1], points[index], points[index + 1]

        def pull(a, b):
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
            step = min(radius, length / 2)
            return QtCore.QPointF(a.x() + dx / length * step,
                                  a.y() + dy / length * step)

        path.lineTo(pull(corner, prev))
        path.quadTo(corner, pull(corner, nxt))
    path.lineTo(points[-1])


def _install_back_edge_routing() -> None:
    """되돌아가는 연결을 옆으로 우회시켜 그린다.

    NodeGraphQt 의 세로 각진 라우팅은 목표가 출발보다 아래에 있다고 가정한다.
    되돌아가는 연결에서는 아래로 내려갔다 위로 올라오는 경로가 나와 그래프
    전체를 가로지른다. 그런 경우만 가로채 오른쪽 여백으로 돌린다.
    """
    if getattr(PipeItem, "_clikey_back_routing", False):
        return

    original = PipeItem.draw_path

    def center_of(port):
        spot = port.scenePos()
        rect = port.boundingRect()
        return QtCore.QPointF(spot.x() + rect.width() / 2,
                              spot.y() + rect.height() / 2)

    def draw_path(self, start_port, end_port=None, cursor_pos=None):
        out_port, in_port = self.output_port, self.input_port
        vertical = self.viewer_layout_direction() == LayoutDirectionEnum.VERTICAL.value

        # 끌고 있는 임시 선, 가로 배치, 한쪽 포트가 없는 경우는 원래대로
        if cursor_pos or not vertical or out_port is None or in_port is None:
            return original(self, start_port, end_port, cursor_pos)

        source, target = center_of(out_port), center_of(in_port)
        if target.y() > source.y() + BACK_MIN_DROP:
            return original(self, start_port, end_port, cursor_pos)

        out_node, in_node = out_port.node, in_port.node
        lane = max(out_node.scenePos().x() + out_node.boundingRect().width(),
                   in_node.scenePos().x() + in_node.boundingRect().width()) + BACK_LANE_GAP

        points = [
            source,
            QtCore.QPointF(source.x(), source.y() + BACK_STUB),
            QtCore.QPointF(lane, source.y() + BACK_STUB),
            QtCore.QPointF(lane, target.y() - BACK_STUB),
            QtCore.QPointF(target.x(), target.y() - BACK_STUB),
            target,
        ]

        path = QtGui.QPainterPath()
        _rounded_polyline(path, points, BACK_CORNER)
        self.setPath(path)
        self._draw_direction_pointer()

    PipeItem.draw_path = draw_path
    PipeItem._clikey_back_routing = True


#: 일이 이어지는 길은 모두 초록(기본색)이고, 비껴가는 갈래만 회색이다.
#: 예전에 붙여 두었던 "참"/"거짓" 글자를 뺀 뒤로 둘이 구분되지 않았다.
#: 여기 없는 포트(다음 · 참 · 반복 · 완료)는 기본색을 그대로 쓴다.
PORT_COLORS = {
    "false": T.INK_3,
}


def port_color(name: str):
    """포트 이름에 맞는 (r, g, b, a). 갈래가 하나뿐인 포트는 None."""
    hex_color = PORT_COLORS.get(name)
    return (*_rgb(hex_color), 255) if hex_color else None


def _install_port_colors() -> None:
    """연결선을 출발한 포트 색으로 그린다.

    NodeGraphQt 는 모든 선을 한 색으로 그려서, 조건 노드의 참·거짓 두 선이
    똑같이 보였다. 어느 쪽이 참인지 보드에서 알 수 없다.
    """
    if getattr(PipeItem, "_clikey_port_colors", False):
        return

    def resolved(self):
        out = self.output_port
        tinted = port_color(out.name) if out is not None else None
        return tinted or self._color

    PipeItem.color = property(resolved, lambda self, value: setattr(self, "_color", value))

    original = PipeItem.draw_path

    def draw_path(self, start_port, end_port=None, cursor_pos=None):
        original(self, start_port, end_port, cursor_pos)
        # 고르거나 실행 중일 때의 색은 건드리지 않는다
        if not (self._active or self._highlight):
            self.set_pipe_styling(color=self.color, width=2, style=self.style)

    PipeItem.draw_path = draw_path
    PipeItem._clikey_port_colors = True


def _hide_pipe_arrows() -> None:
    """연결선 가운데 화살표를 없앤다.

    흐름은 세로 배치와 포트 위치(위=입력, 아래=출력)로 이미 읽히고,
    노드가 늘어나면 화살표가 시끄럽다. NodeGraphQt 에 끄는 설정이 없어
    화살표를 그리는 함수를 숨기기만 하도록 바꾼다.
    """
    if getattr(PipeItem, "_clikey_no_arrow", False):
        return

    def no_arrow(self):
        self._dir_pointer.setVisible(False)

    PipeItem._draw_direction_pointer = no_arrow
    PipeItem._clikey_no_arrow = True


def _click_only_selects_pipes() -> None:
    """연결선을 누르면 고르기만 한다.

    NodeGraphQt 는 선을 누르면 가까운 쪽 절반을 판단해 그 끝을 잡아 떼고
    다시 잇게 해준다. 선을 지우거나 살펴보려고 눌렀을 때도 연결이 끊겨
    헷갈린다. 그래서 선을 눌렀을 때는 원래 처리를 건너뛴다 — 고르는 일은
    그 뒤에 이어 도는 Qt 기본 처리가 알아서 한다.

    다시 이으려면 노드의 포트에서 끌어다 놓으면 된다.
    """
    if getattr(NodeViewer, "_clikey_pipe_click_only", False):
        return

    original = NodeViewer.sceneMousePressEvent

    def pipe_at(viewer, pos):
        """그 자리에 노드·포트 없이 선만 있는가."""
        for item in viewer._items_near(pos, None, 5, 5):
            if isinstance(item, (AbstractNodeItem, PortItem)):
                return None
            if isinstance(item, PipeItem):
                return item
        return None

    def patched(self, event):
        # 선 자르기(Alt+Shift)·화면 밀기(Alt)·이어 그리는 중일 때는 건드리지 않는다
        busy = self.ALT_state or self._LIVE_PIPE.isVisible()
        if not busy and pipe_at(self, event.scenePos()) is not None:
            return
        return original(self, event)

    NodeViewer.sceneMousePressEvent = patched
    NodeViewer._clikey_pipe_click_only = True


UNDO_KEYS = {"Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z", "Alt+Backspace",
             "Alt+Shift+Backspace"}


def _drop_builtin_undo_shortcuts(viewer) -> None:
    """NodeGraphQt 가 뷰어에 달아둔 Undo/Redo 액션의 단축키를 뗀다.

    그대로 두면 편집기 쪽 되돌리기와 같은 키를 다투게 되고, Qt 는 이런 경우
    '모호함'으로 보고 **양쪽 다 실행하지 않는다**. 게다가 NodeGraphQt 의
    undo 스택에는 선택 변경까지 쌓여서 우리 모델과 어긋난다.
    """
    from PySide6.QtGui import QAction, QKeySequence

    for action in viewer.findChildren(QAction):
        if {s.toString() for s in action.shortcuts()} & UNDO_KEYS:
            action.setShortcuts([QKeySequence()])
            action.setEnabled(False)


def make_graph_widget() -> NodeGraph:
    _theme_pipe_constants()
    _hide_pipe_arrows()
    _install_back_edge_routing()
    _install_port_colors()
    _click_only_selects_pipes()

    ng = NodeGraph(layout_direction=LayoutDirectionEnum.VERTICAL.value)

    # Clikey 그래프는 되돌아가는 반복(재시도, 반복 노드)이 핵심이라 순환을 허용해야
    # 한다. NodeGraphQt 는 기본이 비순환이고, 걸리면 연결을 조용히 거부한다.
    ng.set_acyclic(False)

    ng.set_pipe_style(PipeLayoutEnum.ANGLE.value)
    ng.set_grid_mode(ViewerEnum.GRID_DISPLAY_DOTS.value)
    ng.set_background_color(*_rgb(T.CANVAS))
    ng.set_grid_color(*_rgb("#D3D6DD"))
    ng.register_node(ClikeyNode)

    # 뷰어는 QGraphicsView — 기본 테두리를 지운다
    viewer = ng.viewer()
    viewer.setFrameShape(QtWidgets.QFrame.NoFrame)
    viewer.setFrameShadow(QtWidgets.QFrame.Plain)
    viewer.setLineWidth(0)
    _drop_builtin_undo_shortcuts(viewer)
    return ng


def populate(model: Graph, ng: NodeGraph) -> Dict[str, object]:
    """모델을 캔버스에 그리고 {모델 노드 id: 화면 노드} 를 돌려준다."""
    made = {}

    for node_id, node in model.nodes.items():
        ui = ng.create_node(
            "clikey.ClikeyNode",
            name=node_id,                       # NodeGraphQt 는 이름 중복을 못 견딘다
            pos=model.layout.get(node_id, [0, 0]),
            push_undo=False,
        )
        ui.view.title = node.name or LABEL.get(node.type, node.type)
        ui.view.detail = summarize(node)

        if node.type != "start":
            ui.add_input("in", multi_input=True, display_name=False)
        for port in node.ports:
            # 출력 하나에서 갈 수 있는 다음 노드는 하나뿐이다. 다중 연결을 허용하면
            # 화면에는 선이 둘 그려지는데 실행은 하나만 따라가 조용히 어긋난다.
            made_port = ui.add_output(port, display_name=False, multi_output=False)
            _tint_port(made_port, port)

        skin = SKIN[CATEGORY.get(node.type, "wait")]
        ui.view.border_color = (*skin["border"], 255)
        ui.view.accent = skin["accent"]

        made[node_id] = ui

    for edge in model.edges:
        src, dst = made.get(edge.src), made.get(edge.dst)
        if not src or not dst:
            continue
        try:
            src.get_output(edge.port).connect_to(dst.get_input("in"), push_undo=False)
        except Exception:
            pass

    return made


def read_edges(made: Dict[str, object]) -> list:
    """캔버스에 그려진 연결을 모델 엣지로 되읽는다.

    사용자가 포트를 끌어 연결하거나 끊을 수 있으므로, 모델의 엣지는 저장 직전에
    캔버스에서 다시 만든다.
    """
    from core.graph.model import Edge

    by_ui_name = {ui.name(): node_id for node_id, ui in made.items()}
    edges = []

    for node_id, ui in made.items():
        for port_name, port in ui.outputs().items():
            for target in port.connected_ports():
                target_id = by_ui_name.get(target.node().name())
                if target_id:
                    edges.append(Edge(src=node_id, dst=target_id, port=port_name))

    edges.sort(key=lambda e: (e.src, e.port, e.dst))
    return edges


def add_node(model_node, ng: NodeGraph, pos) -> object:
    """모델 노드 하나를 캔버스에 올린다."""
    ui = ng.create_node(
        "clikey.ClikeyNode",
        name=model_node.id,
        pos=[round(pos[0]), round(pos[1])],
        push_undo=False,
    )
    ui.view.title = model_node.name or LABEL.get(model_node.type, model_node.type)
    ui.view.detail = summarize(model_node)

    if model_node.type != "start":
        ui.add_input("in", multi_input=True, display_name=False)
    for port in model_node.ports:
        ui.add_output(port, display_name=False)

    skin = SKIN[CATEGORY.get(model_node.type, "wait")]
    ui.view.border_color = (*skin["border"], 255)
    ui.view.accent = skin["accent"]
    return ui


def refresh_card(ui, model_node) -> None:
    """파라미터가 바뀌었을 때 카드의 요약 문구를 갱신."""
    ui.view.title = model_node.name or LABEL.get(model_node.type, model_node.type)
    ui.view.detail = summarize(model_node)
    ui.view.update()


def read_layout(made: Dict[str, object]) -> Dict[str, list]:
    """화면에서 옮긴 노드 위치를 모델 좌표로 되읽는다."""
    layout = {}
    for node_id, ui in made.items():
        try:
            x, y = ui.pos()
            layout[node_id] = [round(x), round(y)]
        except Exception:
            pass
    return layout
