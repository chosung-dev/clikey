from typing import Optional, Tuple
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
    def virtual_screen() -> Tuple[int, int, int, int]:
        """모든 모니터를 감싸는 사각형 (왼쪽, 위, 너비, 높이).

        주 모니터 위나 왼쪽에 다른 모니터가 있으면 왼쪽·위가 음수다.
        """
        get = windll.user32.GetSystemMetrics
        return (get(win32con.SM_XVIRTUALSCREEN), get(win32con.SM_YVIRTUALSCREEN),
                get(win32con.SM_CXVIRTUALSCREEN), get(win32con.SM_CYVIRTUALSCREEN))

    @staticmethod
    def _take_screenshot(region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        hdesktop = win32gui.GetDesktopWindow()
        left, top, width, height = ImageMatcher.virtual_screen()

        if region:
            x1, y1, x2, y2 = region
            # 화면 왼쪽·위가 음수일 수 있다. 0 으로 자르면 주 모니터 위나
            # 왼쪽에 있는 모니터의 범위가 통째로 어긋난다.
            x1, y1 = max(left, x1), max(top, y1)
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
        # 찍은 그림의 왼쪽 위가 화면 좌표 어디인지. 범위를 주지 않았다면 그것은
        # (0, 0) 이 아니라 모든 모니터를 감싸는 사각형의 왼쪽 위다.
        if search_region:
            offset_x, offset_y = search_region[0], search_region[1]
        else:
            offset_x, offset_y, _, _ = ImageMatcher.virtual_screen()
        center_x = max_loc[0] + template_w // 2 + offset_x
        center_y = max_loc[1] + template_h // 2 + offset_y

        del template, screenshot_bgr, result

        return center_x, center_y
