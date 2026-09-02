# core/runlog.py
"""매크로를 마지막으로 실행한 시각.

매크로 파일이 아니라 앱 상태에 담는다. 실행할 때마다 매크로 파일을 건드리면
수정 시각이 계속 바뀌고 목록 요약 캐시도 매번 무효가 된다. 실행 기록은
매크로의 내용도 아니다.

대신 경로를 열쇠로 쓰므로 이름을 바꾸거나 폴더를 옮길 때 `rename` 을 함께
불러줘야 기록이 따라간다.
"""
from __future__ import annotations

import time
from typing import Dict

from core.library import humanize
from core.persistence import load_app_state, save_app_state

STATE_KEY = "last_run"

#: 지운 매크로의 기록이 쌓이지 않도록 오래된 것부터 버린다
LIMIT = 500


def _load() -> Dict[str, float]:
    raw = load_app_state().get(STATE_KEY)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, (int, float))}


def _save(table: Dict[str, float]) -> None:
    if len(table) > LIMIT:
        newest = sorted(table.items(), key=lambda kv: kv[1], reverse=True)[:LIMIT]
        table = dict(newest)
    save_app_state({STATE_KEY: table})


def get(path) -> float:
    """마지막 실행 시각. 실행한 적이 없으면 0."""
    return _load().get(str(path), 0.0)


def mark(path, when: float = 0.0) -> float:
    """지금(또는 주어진 시각)을 실행 시각으로 적는다."""
    when = when or time.time()
    table = _load()
    table[str(path)] = when
    _save(table)
    return when


def forget(path) -> None:
    table = _load()
    if table.pop(str(path), None) is not None:
        _save(table)


def rename(old, new) -> None:
    """매크로를 옮기거나 이름을 바꿀 때 기록도 따라오게 한다."""
    old, new = str(old), str(new)
    if old == new:
        return
    table = _load()
    when = table.pop(old, None)
    if when is None:
        return
    table[new] = when
    _save(table)


def text(path) -> str:
    return humanize(get(path))
