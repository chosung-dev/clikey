# core/graph/model.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json
import uuid

SCHEMA_VERSION = 1

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

    "image_match": ("true", "false"),
    "rgb_match": ("true", "false"),

    "loop": ("loop", "done"),
}

# 좌표를 찾아 뒤쪽 노드가 참조할 수 있게 남기는 노드들
LOCATING_TYPES = frozenset({"image_match", "rgb_match"})
CONDITION_TYPES = frozenset({"image_match", "rgb_match"})


def new_id() -> str:
    return "n" + uuid.uuid4().hex[:8]


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
        return NODE_PORTS.get(self.type, ())

    @property
    def is_condition(self) -> bool:
        return self.type in CONDITION_TYPES

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

    def disconnect(self, src: str, port: str = "next") -> None:
        self.edges = [e for e in self.edges if not (e.src == src and e.port == port)]
        self.reindex()

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "entry": self.entry,
            "layout": self.layout,
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

        return cls(nodes=nodes, edges=edges, entry=entry, layout=layout)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> Graph:
        return cls.from_dict(json.loads(text))
