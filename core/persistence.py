# core/persistence.py
from __future__ import annotations
from typing import Dict, Any, List
import os, json

def is_valid_macro_line(s: str) -> bool:
    if not isinstance(s, str):
        return False
    if s.startswith(("키보드:", "마우스:", "시간:", "조건:", "조건끝")):
        return True
    if s.startswith("  ") and s[2:].startswith(("키보드:", "마우스:", "시간:")):
        return True
    return False

def export_data(list_items: List[str], settings: Dict[str, Any], hotkeys: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": 1,
        "items": list_items,
        "settings": {
            "repeat": int(settings.get("repeat", 1)),
            "start_delay": int(settings.get("start_delay", 3)),
        },
        "hotkeys": {
            "start": hotkeys.get("start"),
            "stop": hotkeys.get("stop"),
        },
    }

# --- 앱 상태 저장/복원: 최근 파일 경로 등 ---
def _app_state_path() -> str:
    base = os.path.join(os.path.expanduser("~"), ".namaans_macro")
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state or {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
