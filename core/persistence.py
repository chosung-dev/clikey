# core/persistence.py
from __future__ import annotations
from typing import Dict, Any, List
import os, json

from core.macro_block import MacroBlock


def export_data(macro_blocks: List[MacroBlock], settings: Dict[str, Any], hotkeys: Dict[str, Any]) -> Dict[str, Any]:
    """Export data using MacroBlock format."""
    return {
        "version": 1,
        "macro_blocks": [block.to_dict() for block in macro_blocks],
        "settings": {
            "repeat": int(settings.get("repeat", 1)),
            "start_delay": float(settings.get("start_delay", 3)),
            "step_delay": float(settings.get("step_delay", 0.001)),
            "beep_on_finish": int(settings.get("beep_on_finish", False)),
        },
        "hotkeys": {
            "start": hotkeys.get("start"),
            "stop": hotkeys.get("stop"),
        },
    }


# --- 앱 상태 저장/복원: 최근 파일 경로 등 ---
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state or {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_macro_data(file_path: str) -> Dict[str, Any]:
    """Load macro data from file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
