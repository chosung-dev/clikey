# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional

from PIL import ImageGrab

def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """Safely grab RGB at screen coordinate (x,y). Returns None on failure."""
    try:
        img = ImageGrab.grab()
        r, g, b, *_ = img.getpixel((x, y))
        return (r, g, b)
    except Exception:
        return None

