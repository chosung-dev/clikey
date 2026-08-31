# core/persistence.py
"""앱 상태(환경설정·최근 확인 시각 등)를 사용자 홈에 저장한다."""
from __future__ import annotations
import os, json


def _app_state_path() -> str:
    base = os.path.join(os.path.expanduser("~"), ".clikey")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "app_state.json")


def load_app_state() -> dict:
    path = _app_state_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_app_state(state: dict) -> None:
    path = _app_state_path()
    try:
        # 기존 상태와 merge
        existing = load_app_state()
        existing.update(state or {})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
