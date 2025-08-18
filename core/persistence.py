# core/persistence.py
from __future__ import annotations
from typing import Dict, Any, List

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
