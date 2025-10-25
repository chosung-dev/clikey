# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional
import ctypes

# GPU 캡처 라이브러리 시도
try:
    import mss
    import numpy as np
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False


def _grab_rgb_gpu(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """GPU 가속 (mss) 기반 색상 추출"""
    try:
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": 1, "height": 1}
            img = np.array(sct.grab(monitor))  # BGRA 포맷
            b, g, r, _ = img[0, 0]
            return int(r), int(g), int(b)
    except Exception:
        return None


def _grab_rgb_cpu(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """기존 CPU(GDI) 기반 색상 추출"""
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


def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """
    특정 좌표의 RGB 값을 가져옴.
    - GPU(mss) 사용 가능 시 빠른 버전 사용
    - 그렇지 않으면 CPU(ctypes) 버전으로 자동 fallback
    """
    if _HAS_MSS:
        color = _grab_rgb_gpu(x, y)
        if color is not None:
            return color
    # fallback
    return _grab_rgb_cpu(x, y)
