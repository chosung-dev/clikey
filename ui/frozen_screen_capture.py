"""
정지 화면 캡처 - 화면을 스크린샷으로 고정한 뒤 돋보기로 정밀 색상 캡처
"""
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
from typing import Callable, Optional

# Lazy import for faster startup
_pyautogui = None

def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        _pyautogui = pyautogui
    return _pyautogui


class FrozenScreenCapture:
    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.root: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self.screenshot: Optional[Image.Image] = None
        self.callback: Optional[Callable] = None
        self.cancel_callback: Optional[Callable] = None

        self.zoom_factor = 10
        self.capture_area = 20
        self.mag_size = 200

        # Canvas item IDs
        self.bg_photo = None
        self.h_line = None
        self.v_line = None
        self.mag_photo = None
        self.mag_image_id = None
        self.mag_border_id = None
        self.info_text_id = None
        self.rgb_text_id = None
        self.rgb_shadow_id = None
        self.color_swatch_id = None

    def show(self, callback: Callable, cancel_callback: Optional[Callable] = None):
        """
        정지 화면 캡처를 시작합니다.

        Args:
            callback: 캡처 완료 시 호출 (x, y, r, g, b)
            cancel_callback: ESC 취소 시 호출
        """
        self.callback = callback
        self.cancel_callback = cancel_callback

        pyautogui = _get_pyautogui()
        self.screenshot = pyautogui.screenshot()

        sw = self.screenshot.width
        sh = self.screenshot.height

        self.root = tk.Toplevel(self.parent)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{sw}x{sh}+0+0")

        self.bg_photo = ImageTk.PhotoImage(self.screenshot)
        self.canvas = tk.Canvas(
            self.root, width=sw, height=sh,
            highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        # 안내 텍스트 (그림자 + 본문)
        guide = "클릭하여 색상을 캡처하세요 (ESC: 취소)"
        self.canvas.create_text(
            sw // 2 + 1, 31, text=guide,
            fill="black", font=("맑은 고딕", 14, "bold"), tags="guide_shadow"
        )
        self.info_text_id = self.canvas.create_text(
            sw // 2, 30, text=guide,
            fill="white", font=("맑은 고딕", 14, "bold"), tags="guide"
        )

        # 십자선 (빨간 점선)
        self.h_line = self.canvas.create_line(0, 0, sw, 0, fill="red", width=1, dash=(4, 4))
        self.v_line = self.canvas.create_line(0, 0, 0, sh, fill="red", width=1, dash=(4, 4))

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.root.bind("<Return>", lambda e: self._on_enter())
        self.root.bind("<Escape>", lambda e: self._on_cancel())
        self.root.focus_force()

    def _on_motion(self, event):
        x, y = event.x, event.y
        sw = self.screenshot.width
        sh = self.screenshot.height

        # 십자선 업데이트
        self.canvas.coords(self.h_line, 0, y, sw, y)
        self.canvas.coords(self.v_line, x, 0, x, sh)

        # 커서 주변 영역 크롭 + 확대
        half = self.capture_area // 2
        left = max(0, x - half)
        top = max(0, y - half)
        right = min(sw, left + self.capture_area)
        bottom = min(sh, top + self.capture_area)

        crop = self.screenshot.crop((left, top, right, bottom))
        zoomed = crop.resize((self.mag_size, self.mag_size), Image.NEAREST)

        # 돋보기 내 십자 마커
        draw = ImageDraw.Draw(zoomed)
        c = self.mag_size // 2
        draw.line([(c - 12, c), (c + 12, c)], fill="red", width=2)
        draw.line([(c, c - 12), (c, c + 12)], fill="red", width=2)

        self.mag_photo = ImageTk.PhotoImage(zoomed)

        # 돋보기 위치 (커서 근처, 화면 밖으로 나가지 않도록)
        mag_x = x + 30
        mag_y = y - self.mag_size - 30
        if mag_x + self.mag_size > sw:
            mag_x = x - self.mag_size - 30
        if mag_y < 0:
            mag_y = y + 30
        if mag_x < 0:
            mag_x = 10
        if mag_y + self.mag_size > sh:
            mag_y = sh - self.mag_size - 10

        # 돋보기 이미지 업데이트
        if self.mag_image_id:
            self.canvas.coords(self.mag_image_id, mag_x, mag_y)
            self.canvas.itemconfig(self.mag_image_id, image=self.mag_photo)
        else:
            self.mag_image_id = self.canvas.create_image(
                mag_x, mag_y, anchor="nw", image=self.mag_photo
            )

        # 돋보기 테두리
        if self.mag_border_id:
            self.canvas.coords(
                self.mag_border_id,
                mag_x, mag_y, mag_x + self.mag_size, mag_y + self.mag_size
            )
        else:
            self.mag_border_id = self.canvas.create_rectangle(
                mag_x, mag_y, mag_x + self.mag_size, mag_y + self.mag_size,
                outline="red", width=2
            )

        # 현재 픽셀 색상
        px = min(x, sw - 1)
        py = min(y, sh - 1)
        pixel = self.screenshot.getpixel((px, py))
        r, g, b = pixel[0], pixel[1], pixel[2]

        # 색상 견본 (돋보기 아래)
        swatch_size = 16
        swatch_x = mag_x
        swatch_y = mag_y + self.mag_size + 4
        hex_color = f"#{r:02x}{g:02x}{b:02x}"

        if self.color_swatch_id:
            self.canvas.coords(
                self.color_swatch_id,
                swatch_x, swatch_y,
                swatch_x + swatch_size, swatch_y + swatch_size
            )
            self.canvas.itemconfig(self.color_swatch_id, fill=hex_color, outline="white")
        else:
            self.color_swatch_id = self.canvas.create_rectangle(
                swatch_x, swatch_y,
                swatch_x + swatch_size, swatch_y + swatch_size,
                fill=hex_color, outline="white", width=1
            )

        # 좌표/RGB 텍스트 (그림자 + 본문)
        info = f"({x}, {y})  RGB({r}, {g}, {b})"
        text_x = swatch_x + swatch_size + 6
        text_y = swatch_y + swatch_size // 2

        if self.rgb_shadow_id:
            self.canvas.coords(self.rgb_shadow_id, text_x + 1, text_y + 1)
            self.canvas.itemconfig(self.rgb_shadow_id, text=info)
        else:
            self.rgb_shadow_id = self.canvas.create_text(
                text_x + 1, text_y + 1, text=info, anchor="w",
                fill="black", font=("맑은 고딕", 11, "bold")
            )

        if self.rgb_text_id:
            self.canvas.coords(self.rgb_text_id, text_x, text_y)
            self.canvas.itemconfig(self.rgb_text_id, text=info)
        else:
            self.rgb_text_id = self.canvas.create_text(
                text_x, text_y, text=info, anchor="w",
                fill="white", font=("맑은 고딕", 11, "bold")
            )

    def _capture_at(self, x, y):
        sw = self.screenshot.width
        sh = self.screenshot.height
        px = min(x, sw - 1)
        py = min(y, sh - 1)
        pixel = self.screenshot.getpixel((px, py))
        r, g, b = pixel[0], pixel[1], pixel[2]
        self.hide()
        if self.callback:
            self.callback(x, y, r, g, b)

    def _on_click(self, event):
        self._capture_at(event.x, event.y)

    def _on_enter(self):
        pyautogui = _get_pyautogui()
        x, y = pyautogui.position()
        self._capture_at(x, y)

    def _on_cancel(self):
        self.hide()
        if self.cancel_callback:
            self.cancel_callback()

    def hide(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
            self.canvas = None
            self.screenshot = None
            self.mag_image_id = None
            self.mag_border_id = None
            self.rgb_text_id = None
            self.rgb_shadow_id = None
            self.color_swatch_id = None
