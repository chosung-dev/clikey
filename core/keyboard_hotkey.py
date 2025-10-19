# core/keyboard_hotkey.py
from __future__ import annotations
from typing import Optional
import keyboard


def normalize_key_for_keyboard(keysym: str) -> Optional[str]:
    """Normalize key name from Tkinter/X11 format to keyboard library format."""
    if not keysym:
        return None

    if len(keysym) == 1:
        return keysym.lower()

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
        "Control_L": "ctrl",
        "Control_R": "ctrl",
        "Shift_L": "shift",
        "Shift_R": "shift",
        "Alt_L": "alt",
        "Alt_R": "alt",
    }

    if keysym.startswith("F") and keysym[1:].isdigit():
        return keysym.lower()

    return mapping.get(keysym, keysym.lower())

def register_hotkeys(root, ui) -> None:
    """Register or update global hotkeys for start/stop."""
    for key in ("start", "stop"):
        handle = ui.hotkey_handles.get(key)
        if handle is not None:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
            ui.hotkey_handles[key] = None

    if ui.hotkeys.get("start"):
        ui.hotkey_handles["start"] = keyboard.add_hotkey(
            ui.hotkeys["start"], lambda: root.after(0, ui.run_macros)
        )
    if ui.hotkeys.get("stop"):
        ui.hotkey_handles["stop"] = keyboard.add_hotkey(
            ui.hotkeys["stop"], lambda: root.after(0, ui.stop_execution)
        )
