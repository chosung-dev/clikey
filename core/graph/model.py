# core/graph/model.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json
import uuid

#: 2 부터 ask 노드가 들어간다. 올려두지 않으면 구버전 앱이 ask 를 모르는
#: 노드로 보고 조용히 건너뛴다(engine._execute) — 판단을 빼먹고 아무 답이나
#: 누른 것처럼 진행하므로, 읽지 못하게 막는 편이 안전하다.
SCHEMA_VERSION = 2

# 노드 종류 -> 출력 포트. 빈 튜플이면 흐름이 여기서 끝난다.
NODE_PORTS: Dict[str, Tuple[str, ...]] = {
    "start": ("next",),
    "stop": (),

    "mouse_click": ("next",),
    "mouse_move": ("next",),
    "mouse_down": ("next",),
    "mouse_up": ("next",),

    "key_press": ("next",),
    "key_down": ("next",),
    "key_up": ("next",),

    "delay": ("next",),
    "notify": ("next",),

    "image_match": ("true", "false"),
    "rgb_match": ("true", "false"),

    "loop": ("loop", "done"),

    # ask 의 출력은 params["choices"] 에서 나온다(Node.ports). 여기 빈 튜플은
    # validate 의 "알 수 없는 노드 종류" 검사를 통과시키기 위한 자리다.
    "ask": (),
    "ai_point": ("찾음", "못 찾음"),
}

# 좌표를 찾아 뒤쪽 노드가 참조할 수 있게 남기는 노드들
LOCATING_TYPES = frozenset({"image_match", "rgb_match", "ai_point"})
CONDITION_TYPES = frozenset({"image_match", "rgb_match", "ai_point"})

#: 출력 포트가 파라미터에서 나오는 노드들. 선택지 하나가 곧 포트 하나다.
CHOICE_TYPES = frozenset({"ask"})

#: 판단을 밖에 맡기는 노드들. 하나라도 있으면 Clikey 안에서는 돌 수 없다.
AI_TYPES = frozenset({"ask", "ai_point"})

#: 화면 그림을 보낼 때 줄어들지 않는 한계 (Claude 4.7 이후 기준).
#: 28x28 픽셀 한 칸이 비주얼 토큰 하나이고, 긴 변과 칸 수 둘 다 넘지 않아야
#: 원본 그대로 전달된다. 줄어들면 글씨가 뭉개져 짚는 자리가 흔들린다.
VISION_MAX_EDGE = 2576
VISION_MAX_TOKENS = 4784
VISION_PATCH = 28


