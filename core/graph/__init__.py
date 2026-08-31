# core/graph/__init__.py
"""노드 그래프 매크로 모델과 실행 엔진 (UI 비의존).

기존 `items` 순차 리스트 모델과 나란히 존재한다. UI가 그래프로 넘어오기 전까지
양쪽이 함께 동작하며, 이 패키지는 tkinter를 포함한 어떤 UI도 import 하지 않는다.
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
