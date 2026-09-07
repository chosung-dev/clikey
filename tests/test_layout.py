"""core.graph.layout 자동 정렬 테스트 — Qt 없이 좌표만 본다.

    python tests/test_layout.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.graph import Graph  # noqa: E402
from core.graph import layout  # noqa: E402

SIZE = (160.0, 60.0)


def sizes(graph):
    return {nid: SIZE for nid in graph.nodes}


def center(pos, nid):
    return pos[nid][0] + SIZE[0] / 2


def chain(graph, *ids):
    for a, b in zip(ids, ids[1:]):
        graph.connect(a, b)


# ---------------------------------------------------------------- 기본

def test_empty():
    assert layout.arrange(Graph()) == {}


def test_chain_is_a_straight_column():
    g = Graph()
    for nid, kind in (("s", "start"), ("a", "delay"), ("b", "notify"), ("e", "stop")):
        g.add_node(kind, node_id=nid)
    chain(g, "s", "a", "b", "e")

    pos = layout.arrange(g, sizes(g))
    assert len({x for x, _ in pos.values()}) == 1          # 한 줄로 선다
    ys = [pos[n][1] for n in ("s", "a", "b", "e")]
    assert ys == sorted(ys) and len(set(ys)) == 4          # 위에서 아래로


def test_every_node_gets_a_place():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("delay", node_id="a")        # 아무 데도 이어지지 않은 노드
    g.add_node("stop", node_id="e")
    g.connect("s", "e")

    assert set(layout.arrange(g, sizes(g))) == {"s", "a", "e"}


# ---------------------------------------------------------------- 갈래

def test_branches_split_sideways():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("image_match", node_id="c")
    g.add_node("delay", node_id="t")
    g.add_node("delay", node_id="f")
    chain(g, "s", "c")
    g.connect("c", "t", "true")
    g.connect("c", "f", "false")

    pos = layout.arrange(g, sizes(g))
    assert pos["t"][1] == pos["f"][1]                      # 같은 층
    assert pos["t"][0] < pos["f"][0]                       # 참이 왼쪽
    assert pos["t"][0] + SIZE[0] < pos["f"][0]             # 겹치지 않는다
    assert pos["t"][1] > pos["c"][1]                       # 조건보다 아래


def test_merge_sits_between_and_below_both_sides():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("image_match", node_id="c")
    g.add_node("delay", node_id="t")
    g.add_node("delay", node_id="f")
    g.add_node("stop", node_id="m")
    chain(g, "s", "c")
    g.connect("c", "t", "true")
    g.connect("c", "f", "false")
    g.connect("t", "m")
    g.connect("f", "m")

    pos = layout.arrange(g, sizes(g))
    assert pos["m"][1] > pos["t"][1] and pos["m"][1] > pos["f"][1]
    assert center(pos, "t") < center(pos, "m") < center(pos, "f")
    assert center(pos, "m") == center(pos, "c")            # 조건 바로 아래


# ---------------------------------------------------------------- 순환

def test_back_edge_does_not_stack_nodes():
    """되돌아가는 연결이 있어도 층은 앞으로만 간다."""
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("loop", node_id="l")
    g.add_node("delay", node_id="a")
    g.add_node("stop", node_id="e")
    chain(g, "s", "l")
    g.connect("l", "a", "loop")
    g.connect("l", "e", "done")
    g.connect("a", "l")                                    # 반복 — 위로 되돌아간다

    pos = layout.arrange(g, sizes(g))
    assert pos["l"][1] > pos["s"][1]
    assert pos["a"][1] > pos["l"][1] and pos["e"][1] > pos["l"][1]
    assert len({p[1] for p in pos.values()}) == 3          # 층이 뭉개지지 않는다


def test_pure_cycle_still_lays_out():
    """시작에서 닿지 않는데 자기들끼리 도는 무리도 자리를 받는다."""
    g = Graph()
    g.add_node("delay", node_id="a")
    g.add_node("delay", node_id="b")
    g.connect("a", "b")
    g.connect("b", "a")

    pos = layout.arrange(g, sizes(g))
    assert set(pos) == {"a", "b"}
    assert pos["a"] != pos["b"]


# ---------------------------------------------------------------- 무리 / 자리

def test_separate_groups_do_not_overlap():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("stop", node_id="e")
    g.add_node("delay", node_id="x")
    g.add_node("delay", node_id="y")
    g.connect("s", "e")
    g.connect("x", "y")

    pos = layout.arrange(g, sizes(g))
    main = {p[0] for p in (pos["s"], pos["e"])}
    apart = {p[0] for p in (pos["x"], pos["y"])}
    assert max(main) + SIZE[0] < min(apart)                # 옆으로 비켜 선다
    assert pos["x"][1] == pos["s"][1]                      # 맨 위 줄은 맞춘다


def test_anchor_keeps_the_graph_where_it_was():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("stop", node_id="e")
    g.connect("s", "e")
    g.layout = {"s": [640, 480], "e": [900, 300]}

    pos = layout.arrange(g, sizes(g))
    assert min(p[0] for p in pos.values()) == 640
    assert min(p[1] for p in pos.values()) == 300


def test_tall_cards_do_not_collide():
    """미리보기가 달린 카드는 키가 크다 — 아랫줄이 그만큼 내려가야 한다."""
    g = Graph()
    g.add_node("image_match", node_id="c")
    g.add_node("stop", node_id="e")
    g.connect("c", "e", "true")

    tall = {"c": (160.0, 200.0), "e": SIZE}
    pos = layout.arrange(g, tall)
    assert pos["e"][1] >= pos["c"][1] + 200


def test_arrange_is_stable():
    g = Graph()
    g.add_node("start", node_id="s")
    g.add_node("image_match", node_id="c")
    g.add_node("delay", node_id="t")
    g.add_node("delay", node_id="f")
    chain(g, "s", "c")
    g.connect("c", "t", "true")
    g.connect("c", "f", "false")

    first = layout.arrange(g, sizes(g))
    g.layout = {nid: list(p) for nid, p in first.items()}
    assert layout.arrange(g, sizes(g)) == first            # 다시 눌러도 그대로


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