def vision_tokens(width: int, height: int) -> int:
    """그림 하나가 차지하는 비주얼 토큰 수."""
    return (-(-int(width) // VISION_PATCH)) * (-(-int(height) // VISION_PATCH))


def region_problem(region: Any) -> str:
    """영역이 그대로 전달될 수 있는지. 문제가 없으면 빈 문자열."""
    if not (isinstance(region, (list, tuple)) and len(region) == 4):
        return "보낼 화면 범위를 지정해야 합니다."

    x1, y1, x2, y2 = (int(v) for v in region)
    width, height = x2 - x1, y2 - y1
    if width <= 0 or height <= 0:
        return "보낼 화면 범위가 비어 있습니다."

    if max(width, height) > VISION_MAX_EDGE:
        return (f"범위의 긴 변이 {max(width, height)}px 입니다. "
                f"{VISION_MAX_EDGE}px 이하로 줄여주세요.")

    tokens = vision_tokens(width, height)
    if tokens > VISION_MAX_TOKENS:
        return (f"범위가 너무 넓습니다 ({width}×{height}, {tokens}토큰). "
                f"{VISION_MAX_TOKENS}토큰 이하가 되게 줄여주세요.")
    return ""


def new_id() -> str:
    return "n" + uuid.uuid4().hex[:8]


def choice_ports(choices: Any) -> Tuple[str, ...]:
    """선택지 목록을 출력 포트 이름으로. 빈 것과 겹치는 것은 걸러낸다.

    겹친 이름을 그대로 두면 포트가 하나로 합쳐져 나중 것이 사라진다. 여기서
    미리 접어두고, 사용자에게는 `validate` 가 따로 알린다.
    """
    ports: List[str] = []
    for choice in (choices or ()):
        name = str(choice).strip()
        if name and name not in ports:
            ports.append(name)
    return tuple(ports)


# ---------------------------------------------------------------- 좌표

def resolve_axis(value: Any, coords: Dict[str, Tuple[int, int]], axis: str) -> Optional[int]:
    """좌표 한 축을 푼다. 정수이거나 {"ref": 노드id} 형태."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        ref = value.get("ref")
        found = coords.get(ref) if ref else None
        if found is None:
            return None
        return found[0] if axis == "x" else found[1]
    return None


def resolve_pos(pos: Any, coords: Dict[str, Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """{"x": ..., "y": ...} 를 실제 좌표로. 풀 수 없으면 None."""
    if not isinstance(pos, dict):
        return None
    x = resolve_axis(pos.get("x"), coords, "x")
    y = resolve_axis(pos.get("y"), coords, "y")
    if x is None or y is None:
        return None
    return x, y


def _axis_ref(value: Any) -> Optional[str]:
    return value.get("ref") if isinstance(value, dict) else None


# ---------------------------------------------------------------- 노드 / 엣지

@dataclass
class Node:
    id: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    name: str = ""

    @property
    def ports(self) -> Tuple[str, ...]:
        if self.type in CHOICE_TYPES:
            return choice_ports(self.params.get("choices"))
        return NODE_PORTS.get(self.type, ())

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"type": self.type}
        if self.name:
            data["name"] = self.name
        data.update(self.params)
        return data

    @classmethod
    def from_dict(cls, node_id: str, data: Dict[str, Any]) -> Node:
        params = {k: v for k, v in data.items() if k not in ("type", "name")}
        return cls(
            id=node_id,
            type=data.get("type", ""),
            params=params,
            name=data.get("name", ""),
        )


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    port: str = "next"

    def to_dict(self) -> Dict[str, Any]:
        data = {"from": self.src, "to": self.dst}
        if self.port != "next":
            data["port"] = self.port
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Edge:
        return cls(
            src=data.get("from", ""),
            dst=data.get("to", ""),
            port=data.get("port", "next"),
        )


# ---------------------------------------------------------------- 그래프

@dataclass
class Graph:
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    entry: Optional[str] = None
    layout: Dict[str, List[int]] = field(default_factory=dict)
    #: 꺼두면 목록에서 단축키를 걸지 않는다. 지우지 않고 잠시 쉬게 할 때 쓴다.
    enabled: bool = True

    def __post_init__(self):
        self._index: Dict[Tuple[str, str], str] = {}
        self.reindex()

    def reindex(self) -> None:
        """(노드, 포트) -> 다음 노드. 같은 포트에 엣지가 둘이면 처음 것만 쓴다."""
        index: Dict[Tuple[str, str], str] = {}
        for edge in self.edges:
            index.setdefault((edge.src, edge.port), edge.dst)
        self._index = index

    def next_id(self, node_id: str, port: str) -> Optional[str]:
        return self._index.get((node_id, port))

    def node(self, node_id: Optional[str]) -> Optional[Node]:
        return self.nodes.get(node_id) if node_id else None

    # ------------------------------------------------------------ 편집

    def add_node(self, type: str, params: Optional[Dict[str, Any]] = None,
                 name: str = "", node_id: Optional[str] = None) -> Node:
        node = Node(id=node_id or new_id(), type=type, params=dict(params or {}), name=name)
        self.nodes[node.id] = node
        if self.entry is None and type == "start":
            self.entry = node.id
        return node

    def connect(self, src: str, dst: str, port: str = "next") -> Edge:
        edge = Edge(src=src, dst=dst, port=port)
        self.edges = [e for e in self.edges if not (e.src == src and e.port == port)]
        self.edges.append(edge)
        self.reindex()
        return edge

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.layout.pop(node_id, None)
        self.edges = [e for e in self.edges if e.src != node_id and e.dst != node_id]
        if self.entry == node_id:
            self.entry = None
        self.reindex()

    # ------------------------------------------------------------ 실행 설정

    def start_node(self) -> Optional[Node]:
        node = self.node(self.entry)
        if node is not None and node.type == "start":
            return node
        return next((n for n in self.nodes.values() if n.type == "start"), None)

    def run_settings(self, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """매크로마다 갖는 실행 설정. 시작 노드에 적혀 있다.

        예전에 만든 파일에는 없으므로 `fallback`(앱 기본값)으로 메운다.
        """
        fallback = fallback or {}
        node = self.start_node()
        params = node.params if node is not None else {}

        def pick(key: str, default: float) -> float:
            for source in (params, fallback):
                if key in source:
                    try:
                        return max(0.0, float(source[key]))
                    except (TypeError, ValueError):
                        pass
            return default

        return {
            "step_delay": pick("step_delay", 0.03),
            "mouse_move_duration": pick("mouse_move_duration", 0.0),
        }

    # ------------------------------------------------------------ 검사

    def validate(self) -> List[str]:
        """치명적인 문제만 문자열로 모아 반환. 빈 리스트면 실행 가능."""
        problems: List[str] = []

        if not self.entry:
            problems.append("시작 노드가 없습니다.")
        elif self.entry not in self.nodes:
            problems.append(f"시작 노드 '{self.entry}' 를 찾을 수 없습니다.")

        for node_id, node in self.nodes.items():
            if node.type not in NODE_PORTS:
                problems.append(f"{node_id}: 알 수 없는 노드 종류 '{node.type}'")
                continue

            if node.type in CHOICE_TYPES:
                problems.extend(self._choice_problems(node_id, node))
            if node.type == "ai_point":
                problems.extend(self._point_problems(node_id, node))
            for key in ("pos",):
                ref_ids = [
                    r for r in (_axis_ref(node.params.get(key, {}).get(axis))
                                for axis in ("x", "y")
                                if isinstance(node.params.get(key), dict))
                    if r
                ]
                for ref in ref_ids:
                    if ref not in self.nodes:
                        problems.append(f"{node_id}: 없는 노드 '{ref}' 의 좌표를 참조합니다.")
                    elif self.nodes[ref].type not in LOCATING_TYPES:
                        problems.append(f"{node_id}: '{ref}' 는 좌표를 남기지 않는 노드입니다.")

        seen_ports = set()
        for edge in self.edges:
            if edge.src not in self.nodes:
                problems.append(f"연결의 출발 노드 '{edge.src}' 가 없습니다.")
                continue
            if edge.dst not in self.nodes:
                problems.append(f"연결의 도착 노드 '{edge.dst}' 가 없습니다.")
            allowed = self.nodes[edge.src].ports
            if edge.port not in allowed:
                label = ", ".join(allowed) if allowed else "없음"
                problems.append(
                    f"{edge.src}: '{edge.port}' 출력이 없습니다. (가능: {label})"
                )

            # 출력 하나에서 두 곳으로 가면 실행은 한 곳만 따라간다 — 조용히
            # 어긋나므로 문제로 알린다.
            key = (edge.src, edge.port)
            if key in seen_ports:
                problems.append(
                    f"{edge.src}: '{edge.port}' 출력이 여러 노드에 연결돼 있습니다."
                )
            seen_ports.add(key)

        return problems

    @staticmethod
    def _choice_problems(node_id: str, node: Node) -> List[str]:
        """선택지가 포트가 되므로 비거나 겹치면 흐름이 끊긴다."""
        problems: List[str] = []
        raw = [str(c).strip() for c in (node.params.get("choices") or ())]
        kept = [c for c in raw if c]

        if len(kept) < 2:
            problems.append(f"{node_id}: 선택지가 둘 이상 있어야 합니다.")
        if len(set(kept)) != len(kept):
            dupes = sorted({c for c in kept if kept.count(c) > 1})
            problems.append(
                f"{node_id}: 선택지 이름이 겹칩니다 ({', '.join(dupes)})."
            )
        if not str(node.params.get("prompt") or "").strip():
            problems.append(f"{node_id}: 판단 요청 내용이 비어 있습니다.")
        return problems

    @staticmethod
    def _point_problems(node_id: str, node: Node) -> List[str]:
        """짚어야 할 자리를 찾는 노드는 범위가 반드시 있어야 한다.

        화면 전체를 보내면 그림이 줄어들어 글씨가 뭉개지고, 짚은 자리도 그만큼
        흔들린다. 좁혀야 정확해진다.
        """
        problems: List[str] = []
        trouble = region_problem(node.params.get("region"))
        if trouble:
            problems.append(f"{node_id}: {trouble}")
        if not str(node.params.get("prompt") or "").strip():
            problems.append(f"{node_id}: 무엇을 찾을지 적어야 합니다.")
        return problems

    @property
    def mcp_only(self) -> bool:
        """판단을 구할 상대가 있어야 도는 매크로.

        `validate` 에 넣지 않는다 — 그건 "고장난 매크로" 라는 뜻이 된다. 이것은
        고장이 아니라 실행 경로가 다른 매크로다.
        """
        return any(n.type in AI_TYPES for n in self.nodes.values())

    def unreachable_ids(self) -> List[str]:
        """시작 노드에서 닿지 않는 노드. 실행을 막지는 않는다."""
        if not self.entry or self.entry not in self.nodes:
            return sorted(self.nodes)
        seen = set()
        stack = [self.entry]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            node = self.nodes.get(current)
            if not node:
                continue
            for port in node.ports:
                nxt = self.next_id(current, port)
                if nxt:
                    stack.append(nxt)
        return sorted(set(self.nodes) - seen)

    # ------------------------------------------------------------ 직렬화

    def locators(self, exclude: Optional[str] = None) -> List[str]:
        """좌표를 남기는 노드들의 id. 다른 노드가 그 좌표를 참조할 수 있다."""
        return [nid for nid, node in self.nodes.items()
                if node.type in LOCATING_TYPES and nid != exclude]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "entry": self.entry,
            "layout": self.layout,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Graph:
        version = data.get("version", SCHEMA_VERSION)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"이 매크로는 최신 버전(v{version})으로 저장되었습니다. "
                f"이 프로그램은 v{SCHEMA_VERSION}까지 읽을 수 있습니다."
            )

        nodes = {
            nid: Node.from_dict(nid, ndata)
            for nid, ndata in (data.get("nodes") or {}).items()
        }
        edges = [Edge.from_dict(e) for e in (data.get("edges") or [])]
        layout = {k: list(v) for k, v in (data.get("layout") or {}).items()}

        entry = data.get("entry")
        if not entry:
            entry = next((nid for nid, n in nodes.items() if n.type == "start"), None)

        # 옛 파일에는 없던 값이라 기본은 켜짐
        enabled = data.get("enabled", True) is not False

        return cls(nodes=nodes, edges=edges, entry=entry, layout=layout,
                   enabled=enabled)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> Graph:
        return cls.from_dict(json.loads(text))
