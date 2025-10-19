# core/screen.py
from __future__ import annotations
from typing import Tuple, Optional
import ctypes

def grab_rgb_at(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    """Safely grab RGB at screen coordinate (x,y) using Windows API. Returns None on failure."""
    hdc = None
    try:
        # Windows API를 사용하여 화면 DC 가져오기
        hdc = ctypes.windll.user32.GetDC(0)
        if not hdc:
            return None

        # GetPixel로 픽셀 색상 가져오기 (BGR 형식으로 반환됨)
        color = ctypes.windll.gdi32.GetPixel(hdc, x, y)

        # 오류 체크 (GetPixel은 실패 시 CLR_INVALID(0xFFFFFFFF) 반환)
        if color == 0xFFFFFFFF:
            return None

        # BGR을 RGB로 변환
        # color는 0x00BBGGRR 형식
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

