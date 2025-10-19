# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional
import ctypes


def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    hdc = None
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        if not hdc:
            return None

        color = ctypes.windll.gdi32.GetPixel(hdc, x, y)
        if color == 0xFFFFFFFF:
            return None

        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF

        return (r, g, b)
    except Exception:
        return None
    finally:
        if hdc:
            try:
                ctypes.windll.user32.ReleaseDC(0, hdc)
            except Exception:
                pass

