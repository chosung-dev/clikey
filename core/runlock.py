# core/runlock.py
"""매크로 실행권 하나. 마우스·키보드는 나눠 쓸 수 없다.

지금까지 대시보드는 매크로 경로를 키로 같은 매크로의 중복 실행만 막았다.
서로 다른 매크로 둘이 동시에 도는 것은 막지 않았는데, 둘 다 마우스를
움직이므로 어느 쪽도 제대로 돌지 않는다. MCP 로 Claude 가 실행을 시작할 수
있게 되면서 그 틈이 훨씬 잘 벌어지므로 실행권을 하나로 모은다.

기다리지 않는다. 이미 도는 것이 있으면 그 이름을 돌려주고 곧바로 물러난다 —
툴 호출이 앞의 매크로가 끝날 때까지 붙들려 있으면 부르는 쪽이 멈춘 것처럼
보인다.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Optional

_guard = threading.Lock()      # 아래 두 값을 지킨다
_taken = False
_holder: Optional[str] = None


def acquire(name: str) -> bool:
    """실행권을 잡는다. 이미 남이 잡고 있으면 False."""
    global _taken, _holder
    with _guard:
        if _taken:
            return False
        _taken = True
        _holder = name
        return True


def release() -> None:
    global _taken, _holder
    with _guard:
        _taken = False
        _holder = None


def holder() -> Optional[str]:
    """지금 돌고 있는 매크로 이름. 없으면 None."""
    with _guard:
        return _holder if _taken else None


@contextmanager
def held(name: str):
    """잡았으면 이름, 못 잡았으면 None 을 준다. 잡았을 때만 놓는다."""
    if not acquire(name):
        yield None
        return
    try:
        yield name
    finally:
        release()
