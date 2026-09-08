# core/prefs.py
"""앱 전체 설정. 매크로 파일이 아니라 사용자 단위로 남는다.

`~/.clikey/app_state.json` 에 함께 저장한다.
"""
from __future__ import annotations

from typing import Any, Dict

from core.persistence import load_app_state, save_app_state

KEY = "prefs"

DEFAULTS: Dict[str, Any] = {
    # 새 매크로를 만들 때 시작·종료 노드에 박히는 단축키
    "default_start_key": "f8",
    "default_stop_key": "f9",
    # 실행 설정
    "step_delay": 0.03,
    "mouse_move_duration": 0.0,
    # Claude Code 연동 (MCP). 기본은 꺼둔다 — 켜야 포트가 열린다.
    "mcp_enabled": False,
    "mcp_port": 3001,
}


def load() -> Dict[str, Any]:
    stored = (load_app_state() or {}).get(KEY) or {}
    values = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in stored:
            continue
        try:
            values[key] = type(default)(stored[key])
        except (TypeError, ValueError):
            pass
    return values


def save(values: Dict[str, Any]) -> None:
    current = load()
    current.update({k: v for k, v in values.items() if k in DEFAULTS})
    save_app_state({KEY: current})
