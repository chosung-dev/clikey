"""core.graph 스모크 테스트 — 실제 마우스/키보드/화면을 건드리지 않는다.

    python tests/test_graph.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph import Graph, GraphExecutor, StopReason  # noqa: E402
from core.graph.model import SCHEMA_VERSION, Edge, Node, resolve_pos  # noqa: E402


def trace(executor_cls, graph, **kwargs):
    """방문한 노드 순서와 실행 결과를 함께 돌려준다."""
    visited = []
    ex = executor_cls(graph, on_node=visited.append, **kwargs)
    result = ex.run()
    return visited, result, ex


# ---------------------------------------------------------------- 모델

def test_roundtrip():
    g = Graph()
    start = g.add_node("start", node_id="n1")
    click = g.add_node("mouse_click", {"button": "left", "pos": {"x": 10, "y": 20}}, node_id="n2")
    g.connect(start.id, click.id)
    g.layout[start.id] = [0, 0]

    restored = Graph.from_dict(g.to_dict())

    assert restored.entry == "n1"
    assert restored.nodes["n2"].params["pos"] == {"x": 10, "y": 20}
    assert restored.next_id("n1", "next") == "n2"
    assert restored.layout["n1"] == [0, 0]
    assert restored.to_dict() == g.to_dict()


def test_future_version_is_refused():
    try:
        Graph.from_dict({"version": SCHEMA_VERSION + 1, "nodes": {}, "edges": []})
    except ValueError as exc:
        assert "최신 버전" in str(exc)
    else:
        raise AssertionError("미래 버전 파일을 그냥 읽어버렸다")


def test_validate_catches_bad_port_and_missing_node():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.edges.append(Edge("n2", "n1", "true"))        # delay 에는 true 포트가 없다
    g.edges.append(Edge("n1", "없는노드", "next"))
    g.reindex()

    joined = " / ".join(g.validate())

    assert "'true' 출력이 없습니다" in joined, joined
    assert "없는노드" in joined, joined


def test_validate_catches_bad_coord_ref():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.add_node("mouse_click", {"pos": {"x": {"ref": "n2"}, "y": {"ref": "n2"}}}, node_id="n3")

    joined = " / ".join(g.validate())

    assert "좌표를 남기지 않는" in joined, joined


def test_validate_passes_on_good_graph():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("image_match", {"template": "a.png"}, node_id="img")
    g.add_node("mouse_click", {"pos": {"x": {"ref": "img"}, "y": {"ref": "img"}}}, node_id="click")
    g.add_node("stop", node_id="end")
    g.connect("n1", "img")
    g.connect("img", "click", "true")
    g.connect("img", "end", "false")
    g.connect("click", "end")

    assert g.validate() == []


def test_unreachable():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.add_node("delay", {"seconds": 0}, node_id="n3")   # 아무도 안 가리킴
    g.connect("n1", "n2")

    assert g.unreachable_ids() == ["n3"]


def test_resolve_pos():
    coords = {"n2": (100, 200)}

    assert resolve_pos({"x": 5, "y": 6}, coords) == (5, 6)
    assert resolve_pos({"x": {"ref": "n2"}, "y": {"ref": "n2"}}, coords) == (100, 200)
    # 한 축만 참조하는 형태 유지 (기존 "name.x, 500" 표현에 대응)
    assert resolve_pos({"x": {"ref": "n2"}, "y": 7}, coords) == (100, 7)
    # 아직 찾지 못한 노드를 참조하면 풀 수 없다
    assert resolve_pos({"x": {"ref": "n9"}, "y": 7}, coords) is None


def test_connect_replaces_same_port():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="a")
    g.add_node("delay", {"seconds": 0}, node_id="b")
    g.connect("n1", "a")
    g.connect("n1", "b")        # 같은 포트를 다시 연결하면 갈아끼운다

    assert g.next_id("n1", "next") == "b"
    assert len([e for e in g.edges if e.src == "n1"]) == 1


def test_remove_node_drops_its_edges():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.connect("n1", "n2")
    g.remove_node("n2")

    assert g.edges == []
    assert g.next_id("n1", "next") is None


# ---------------------------------------------------------------- 실행 엔진

def test_linear_run():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.add_node("stop", node_id="n3")
    g.connect("n1", "n2")
    g.connect("n2", "n3")

    visited, result, _ = trace(GraphExecutor, g)

    assert visited == ["n1", "n2", "n3"]
    assert result.reason == StopReason.STOP_NODE


def test_dangling_edge_completes():
    """마지막 노드에 나가는 연결이 없으면 자연 종료."""
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.connect("n1", "n2")

    visited, result, _ = trace(GraphExecutor, g)

    assert visited == ["n1", "n2"]
    assert result.reason == StopReason.COMPLETED


def test_loop_node_runs_body_then_exits():
    """loop(max=3): loop 포트로 2번 나간 뒤 3번째에 done 으로 빠진다."""
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="body")
    g.add_node("loop", {"max": 3}, node_id="lp")
    g.add_node("stop", node_id="end")
    g.connect("n1", "lp")
    g.connect("lp", "body", "loop")
    g.connect("body", "lp")
    g.connect("lp", "end", "done")

    visited, result, _ = trace(GraphExecutor, g)

    assert visited == ["n1", "lp", "body", "lp", "body", "lp", "end"], visited
    assert result.reason == StopReason.STOP_NODE


def test_loop_counter_resets_for_reentry():
    """done 으로 빠진 뒤 다시 들어오면 카운터가 처음부터 센다."""
    g = Graph()
    g.add_node("loop", {"max": 2}, node_id="lp")
    g.entry = "lp"
    g.connect("lp", "lp", "loop")

    ex = GraphExecutor(g)
    assert ex._do_loop(g.nodes["lp"]) == "loop"
    assert ex._do_loop(g.nodes["lp"]) == "done"
    assert ex._do_loop(g.nodes["lp"]) == "loop"


def test_infinite_loop_hits_step_cap():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("loop", {"max": 0}, node_id="lp")        # 0 = 무한
    g.connect("n1", "lp")
    g.connect("lp", "lp", "loop")

    _, result, _ = trace(GraphExecutor, g, max_steps=50)

    assert result.reason == StopReason.MAX_STEPS
    assert result.steps == 50


def test_stop_callback_interrupts():
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("loop", {"max": 0}, node_id="lp")
    g.connect("n1", "lp")
    g.connect("lp", "lp", "loop")

    seen = {"n": 0}

    def stop():
        seen["n"] += 1
        return seen["n"] > 10

    result = GraphExecutor(g, stop_callback=stop).run()

    assert result.reason == StopReason.STOPPED


def test_condition_branches_and_stores_coords():
    """조건의 참/거짓이 서로 다른 갈래로 가고, 찾은 좌표를 뒤 노드가 참조한다."""

    class Fake(GraphExecutor):
        """rgb_match 는 첫 번째만 실패하고 두 번째에 성공하도록 대체."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.checked = 0
            self.moved = []

        def _do_rgb_match(self, node):
            self.checked += 1
            if self.checked == 1:
                return "false"
            self.coords[node.id] = (640, 480)
            return "true"

        def _do_mouse_move(self, node):
            self.moved.append(resolve_pos(node.params.get("pos"), self.coords))
            return "next"

    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("rgb_match", {"pos": {"x": 1, "y": 1}, "color": [1, 2, 3]}, node_id="cond")
    g.add_node("delay", {"seconds": 0}, node_id="retry")
    g.add_node("mouse_move", {"pos": {"x": {"ref": "cond"}, "y": {"ref": "cond"}}}, node_id="use")
    g.add_node("stop", node_id="end")

    g.connect("n1", "cond")
    g.connect("cond", "retry", "false")
    g.connect("retry", "cond")              # 되돌아가기
    g.connect("cond", "use", "true")
    g.connect("use", "end")

    visited, result, ex = trace(Fake, g)

    assert visited == ["n1", "cond", "retry", "cond", "use", "end"], visited
    assert ex.moved == [(640, 480)], ex.moved
    assert result.reason == StopReason.STOP_NODE


