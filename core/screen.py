# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional

try:
    from PIL import ImageGrab
except Exception as e:  # Pillow 없는 경우를 대비
    ImageGrab = None  # type: ignore

try:
    import pyautogui
except Exception:
    pyautogui = None  # type: ignore

def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """Safely grab RGB at screen coordinate (x,y). Returns None on failure."""
    if ImageGrab is None:
        return None
    try:
        img = ImageGrab.grab()
        r, g, b = img.getpixel((x, y))
        return (r, g, b)
    except Exception:
        return None

def get_rgb_under_mouse() -> Optional[Tuple[int, int, int, int, int]]:
    """Returns (x, y, r, g, b) under current cursor, or None on failure."""
    if pyautogui is None:
        return None
    try:
        x, y = pyautogui.position()
        rgb = grab_rgb_at(x, y)
        if rgb is None:
            return None
        r, g, b = rgb
        return (x, y, r, g, b)
    except Exception:
        return None
