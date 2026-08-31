# core/graph/__init__.py
"""노드 그래프 매크로 모델과 실행 엔진.

어떤 UI도 import 하지 않는다 — 편집기 없이도 그래프를 읽고 돌릴 수 있다.
"""
from core.graph.model import (
    SCHEMA_VERSION,
    NODE_PORTS,
    CONDITION_TYPES,
    Edge,
    Graph,
    Node,
)
from core.graph.engine import GraphExecutor, StopReason

__all__ = [
    "SCHEMA_VERSION",
    "NODE_PORTS",
    "CONDITION_TYPES",
    "Edge",
    "Graph",
    "Node",
    "GraphExecutor",
    "StopReason",
]
