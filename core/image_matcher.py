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
    def _load_image(template_path: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        if not os.path.exists(template_path):
            return None, None
        try:
            with open(template_path, 'rb') as f:
                nparr = np.frombuffer(f.read(), np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
            if image is None:
                image = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
        except Exception:
            image = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)

        if image is None:
            return None, None

        if len(image.shape) == 3 and image.shape[2] == 4:
            alpha = image[:, :, 3]
            bgr = image[:, :, :3].copy()
            if np.any(alpha < 255):
                mask = (alpha > 127).astype(np.uint8) * 255
                return bgr, mask
            return bgr, None

        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image[:, :, :3].copy(), None

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
        template, mask = ImageMatcher._load_image(template_path)
        if template is None:
            return None

        screenshot_bgr = ImageMatcher._take_screenshot(search_region)

        if mask is not None:
            mask_3ch = cv2.merge([mask, mask, mask])
            result = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCORR_NORMED, mask=mask_3ch)
            _, _, _, max_loc = cv2.minMaxLoc(result)

            template_h, template_w = template.shape[:2]
            y, x = max_loc[1], max_loc[0]
            if y + template_h > screenshot_bgr.shape[0] or x + template_w > screenshot_bgr.shape[1]:
                return None
            roi = screenshot_bgr[y:y + template_h, x:x + template_w]

            mask_bool = np.stack([mask > 0] * 3, axis=-1)
            t_pixels = template[mask_bool].astype(np.float64)
            r_pixels = roi[mask_bool].astype(np.float64)
            t_centered = t_pixels - t_pixels.mean()
            r_centered = r_pixels - r_pixels.mean()
            denom = np.sqrt(np.sum(t_centered ** 2) * np.sum(r_centered ** 2))
            max_val = (np.sum(t_centered * r_centered) / denom) if denom > 0 else 0.0
        else:
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
