# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional

from autoit import autoit
from PIL import ImageGrab


def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """Safely grab RGB at screen coordinate (x,y). Returns None on failure."""
    try:
        img = ImageGrab.grab()
        r, g, b = img.getpixel((x, y))
        return (r, g, b)
    except Exception:
        return None

def get_rgb_under_mouse() -> Optional[Tuple[int, int, int, int, int]]:
    """Returns (x, y, r, g, b) under current cursor, or None on failure."""
    try:
        x, y = autoit.mouse_get_pos()
        rgb = grab_rgb_at(x, y)
        if rgb is None:
            return None
        r, g, b = rgb
        return (x, y, r, g, b)
    except Exception:
        return None