def test_unresolvable_ref_does_not_crash():
    """참조 대상이 아직 좌표를 못 찾았으면 그 동작만 건너뛴다."""

    class Fake(GraphExecutor):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.moved = []

        def _do_mouse_move(self, node):
            pos = resolve_pos(node.params.get("pos"), self.coords)
            if pos is None:
                return "next"
            self.moved.append(pos)
            return "next"

    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("image_match", {"template": "x.png"}, node_id="img")
    g.add_node("mouse_move", {"pos": {"x": {"ref": "img"}, "y": {"ref": "img"}}}, node_id="use")
    g.add_node("stop", node_id="end")
    g.connect("n1", "use")                  # img 를 거치지 않고 바로 사용
    g.connect("use", "end")

    visited, result, ex = trace(Fake, g)

    assert visited == ["n1", "use", "end"]
    assert ex.moved == []
    assert result.reason == StopReason.STOP_NODE


def test_step_by_step():
    """run() 없이 한 단계씩 실행할 수 있다 (일시정지·스텝 실행의 토대)."""
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.connect("n1", "n2")

    ex = GraphExecutor(g)

    assert ex.current == "n1"
    assert ex.step() is None
    assert ex.current == "n2"
    assert ex.step() == StopReason.COMPLETED
    assert ex.finished


def test_unknown_node_is_skipped():
    """구버전 앱이 신형 파일을 열어도 흐름이 끊기지 않는다."""
    g = Graph()
    g.add_node("start", node_id="n1")
    g.nodes["n2"] = Node(id="n2", type="type_text", params={"text": "hi"})
    g.add_node("stop", node_id="n3")
    g.connect("n1", "n2")
    g.edges.append(Edge("n2", "n3", "next"))
    g.reindex()

    visited, result, _ = trace(GraphExecutor, g)

    assert visited == ["n1", "n2", "n3"]
    assert result.reason == StopReason.STOP_NODE


def test_error_in_node_is_reported():
    class Boom(GraphExecutor):
        def _do_delay(self, node):
            raise RuntimeError("터졌다")

    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="n2")
    g.connect("n1", "n2")

    result = Boom(g).run()

    assert result.reason == StopReason.ERROR
    assert "터졌다" in result.error
    assert result.last_node == "n2"


def test_enabled_defaults_on_and_survives_round_trip():
    g = Graph()
    assert g.enabled is True

    g.enabled = False
    assert Graph.from_json(g.to_json()).enabled is False


def test_enabled_missing_in_old_files_means_on():
    """사용 여부가 없던 시절 파일은 켜진 것으로 읽는다."""
    old = {"version": 1, "nodes": {}, "edges": [], "entry": None, "layout": {}}
    assert Graph.from_dict(old).enabled is True

# ----------------------------------------------------------------

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            print(f"      {type(exc).__name__}: {str(exc)[:300]}")
        else:
            print(f"ok    {fn.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
