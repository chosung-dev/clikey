from typing import Optional, Tuple, Dict, Any
import os
import cv2
import numpy as np
import win32gui
import win32ui
import win32con
from ctypes import windll


class ImageMatcher:
    @staticmethod
    def _load_image(template_path: str) -> Optional[np.ndarray]:
        if not os.path.exists(template_path):
            return None
        try:
            with open(template_path, 'rb') as f:
                nparr = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return image
        except Exception:
            return cv2.imread(template_path, cv2.IMREAD_COLOR)

    @staticmethod
    def _take_screenshot(region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        hdesktop = win32gui.GetDesktopWindow()
        left = windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width = windll.user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = windll.user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)

        if region:
            x1, y1, x2, y2 = region
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(x2, left + width), min(y2, top + height)
            capture_left, capture_top = x1, y1
            capture_width, capture_height = x2 - x1, y2 - y1
        else:
            capture_left, capture_top = left, top
            capture_width, capture_height = width, height

        desktop_dc = win32gui.GetWindowDC(hdesktop)
        img_dc = win32ui.CreateDCFromHandle(desktop_dc)
        mem_dc = img_dc.CreateCompatibleDC()

        screenshot_bmp = win32ui.CreateBitmap()
        screenshot_bmp.CreateCompatibleBitmap(img_dc, capture_width, capture_height)
        mem_dc.SelectObject(screenshot_bmp)

        mem_dc.BitBlt((0, 0), (capture_width, capture_height), img_dc,
                      (capture_left, capture_top), win32con.SRCCOPY)

        bmpinfo = screenshot_bmp.GetInfo()
        bmpstr = screenshot_bmp.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8)
        img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)

        screenshot_bgr = img[:, :, :3].copy()

        mem_dc.DeleteDC()
        win32gui.DeleteObject(screenshot_bmp.GetHandle())
        img_dc.DeleteDC()
        win32gui.ReleaseDC(hdesktop, desktop_dc)

        return screenshot_bgr

    @staticmethod
    def find_image_on_screen(
        template_path: str,
        threshold: float = 0.9,
        search_region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        template = ImageMatcher._load_image(template_path)
        if template is None:
            return None

        screenshot_bgr = ImageMatcher._take_screenshot(search_region)

        result = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < threshold:
            return None

        template_h, template_w = template.shape[:2]
        offset_x, offset_y = (search_region[0], search_region[1]) if search_region else (0, 0)
        center_x = max_loc[0] + template_w // 2 + offset_x
        center_y = max_loc[1] + template_h // 2 + offset_y

        del template, screenshot_bgr, result

        return center_x, center_y

    @staticmethod
    def create_context_data(template_path: str, center_pos: Tuple[int, int]) -> Dict[str, Any]:
        name_without_ext = os.path.splitext(os.path.basename(template_path))[0]
        return {
            "name": name_without_ext,
            "x": center_pos[0],
            "y": center_pos[1],
            "template_path": template_path
        }
