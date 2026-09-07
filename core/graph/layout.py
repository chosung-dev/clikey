# core/graph/layout.py
"""노드를 흐름대로 다시 앉힌다 (자동 정렬).

시작에서 아래로 흐르고 갈래는 옆으로 벌어지도록, 노드를 층으로 나눈 뒤
각 층 안에서 자리를 정한다. UI 를 import 하지 않는다 — 노드 크기를 받아
좌표만 돌려주므로 편집기 없이도 시험할 수 있다.

층 나누기는 '가장 긴 경로' 방식이다. 노드는 자기에게 들어오는 모든 앞방향
연결보다 반드시 아래에 놓이므로, 되돌아가는 연결(반복·재시도)을 빼면 선이
위로 거슬러 올라가지 않는다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from core.graph.model import Graph

#: 크기를 못 받았을 때 쓸 카드 크기
DEFAULT_SIZE = (160.0, 60.0)

GAP_X = 56.0          # 같은 층에서 카드 사이
GAP_Y = 96.0          # 층과 층 사이
GROUP_GAP = 160.0     # 시작에서 닿지 않는 따로 노는 무리 사이
PASSES = 4            # 자리 다듬기 왕복 횟수

Pos = Tuple[int, int]


# ---------------------------------------------------------------- 그래프 읽기

def _children(graph: Graph) -> Dict[str, List[str]]:
    """{노드: 다음 노드들} — 포트 선언 순서대로.

    실행이 따라가는 길과 같게 `next_id` 를 쓴다. 한 포트에 연결이 둘이면
    실행은 하나만 따라가므로, 그림도 같은 것만 본다.
    """
    out: Dict[str, List[str]] = {}
    for node_id, node in graph.nodes.items():
        kids: List[str] = []
        for port in node.ports:
            dst = graph.next_id(node_id, port)
            if dst and dst in graph.nodes and dst not in kids:
                kids.append(dst)
        out[node_id] = kids
    return out


def _roots(graph: Graph, children: Dict[str, List[str]]) -> List[str]:
    """훑기를 시작할 순서. 앞쪽일수록 먼저 자리를 잡는다.

    시작 노드가 맨 앞, 그다음 들어오는 연결이 없는 노드, 마지막으로 나머지
    (자기들끼리만 순환하는 무리). 모든 노드를 담으므로 빠지는 노드가 없다.
    """
    indeg = {node_id: 0 for node_id in graph.nodes}
    for kids in children.values():
        for kid in kids:
            indeg[kid] += 1

    start = graph.start_node()
    head = [start.id] if start is not None else []
    loose = [n for n in graph.nodes if indeg[n] == 0 and n not in head]
    rest = [n for n in graph.nodes if n not in head and indeg[n] > 0]
    return head + loose + rest


def _walk(children: Dict[str, List[str]],
          roots: Sequence[str]) -> Tuple[List[str], Set[Tuple[str, str]]]:
    """깊이 우선으로 훑어 (발견 순서, 되돌아가는 연결) 를 낸다.

    지금 훑고 있는 길 위에 있는 노드로 가는 연결이 되돌아가는 연결이다.
    그것만 빼면 그래프에 순환이 없어져 층을 나눌 수 있다.
    """
    seen: Set[str] = set()
    order: List[str] = []
    back: Set[Tuple[str, str]] = set()

    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        order.append(root)
        stack = [(root, list(children.get(root, ())))]
        on_path = {root}

        while stack:
            node_id, kids = stack[-1]
            if not kids:
                stack.pop()
                on_path.discard(node_id)
                continue
            kid = kids.pop(0)
            if kid in on_path:
                back.add((node_id, kid))
                continue
            if kid in seen:
                continue                     # 이미 놓인 노드로 합쳐지는 길
            seen.add(kid)
            order.append(kid)
            stack.append((kid, list(children.get(kid, ()))))
            on_path.add(kid)

    return order, back


def _layers(order: Sequence[str], children: Dict[str, List[str]],
            back: Set[Tuple[str, str]]) -> Dict[str, int]:
    """노드마다 몇 번째 층인지. 들어오는 연결보다 항상 아래에 놓인다."""
    rank = {node_id: i for i, node_id in enumerate(order)}
    forward = {
        node_id: [k for k in children.get(node_id, ()) if (node_id, k) not in back]
        for node_id in order
    }

    indeg = {node_id: 0 for node_id in order}
    for kids in forward.values():
        for kid in kids:
            indeg[kid] += 1

    layer = {node_id: 0 for node_id in order}
    ready = sorted((n for n in order if indeg[n] == 0), key=rank.get)

    while ready:
        node_id = ready.pop(0)
        for kid in forward[node_id]:
            layer[kid] = max(layer[kid], layer[node_id] + 1)
            indeg[kid] -= 1
            if indeg[kid] == 0:
                ready.append(kid)
        # 발견 순서를 지켜야 갈래가 왼쪽부터 차례로 놓인다
        ready.sort(key=rank.get)

    return layer


def _groups(graph: Graph, children: Dict[str, List[str]],
            order: Sequence[str]) -> Dict[str, int]:
    """서로 연결되지 않은 무리마다 번호. 작은 번호가 왼쪽에 선다."""
    parent = {node_id: node_id for node_id in graph.nodes}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    for node_id, kids in children.items():
        for kid in kids:
            a, b = find(node_id), find(kid)
            if a != b:
                parent[a] = b

    rank: Dict[str, int] = {}
    for node_id in order:                    # 발견 순서 = 무리의 순서
        rank.setdefault(find(node_id), len(rank))
    return {node_id: rank[find(node_id)] for node_id in graph.nodes}


# ---------------------------------------------------------------- 층 안 순서

def _neighbors(order: Sequence[str], children: Dict[str, List[str]],
               back: Set[Tuple[str, str]]) -> Tuple[Dict[str, List[str]],
                                                    Dict[str, List[str]]]:
    """앞방향 연결만 본 (부모들, 자식들)."""
    preds: Dict[str, List[str]] = {node_id: [] for node_id in order}
    succs: Dict[str, List[str]] = {node_id: [] for node_id in order}
    for node_id in order:
        for kid in children.get(node_id, ()):
            if (node_id, kid) in back:
                continue
            succs[node_id].append(kid)
            preds[kid].append(node_id)
    return preds, succs


def _sort_rows(rows: List[List[str]], preds, succs, group: Dict[str, int]) -> None:
    """이웃의 가운데로 모이도록 층 안 순서를 다듬는다 (제자리 수정).

    합쳐지는 노드가 두 갈래 사이로 오게 해서 선이 덜 엇갈린다. 같은 값이면
    순서를 그대로 두므로(안정 정렬) '참' 갈래가 왼쪽에 남는다.
    """
    for step in range(PASSES):
        downward = step % 2 == 0
        span = range(1, len(rows)) if downward else range(len(rows) - 2, -1, -1)
        spot = {n: i for row in rows for i, n in enumerate(row)}

        for index in span:
            row = rows[index]
            look = preds if downward else succs
            keys = {}
            for i, node_id in enumerate(row):
                near = [spot[o] for o in look[node_id] if o in spot]
                keys[node_id] = (group[node_id],
                                 sum(near) / len(near) if near else i, i)
            row.sort(key=keys.get)
            for i, node_id in enumerate(row):
                spot[node_id] = i


# ---------------------------------------------------------------- 가로 자리

def _gap(a: str, b: str, group: Dict[str, int]) -> float:
    return GROUP_GAP if group[a] != group[b] else GAP_X


def _sep(a: str, b: str, sizes: Dict[str, Tuple[float, float]],
         group: Dict[str, int]) -> float:
    """이웃한 두 카드의 중심이 최소한 이만큼은 떨어져야 한다."""
    return (sizes[a][0] + sizes[b][0]) / 2 + _gap(a, b, group)


def _pack(row: Sequence[str], centers: Dict[str, float],
          sizes: Dict[str, Tuple[float, float]], group: Dict[str, int]) -> None:
    """왼쪽부터 차례로 붙여 놓는다."""
    x = 0.0
    for i, node_id in enumerate(row):
        if i:
            x += _sep(row[i - 1], node_id, sizes, group)
        centers[node_id] = x


def _nudge(row: Sequence[str], i: int, target: float, centers, sizes, group,
           weight: Dict[str, int]) -> None:
    """i 번째 카드를 target 쪽으로 옮긴다.

    순서는 바꾸지 않고, 나보다 가벼운(연결이 적은) 이웃만 밀어낸다. 무거운
    이웃을 만나면 거기까지만 간다 — 이미 자리를 잡은 카드가 흔들리지 않게.
    """
    here = centers[row[i]]
    if abs(target - here) < 0.5:
        return

    if target > here:
        j = i + 1
        while j < len(row) and weight[row[j]] < weight[row[i]]:
            j += 1
        if j < len(row):
            limit = centers[row[j]]
            for k in range(j - 1, i - 1, -1):
                limit -= _sep(row[k], row[k + 1], sizes, group)
            target = min(target, limit)
        if target <= here:
            return
        centers[row[i]] = target
        for k in range(i, len(row) - 1):     # 오른쪽 이웃을 밀어낸다
            need = centers[row[k]] + _sep(row[k], row[k + 1], sizes, group)
            if centers[row[k + 1]] >= need:
                break
            centers[row[k + 1]] = need
    else:
        j = i - 1
        while j >= 0 and weight[row[j]] < weight[row[i]]:
            j -= 1
        if j >= 0:
            limit = centers[row[j]]
            for k in range(j, i):
                limit += _sep(row[k], row[k + 1], sizes, group)
            target = max(target, limit)
        if target >= here:
            return
        centers[row[i]] = target
        for k in range(i, 0, -1):
            need = centers[row[k]] - _sep(row[k - 1], row[k], sizes, group)
            if centers[row[k - 1]] <= need:
                break
            centers[row[k - 1]] = need


def _place_x(rows: List[List[str]], preds, succs, sizes, group) -> Dict[str, float]:
    """카드 가운데의 가로 좌표.

    한 줄씩 위·아래를 오가며, 이어진 카드들의 평균 자리로 당긴다. 연결이
    많은 카드부터 옮겨야 줄기가 곧게 선다.
    """
    centers: Dict[str, float] = {}
    for row in rows:
        _pack(row, centers, sizes, group)

    for step in range(PASSES):
        downward = step % 2 == 0
        span = range(1, len(rows)) if downward else range(len(rows) - 2, -1, -1)
        look = preds if downward else succs

        for index in span:
            row = rows[index]
            weight = {n: len(look[n]) for n in row}
            targets = {}
            for node_id in row:
                near = [centers[o] for o in look[node_id] if o in centers]
                if near:
                    targets[node_id] = sum(near) / len(near)

            movable = sorted(range(len(row)),
                             key=lambda i: (-weight[row[i]], i))
            for i in movable:
                target = targets.get(row[i])
                if target is not None:
                    _nudge(row, i, target, centers, sizes, group, weight)

    return centers


# ---------------------------------------------------------------- 바깥에서 쓰는 것

def arrange(graph: Graph,
            sizes: Optional[Dict[str, Tuple[float, float]]] = None,
            anchor: Optional[Tuple[float, float]] = None) -> Dict[str, Pos]:
    """{노드 id: (x, y)} 를 낸다. 노드가 없으면 빈 사전.

    `sizes` 는 {노드 id: (너비, 높이)}. 카드마다 크기가 다르므로(이미지
    검색 노드는 미리보기만큼 키가 크다) 화면에서 재어 넘겨준다.
    `anchor` 는 결과를 놓을 왼쪽 위 모서리. 없으면 지금 위치의 왼쪽 위에
    맞춰, 정렬해도 화면이 엉뚱한 데로 튀지 않게 한다.
    """
    if not graph.nodes:
        return {}

    sizes = {node_id: tuple(map(float, (sizes or {}).get(node_id, DEFAULT_SIZE)))
             for node_id in graph.nodes}

    children = _children(graph)
    order, back = _walk(children, _roots(graph, children))
    layer = _layers(order, children, back)
    group = _groups(graph, children, order)
    preds, succs = _neighbors(order, children, back)

    rank = {node_id: i for i, node_id in enumerate(order)}
    rows: List[List[str]] = [[] for _ in range(max(layer.values()) + 1)]
    for node_id in order:                    # 발견 순서가 첫 자리 순서
        rows[layer[node_id]].append(node_id)
    for row in rows:                         # 따로 노는 무리끼리 섞이지 않게
        row.sort(key=lambda n: (group[n], rank[n]))

    _sort_rows(rows, preds, succs, group)
    centers = _place_x(rows, preds, succs, sizes, group)

    tops: List[float] = []
    y = 0.0
    for row in rows:
        tops.append(y)
        y += max(sizes[n][1] for n in row) + GAP_Y

    placed = {
        node_id: (centers[node_id] - sizes[node_id][0] / 2, tops[index])
        for index, row in enumerate(rows) for node_id in row
    }

    if anchor is None:
        anchor = _corner(graph, placed)
    dx = anchor[0] - min(x for x, _ in placed.values())
    dy = anchor[1] - min(y for _, y in placed.values())
    return {node_id: (round(x + dx), round(y + dy))
            for node_id, (x, y) in placed.items()}


def _corner(graph: Graph, placed: Dict[str, Tuple[float, float]]) -> Tuple[float, float]:
    """지금 놓여 있는 자리의 왼쪽 위. 아직 자리가 없으면 원점."""
    spots = [graph.layout[n] for n in placed if n in graph.layout]
    if not spots:
        return 0.0, 0.0
    return float(min(p[0] for p in spots)), float(min(p[1] for p in spots))
