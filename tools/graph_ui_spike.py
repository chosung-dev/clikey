"""3-C 스파이크: core.graph 의 그래프를 NodeGraphQt 노드 편집기에 띄운다.

    .venv\\Scripts\\python.exe tools/graph_ui_spike.py
    .venv\\Scripts\\python.exe tools/graph_ui_spike.py --shot out.png

확인하려는 것:
  1. NodeGraphQt 가 PySide6 에서 뜨는가
  2. core.graph 모델을 그대로 노드/연결로 옮길 수 있는가
  3. 참/거짓 두 갈래와 되돌아가는 연결이 표현되는가
  4. 시안의 밝은 테마로 칠할 수 있는가
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Qt import QtCore, QtGui, QtWidgets  # noqa: E402  (NodeGraphQt 가 쓰는 셔틀)
from NodeGraphQt import BaseNode, NodeGraph  # noqa: E402
from NodeGraphQt.qgraphics.node_base import NodeItem  # noqa: E402
from NodeGraphQt.constants import (  # noqa: E402
    LayoutDirectionEnum,
    PipeEnum,
    PipeLayoutEnum,
    ViewerEnum,
)

from core.graph import Graph  # noqa: E402


# ---------------------------------------------------------------- 시안 색

INK = (27, 30, 35)
# 시안의 "노드 종류별 색" — 칩 / 테두리 / 아이콘(=왼쪽 띠)
PALETTE = {
    "input":     {"body": (237, 241, 251), "border": (197, 211, 240), "accent": (58, 91, 199)},
    "wait":      {"body": (241, 242, 245), "border": (211, 214, 221), "accent": (107, 114, 128)},
    "condition": {"body": (251, 243, 227), "border": (235, 213, 174), "accent": (192, 120, 24)},
    "loop":      {"body": (241, 236, 250), "border": (211, 199, 236), "accent": (115, 80, 184)},
    "flow":      {"body": (247, 231, 230), "border": (232, 196, 193), "accent": (196, 69, 61)},
}

CATEGORY = {
    "start": "flow", "stop": "flow",
    "mouse_click": "input", "mouse_move": "input",
    "mouse_down": "input", "mouse_up": "input",
    "key_press": "input", "key_down": "input", "key_up": "input",
    "delay": "wait",
    "image_match": "condition", "rgb_match": "condition",
    "loop": "loop",
}

LABEL = {
    "start": "시작", "stop": "매크로 중지",
    "mouse_click": "마우스 클릭", "mouse_move": "마우스 이동",
    "mouse_down": "마우스 누르기", "mouse_up": "마우스 떼기",
    "key_press": "키 누르기", "key_down": "키 누르고 있기", "key_up": "키 떼기",
    "delay": "대기",
    "image_match": "이미지 있음", "rgb_match": "색상 일치",
    "loop": "반복",
}

PORT_LABEL = {"next": "", "true": "참", "false": "거짓", "loop": "반복", "done": "빠져나감"}


# ---------------------------------------------------------------- 노드 클래스

class ClikeyNodeItem(NodeItem):
    """시안대로 직접 그리는 노드 카드 — 둥근 모서리, 제목, 파라미터 한 줄."""

    RADIUS = 10.0

    def __init__(self, name="node", parent=None):
        super().__init__(name, parent)
        self.title = name
        self.detail = ""
        self.accent = (107, 114, 128)
        # 내장 이름 라벨은 카드 밖에 그려지므로 끄고 직접 그린다
        self.text_item.setVisible(False)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        rect = self.boundingRect().adjusted(1.0, 1.0, -1.0, -1.0)
        border = QtGui.QColor(*self.border_color)
        if self.selected:
            border = QtGui.QColor(58, 91, 199)      # 선택 시 강조 #3A5BC7

        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.setPen(QtCore.Qt.NoPen)
        painter.fillPath(path, QtGui.QColor(255, 255, 255))          # 카드 바탕

        # 왼쪽 종류 색 띠 — 시안의 아이콘 칩 자리를 대신한다
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(
            QtCore.QRectF(rect.left(), rect.top(), 6.0, rect.height()),
            QtGui.QColor(*self.accent),
        )
        painter.restore()

        painter.setPen(QtGui.QPen(border, 1.6 if self.selected else 1.0))
        painter.drawPath(path)

        text_left = rect.left() + 16
        text_w = rect.width() - 24

        title_font = painter.font()
        title_font.setPointSizeF(9.5)
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QtGui.QColor(*INK))
        painter.drawText(
            QtCore.QRectF(text_left, rect.top() + 9, text_w, 18),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            self.title,
        )

        if self.detail:
            detail_font = painter.font()
            detail_font.setPointSizeF(8.5)
            detail_font.setWeight(QtGui.QFont.Weight.Normal)
            painter.setFont(detail_font)
            painter.setPen(QtGui.QColor(90, 97, 109))                # 보조 #5A616D
            painter.drawText(
                QtCore.QRectF(text_left, rect.top() + 28, text_w, 16),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                self.detail,
            )

        painter.restore()


class ClikeyNode(BaseNode):
    """core.graph 노드 하나에 대응. 포트 구성은 생성 후 붙인다."""
    __identifier__ = "clikey"
    NODE_NAME = "clikey"

    def __init__(self):
        super().__init__(qgraphics_item=ClikeyNodeItem)


def summarize(node) -> str:
    """노드 파라미터를 한 줄로."""
    p = node.params
    if node.type == "delay":
        return f"{p.get('seconds', 0)}초"
    if node.type == "image_match":
        return os.path.basename(str(p.get("template", "")))
    if node.type == "rgb_match":
        color = p.get("color")
        return f"RGB{tuple(color)}" if color else ""
    if node.type == "loop":
        m = int(p.get("max", 0) or 0)
        return "무한" if m <= 0 else f"최대 {m}회"
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
        return str(p.get("button", "left"))
    return ""


def build_ui_graph(model: Graph, ng: NodeGraph):
    """core.graph.Graph -> NodeGraphQt 화면 노드."""
    ng.register_node(ClikeyNode)
    made = {}

    for node_id, node in model.nodes.items():
        title = node.name or LABEL.get(node.type, node.type)
        detail = summarize(node)

        ui = ng.create_node(
            "clikey.ClikeyNode",
            name=node_id,                       # NodeGraphQt 는 이름 중복을 못 견딘다
            pos=model.layout.get(node_id, [0, 0]),
            push_undo=False,
        )
        ui.view.title = title                   # 화면에 그릴 제목은 따로 준다
        ui.view.detail = detail

        if node.type != "start":
            ui.add_input("in", multi_input=True, display_name=False)
        for port in node.ports:
            # 시안대로 포트 이름은 감춘다 — 참/거짓은 위치로 읽는다
            ui.add_output(port, display_name=False)

        skin = PALETTE[CATEGORY.get(node.type, "wait")]
        ui.set_color(*skin["body"])
        # 글자색/테두리색은 BaseNode 가 아니라 뷰(QGraphicsItem)에 있다
        ui.view.text_color = (*INK, 255)
        ui.view.border_color = (*skin["border"], 255)
        ui.view.accent = skin["accent"]

        made[node_id] = ui

    for edge in model.edges:
        src, dst = made.get(edge.src), made.get(edge.dst)
        if not src or not dst:
            continue
        try:
            src.get_output(edge.port).connect_to(dst.get_input("in"), push_undo=False)
        except Exception as exc:
            print(f"  연결 실패 {edge.src}--{edge.port}-->{edge.dst}: {exc}")

    return made


# ---------------------------------------------------------------- 예제 그래프

def demo_graph() -> Graph:
    """시안과 같은 흐름 — 로그인 자동화."""
    g = Graph()

    g.add_node("start", node_id="n1")
    g.add_node("image_match", {"template": "로그인_버튼.png"}, node_id="n2")
    g.add_node("mouse_click", {"button": "left",
                               "pos": {"x": {"ref": "n2"}, "y": {"ref": "n2"}}}, node_id="n3")
    g.add_node("delay", {"seconds": 0.3}, node_id="n4")
    g.add_node("rgb_match", {"pos": {"x": 1204, "y": 88},
                             "color": [232, 69, 60]}, node_id="n5")
    g.add_node("stop", node_id="n6")
    g.add_node("delay", {"seconds": 0.5}, node_id="n7")
    g.add_node("key_press", {"key": "esc"}, node_id="n8")

    g.connect("n1", "n2")
    g.connect("n2", "n3", "true")
    g.connect("n2", "n7", "false")
    g.connect("n7", "n2")             # 되돌아가기
    g.connect("n3", "n4")
    g.connect("n4", "n5")
    g.connect("n5", "n6", "true")
    g.connect("n5", "n8", "false")
    g.connect("n8", "n2")             # 되돌아가기

    g.layout.update({
        "n1": [0, 0],
        "n2": [0, 130],
        "n3": [0, 300],
        "n4": [0, 430],
        "n5": [0, 560],
        "n6": [0, 730],
        "n7": [400, 300],
        "n8": [400, 560],
    })
    return g


# ---------------------------------------------------------------- 실행

def main():
    shot = None
    if "--shot" in sys.argv:
        shot = sys.argv[sys.argv.index("--shot") + 1]

    model = demo_graph()
    problems = model.validate()
    print(f"모델 검사: {'문제 없음' if not problems else problems}")

    app = QtWidgets.QApplication(sys.argv)

    ng = NodeGraph(layout_direction=LayoutDirectionEnum.VERTICAL.value)
    ng.set_pipe_style(PipeLayoutEnum.ANGLE.value)        # 시안의 직각 연결선
    ng.set_grid_mode(ViewerEnum.GRID_DISPLAY_DOTS.value)
    ng.set_background_color(239, 240, 243)
    ng.set_grid_color(211, 214, 221)

    made = build_ui_graph(model, ng)
    print(f"화면 노드 {len(made)}개 · 연결 {len(model.edges)}개")

    # 연결선 색은 enum 상수를 못 바꾸므로 만들어진 파이프에 직접 준다
    for pipe in ng.viewer().all_pipes():
        pipe.color = (169, 174, 185, 255)      # 시안 #A9AEB9
        pipe.update()

    widget = ng.widget
    widget.setWindowTitle("Clikey — 노드 편집기 스파이크")
    widget.resize(1280, 820)
    widget.show()

    ng.select_all()
    ng.fit_to_selection()
    ng.clear_selection()

    if shot:
        def capture():
            widget.grab().save(shot)
            print(f"스크린샷 저장: {shot}")
            app.quit()
        QtCore.QTimer.singleShot(1500, capture)

    return app.exec_() if hasattr(app, "exec_") else app.exec()


if __name__ == "__main__":
    sys.exit(main())
