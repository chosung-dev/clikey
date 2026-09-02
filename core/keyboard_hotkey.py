# core/keyboard_hotkey.py
from __future__ import annotations
from typing import Optional

# Lazy import for faster startup
keyboard = None

def _get_keyboard():
    global keyboard
    if keyboard is None:
        import keyboard as kb
        keyboard = kb
    return keyboard


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
