"""라이브러리 폴더에 예시 매크로 파일을 만든다 (화면 확인용).

    .venv\\Scripts\\python.exe tools/make_samples.py

이미 있는 파일은 건드리지 않는다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import library  # noqa: E402
from core.graph import Graph  # noqa: E402


def login_flow() -> Graph:
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("image_match", {"template": "로그인_버튼.png"}, node_id="n2")
    g.add_node("mouse_click", {"button": "left",
                               "pos": {"x": {"ref": "n2"}, "y": {"ref": "n2"}}}, node_id="n3")
    g.add_node("delay", {"seconds": 0.3}, node_id="n4")
    g.add_node("rgb_match", {"pos": {"x": 1204, "y": 88}, "color": [232, 69, 60]}, node_id="n5")
    g.add_node("stop", node_id="n6")
    g.add_node("delay", {"seconds": 0.5}, node_id="n7")
    g.add_node("key_press", {"key": "esc"}, node_id="n8")

    g.connect("n1", "n2")
    g.connect("n2", "n3", "true")
    g.connect("n2", "n7", "false")
    g.connect("n7", "n2")
    g.connect("n3", "n4")
    g.connect("n4", "n5")
    g.connect("n5", "n6", "true")
    g.connect("n5", "n8", "false")
    g.connect("n8", "n2")
    g.layout.update({"n1": [0, 0], "n2": [0, 130], "n3": [0, 300], "n4": [0, 430],
                     "n5": [0, 560], "n6": [0, 730], "n7": [400, 300], "n8": [400, 560]})
    return g


def repeat_clicks(times: int) -> Graph:
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("loop", {"max": times}, node_id="lp")
    g.add_node("mouse_click", {"button": "left", "pos": {"x": 640, "y": 400}}, node_id="hit")
    g.add_node("delay", {"seconds": 0.2}, node_id="wait")
    g.add_node("stop", node_id="end")

    g.connect("n1", "lp")
    g.connect("lp", "hit", "loop")
    g.connect("hit", "wait")
    g.connect("wait", "lp")
    g.connect("lp", "end", "done")
    g.layout.update({"n1": [0, 0], "lp": [0, 130], "hit": [0, 280],
                     "wait": [0, 410], "end": [340, 130]})
    return g


def type_esc() -> Graph:
    g = Graph()
    g.add_node("start", node_id="n1")
    g.add_node("key_press", {"key": "esc"}, node_id="k")
    g.add_node("stop", node_id="end")
    g.connect("n1", "k")
    g.connect("k", "end")
    g.layout.update({"n1": [0, 0], "k": [0, 130], "end": [0, 260]})
    return g


SAMPLES = [
    ("업무 자동화", "로그인 자동화", login_flow()),
    ("업무 자동화", "재고 시트 갱신", repeat_clicks(50)),
    ("테스트", "폼 반복 입력", repeat_clicks(5)),
    ("테스트", "화면 캡처 정리", type_esc()),
    (None, "빠른 정지", type_esc()),
]


def main():
    root = library.library_root()
    print(f"라이브러리: {root}\n")

    made = skipped = 0
    for folder, name, graph in SAMPLES:
        target = root / folder if folder else root
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{name}{library.MACRO_SUFFIX}"

        if path.exists():
            print(f"  건너뜀  {path.relative_to(root)}")
            skipped += 1
            continue

        with open(path, "w", encoding="utf-8") as f:
            f.write(graph.to_json())
        print(f"  생성    {path.relative_to(root)}  (노드 {len(graph.nodes)})")
        made += 1

    print(f"\n{made}개 생성, {skipped}개 건너뜀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
