# core/keyboard_hotkey.py
from __future__ import annotations
from typing import Optional, Dict, Any, Callable

# 전역 핫키용
try:
    import keyboard  # pip install keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    keyboard = None  # type: ignore
    KEYBOARD_AVAILABLE = False

def display_key_name(key: Optional[str]) -> str:
    if not key:
        return ""
    return key.upper() if len(key) == 1 else key

def normalize_key_for_keyboard(keysym: str) -> Optional[str]:
    if not keysym:
        return None
    k = keysym
    if len(k) == 1:
        return k.lower()
    mapping = {
        "Return": "enter",
        "Escape": "esc",
        "BackSpace": "backspace",
        "Tab": "tab",
        "space": "space",
        "Up": "up",
        "Down": "down",
        "Left": "left",
        "Right": "right",
        "Home": "home",
        "End": "end",
        "Prior": "page up",
        "Next": "page down",
        "Insert": "insert",
        "Delete": "delete",
    }
    if k.startswith("F") and k[1:].isdigit():
        return k.lower()
    return mapping.get(k, None)

def register_hotkeys(root, ui) -> None:
    """Register start/stop hotkeys based on ui.hotkeys; stores handles in ui.hotkey_handles."""
    if not KEYBOARD_AVAILABLE or keyboard is None:
        return

    # remove existing
    for k in ("start", "stop"):
        h = ui.hotkey_handles.get(k)
        if h is not None:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
            ui.hotkey_handles[k] = None

    # add new
    if ui.hotkeys.get("start"):
        ui.hotkey_handles["start"] = keyboard.add_hotkey(
            ui.hotkeys["start"], lambda: root.after(0, ui.run_macros)
        )
    if ui.hotkeys.get("stop"):
        ui.hotkey_handles["stop"] = keyboard.add_hotkey(
            ui.hotkeys["stop"], lambda: root.after(0, ui.stop_execution)
        )
