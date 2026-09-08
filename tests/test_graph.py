"""core.graph 스모크 테스트 — 실제 마우스/키보드/화면을 건드리지 않는다.

    python tests/test_graph.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph import Graph, GraphExecutor, StopReason  # noqa: E402
from core.graph.model import SCHEMA_VERSION, Edge, Node, resolve_pos  # noqa: E402
from core import runreport  # noqa: E402


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
    """loop(max=3): 몸통을 세 번 돌린 뒤 done 으로 빠진다."""
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

    assert visited == ["n1", "lp", "body", "lp", "body", "lp", "body",
                       "lp", "end"], visited
    assert result.reason == StopReason.STOP_NODE


def test_loop_counter_resets_for_reentry():
    """done 으로 빠진 뒤 다시 들어오면 카운터가 처음부터 센다."""
    g = Graph()
    g.add_node("loop", {"max": 2}, node_id="lp")
    g.entry = "lp"
    g.connect("lp", "lp", "loop")

    ex = GraphExecutor(g)
    assert ex._do_loop(g.nodes["lp"]) == "loop"
    assert ex._do_loop(g.nodes["lp"]) == "loop"
    assert ex._do_loop(g.nodes["lp"]) == "done"
    assert ex._do_loop(g.nodes["lp"]) == "loop"


def test_loop_of_one_still_runs_the_body_once():
    """max=1 이 몸통을 한 번도 돌리지 않던 버그를 붙잡아 둔다."""
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("delay", {"seconds": 0}, node_id="body")
    g.add_node("loop", {"max": 1}, node_id="lp")
    g.add_node("stop", node_id="end")
    g.connect("n1", "lp")
    g.connect("lp", "body", "loop")
    g.connect("body", "lp")
    g.connect("lp", "end", "done")

    visited, _, _ = trace(GraphExecutor, g)

    assert visited.count("body") == 1, visited


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

def test_notify_node_calls_the_given_way():
    """알림 노드는 부르는 쪽이 건넨 방법으로만 알린다 (엔진은 화면을 모른다)."""
    said = []
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("notify", {"title": "제목", "message": "본문",
                          "seconds": 3, "sound": False}, node_id="n")
    g.add_node("stop", node_id="e")
    g.connect("s", "n")
    g.connect("n", "e")

    GraphExecutor(g, notify=lambda *a: said.append(a)).run()
    assert said == [("제목", "본문", False, 3.0)], said


def test_notify_without_a_way_just_passes_through():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("notify", {"message": "본문"}, node_id="n")
    g.add_node("stop", node_id="e")
    g.connect("s", "n")
    g.connect("n", "e")

    result = GraphExecutor(g).run()
    assert result.reason == StopReason.STOP_NODE
    assert result.error is None

# ---------------------------------------------------------------- ask 노드


def ask_graph(choices=("1번", "2번", "3번"), prompt="정답을 골라줘"):
    """선택지마다 대기 노드가 하나씩 달린 판단 그래프."""
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("ask", {"prompt": prompt, "choices": list(choices)}, node_id="a")
    g.connect("s", "a")
    for name in choices:
        g.add_node("delay", {"ms": 0}, node_id=f"d-{name}")
        g.connect("a", f"d-{name}", port=name)
    return g


def test_ask_ports_follow_choices():
    node = Node("a", "ask", {"choices": ["예", "아니오"]})
    assert node.ports == ("예", "아니오")

    node.params["choices"] = ["1번", "2번", "3번"]
    assert node.ports == ("1번", "2번", "3번")


def test_ask_ports_drop_blank_and_duplicate():
    node = Node("a", "ask", {"choices": ["1번", "", "1번", "  ", "2번"]})
    assert node.ports == ("1번", "2번")


def test_validate_catches_thin_and_duplicate_choices():
    joined = " / ".join(ask_graph(choices=["1번"]).validate())
    assert "선택지가 둘 이상" in joined, joined

    g = ask_graph(choices=["1번", "2번"])
    g.nodes["a"].params["choices"] = ["1번", "1번"]
    joined = " / ".join(g.validate())
    assert "겹칩니다" in joined, joined

    g = ask_graph()
    g.nodes["a"].params["prompt"] = "   "
    assert any("판단 요청" in p for p in g.validate())


def test_ask_graph_is_mcp_only():
    assert ask_graph().mcp_only is True
    plain = Graph()
    plain.add_node("start", node_id="s")
    assert plain.mcp_only is False


def test_ask_without_decider_stops_distinctly():
    result = GraphExecutor(ask_graph()).run()
    # 중지 노드로 보고되면 성공으로 위장된다 — 반드시 구별돼야 한다
    assert result.reason == StopReason.NO_DECIDER, result.reason
    assert result.reason not in runreport.GOOD_REASONS


def test_ask_takes_the_chosen_port():
    visited, result, _ = trace(GraphExecutor, ask_graph(), ask=lambda n: "2번")
    assert result.reason == StopReason.COMPLETED
    assert visited == ["s", "a", "d-2번"], visited


def test_ask_rejects_an_unknown_choice():
    for answer in ("5번", None, ""):
        result = GraphExecutor(ask_graph(), ask=lambda n, a=answer: a).run()
        assert result.reason == StopReason.BAD_DECISION, (answer, result.reason)
        assert result.reason not in runreport.GOOD_REASONS


def test_ask_sees_the_node_it_asks_about():
    seen = []

    def ask(node):
        seen.append((node.id, node.params["prompt"], node.ports))
        return "1번"

    GraphExecutor(ask_graph()).run()           # 상대가 없으면 부르지도 않는다
    assert seen == []

    GraphExecutor(ask_graph(), ask=ask).run()
    assert seen == [("a", "정답을 골라줘", ("1번", "2번", "3번"))], seen


def test_waiting_for_a_decision_does_not_spend_the_time_limit():
    import time

    def slow(node):
        time.sleep(0.4)
        return "1번"

    result = GraphExecutor(ask_graph(), ask=slow, max_seconds=0.2).run()
    assert result.reason == StopReason.COMPLETED, result.reason
    assert result.elapsed < 0.2, result.elapsed


def test_on_exit_reports_the_port_taken():
    steps = []
    ex = GraphExecutor(ask_graph(), ask=lambda n: "3번",
                       on_exit=lambda nid, port: steps.append((nid, port)))
    ex.run()
    assert ("a", "3번") in steps, steps
    assert ("s", "next") in steps, steps


def test_path_recorder_keeps_only_the_forks():
    g = ask_graph()
    recorder = runreport.PathRecorder(g)
    GraphExecutor(g, ask=lambda n: "2번", on_exit=recorder).run()

    path = recorder.result()
    # start 와 delay 는 나갈 곳이 하나뿐이라 남기지 않는다
    assert path == ["ask(a) → 2번"], path


def test_summarize_run_marks_a_failed_decision():
    g = ask_graph()
    recorder = runreport.PathRecorder(g)
    result = GraphExecutor(g, ask=lambda n: "없는답", on_exit=recorder).run()

    summary = runreport.summarize_run(result, recorder.result())
    assert summary["ok"] is False
    assert summary["reason"] == StopReason.BAD_DECISION
    assert "선택지에 없는 답" in summary["text"]
    assert summary["path"] == ["ask(a) → 없음"], summary["path"]


def test_ask_graph_survives_a_roundtrip():
    g = ask_graph()
    restored = Graph.from_dict(g.to_dict())
    assert restored.nodes["a"].ports == ("1번", "2번", "3번")
    assert restored.next_id("a", "2번") == "d-2번"
    assert restored.mcp_only is True
    assert g.to_dict()["version"] == SCHEMA_VERSION


# ---------------------------------------------------------------- ai_point


def point_graph(region=(100, 100, 500, 400), prompt="빨간 점을 짚어줘"):
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("ai_point", {"prompt": prompt,
                            "region": list(region) if region else None},
               node_id="p")
    g.connect("s", "p")
    g.add_node("delay", {"ms": 0}, node_id="hit")
    g.add_node("delay", {"ms": 0}, node_id="miss")
    g.connect("p", "hit", port="찾음")
    g.connect("p", "miss", port="못 찾음")
    return g


def test_point_node_has_two_fixed_ports():
    assert point_graph().nodes["p"].ports == ("찾음", "못 찾음")


def test_point_turns_a_fraction_into_a_screen_coordinate():
    # 영역이 (100,100)-(500,400) 이므로 400 x 300
    for frac, want in (({"x": 0.0, "y": 0.0}, (100, 100)),
                       ({"x": 1.0, "y": 1.0}, (500, 400)),
                       ({"x": 0.5, "y": 0.5}, (300, 250)),
                       ((0.25, 0.75), (200, 325))):
        ex = GraphExecutor(point_graph(), ask=lambda n, f=frac: f)
        ex.run()
        assert ex.coords["p"] == want, (frac, ex.coords.get("p"))


def test_point_coordinate_reaches_the_next_node():
    ex = GraphExecutor(point_graph(), ask=lambda n: {"x": 0.25, "y": 0.75})
    ex.run()
    assert resolve_pos({"x": {"ref": "p"}, "y": {"ref": "p"}}, ex.coords) == (200, 325)


def test_point_branches_on_whether_it_was_found():
    visited, result, _ = trace(GraphExecutor, point_graph(),
                               ask=lambda n: {"x": 0.5, "y": 0.5})
    assert visited == ["s", "p", "hit"], visited
    assert result.reason == StopReason.COMPLETED

    visited, result, _ = trace(GraphExecutor, point_graph(), ask=lambda n: None)
    assert visited == ["s", "p", "miss"], visited


def test_point_rejects_answers_outside_the_frame():
    for bad in ({"x": 1.5, "y": 0.5}, {"x": -0.1, "y": 0.5}, "가운데",
                {"x": "a", "y": 0.5}, (0.5,)):
        result = GraphExecutor(point_graph(), ask=lambda n, b=bad: b).run()
        assert result.reason == StopReason.BAD_DECISION, (bad, result.reason)


def test_point_without_a_decider_stops_distinctly():
    assert GraphExecutor(point_graph()).run().reason == StopReason.NO_DECIDER


def test_point_requires_a_region_that_survives_unshrunk():
    assert any("범위를 지정" in p for p in point_graph(region=None).validate())

    wide = point_graph(region=(0, 0, 3000, 100))       # 긴 변 초과
    assert any("긴 변" in p for p in wide.validate()), wide.validate()

    fat = point_graph(region=(0, 0, 2000, 2000))       # 토큰 초과
    assert any("토큰" in p for p in fat.validate()), fat.validate()

    assert point_graph().validate() == []


def test_point_requires_a_prompt():
    assert any("무엇을 찾을지" in p for p in point_graph(prompt="  ").validate())


def test_vision_budget_matches_the_documented_limits():
    from core.graph.model import (VISION_MAX_EDGE, VISION_MAX_TOKENS,
                                  vision_tokens)

    # 28px 칸으로 나눈 뒤 올림한 개수를 곱한다
    assert vision_tokens(28, 28) == 1
    assert vision_tokens(29, 28) == 2
    assert vision_tokens(1000, 1000) == 1296
    # 문서에 적힌 고해상도 한계와 정확히 맞는 크기
    assert vision_tokens(VISION_MAX_EDGE, 1449) == VISION_MAX_TOKENS


def test_point_graph_is_mcp_only_and_leaves_coordinates():
    from core.graph.model import LOCATING_TYPES

    assert point_graph().mcp_only is True
    assert "ai_point" in LOCATING_TYPES
    assert point_graph().locators() == ["p"]


def test_point_graph_survives_a_roundtrip():
    restored = Graph.from_dict(point_graph().to_dict())
    assert restored.nodes["p"].ports == ("찾음", "못 찾음")
    assert restored.next_id("p", "찾음") == "hit"
    assert restored.mcp_only is True


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
