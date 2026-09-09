"""그래프 엔진을 눈으로 확인하는 데모.

    python tools/graph_demo.py            # 화면만 읽는다 (마우스 안 건드림)
    python tools/graph_demo.py --move     # 마우스도 실제로 움직인다

화면 한 점의 색을 실제로 읽어서, 맞는 색을 기대하는 조건은 '참'으로,
틀린 색을 기대하는 조건은 '거짓'으로 갈라지는 그래프를 돌린다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import screen
from core.graph import Graph, GraphExecutor, StopReason
from core.mouse import get_mouse_position


PORT_MARK = {"true": "있음", "false": "없음", "loop": "반복", "done": "빠져나감", "next": ""}


def build_graph(probe, actual_rgb, move: bool):
    """probe 지점의 색을 두 번 검사한다 — 한 번은 맞게, 한 번은 틀리게."""
    g = Graph()

    g.add_node("start", node_id="start", name="시작")
    g.add_node("loop", {"max": 3}, node_id="loop", name="3회 반복")

    g.add_node(
        "rgb_match",
        {"pos": {"x": probe[0], "y": probe[1]}, "color": list(actual_rgb)},
        node_id="hit", name="색상 일치 (맞는 색)",
    )
    g.add_node(
        "rgb_match",
        {"pos": {"x": probe[0], "y": probe[1]}, "color": [1, 2, 3]},
        node_id="miss", name="색상 일치 (틀린 색)",
    )

    g.add_node("delay", {"seconds": 0.35}, node_id="wait", name="대기 0.35초")
    g.add_node("stop", node_id="end", name="매크로 중지")

    g.connect("start", "loop")
    g.connect("loop", "hit", "loop")

    if move:
        # 찾은 좌표를 뒤 노드가 참조한다 — @parent 를 대신하는 노드 id 참조
        g.add_node(
            "mouse_move",
            {"pos": {"x": {"ref": "hit"}, "y": {"ref": "hit"}}},
            node_id="go", name="마우스 이동 (hit 좌표로)",
        )
        g.connect("hit", "go", "true")
        g.connect("go", "miss")
    else:
        g.connect("hit", "miss", "true")

    g.connect("hit", "wait", "false")        # 실제로는 안 지나감
    g.connect("miss", "wait", "true")        # 실제로는 안 지나감
    g.connect("miss", "wait", "false")       # 여기로 온다
    g.connect("wait", "loop")
    g.connect("loop", "end", "done")

    return g


def main():
    move = "--move" in sys.argv

    probe = get_mouse_position()
    actual = screen.grab_rgb_at(*probe)
    if actual is None:
        print("화면 색을 읽지 못했습니다.")
        return 1

    print(f"기준점: 지금 마우스 자리 {probe}, 그 색 RGB{actual}")
    print(f"마우스 이동: {'실제로 움직임' if move else '안 함 (--move 로 켜기)'}\n")

    graph = build_graph(probe, actual, move)

    problems = graph.validate()
    print(f"검사: {'문제 없음' if not problems else problems}")
    print(f"노드 {len(graph.nodes)}개 · 연결 {len(graph.edges)}개\n")

    started = time.perf_counter()
    order = []

    def on_node(node_id):
        node = graph.nodes[node_id]
        elapsed = time.perf_counter() - started
        order.append(node_id)
        print(f"  {elapsed:6.2f}s  {node.name or node.type}")

    executor = GraphExecutor(
        graph,
        on_node=on_node,
        mouse_move_duration=0.25 if move else 0.0,
        max_steps=200,
        max_seconds=30,
    )

    print("실행 ─────────────────────────────")
    result = executor.run()
    print("──────────────────────────────────\n")

    label = {
        StopReason.STOP_NODE: "중지 노드를 만나 정상 종료",
        StopReason.COMPLETED: "더 갈 곳이 없어 종료",
        StopReason.STOPPED: "정지 요청으로 중단",
        StopReason.MAX_STEPS: "노드 실행 횟수 상한",
        StopReason.TIMEOUT: "시간 초과",
        StopReason.ERROR: f"오류: {result.error}",
    }.get(result.reason, result.reason)

    print(f"결과   : {label}")
    print(f"실행   : 노드 {result.steps}회 · {result.elapsed:.2f}초")
    print(f"찾은 좌표: {executor.coords or '없음'}")

    body = order.count("hit")
    print(f"\n반복 본문이 {body}번 돌았습니다 (반복 횟수 3 -> 몸통 3번 뒤 done)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
