"""
화면 영역 선택 오버레이 위젯
Windows + Shift + S와 유사한 화면 영역 선택 기능을 제공합니다.
"""
import tkinter as tk
from typing import Callable, Optional, Tuple

# Lazy import for faster startup
_pyautogui = None

def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        _pyautogui = pyautogui
    return _pyautogui


class ScreenRegionSelector:
    def __init__(self, callback: Callable[[int, int, int, int], None]):
        """
        Args:
            callback: 영역 선택 완료 시 호출될 콜백 함수 (x1, y1, x2, y2)
        """
        self.callback = callback
        self.root: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self.start_x: Optional[int] = None
        self.start_y: Optional[int] = None
        self.rect_id: Optional[int] = None
        self.is_selecting = False

    def show(self):
        """화면 영역 선택 오버레이 표시"""
        # 전체 화면 크기 가져오기
        pyautogui = _get_pyautogui()
        screen_width, screen_height = pyautogui.size()

        # 투명한 전체 화면 윈도우 생성
        self.root = tk.Toplevel()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.3)  # 반투명
        self.root.configure(bg='black')
        self.root.overrideredirect(True)  # 창 테두리 제거

        # 캔버스 생성
        self.canvas = tk.Canvas(
            self.root,
            width=screen_width,
            height=screen_height,
            bg='black',
            highlightthickness=0,
            cursor='crosshair'
        )
        self.canvas.pack()

        # 안내 텍스트
        info_text = "드래그하여 영역을 선택하세요 (ESC: 취소)"
        self.canvas.create_text(
            screen_width // 2,
            30,
            text=info_text,
            fill='white',
            font=('맑은 고딕', 16, 'bold')
        )

        # 이벤트 바인딩
        self.canvas.bind('<ButtonPress-1>', self._on_mouse_down)
        self.canvas.bind('<B1-Motion>', self._on_mouse_move)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
        self.root.bind('<Escape>', self._on_escape)

        # 포커스 설정
        self.root.focus_force()

    def _on_mouse_down(self, event):
        """마우스 버튼 누름"""
        self.start_x = event.x
        self.start_y = event.y
        self.is_selecting = True

        # 기존 사각형이 있으면 삭제
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _on_mouse_move(self, event):
        """마우스 드래그"""
        if not self.is_selecting:
            return

        # 기존 사각형 삭제
        if self.rect_id:
            self.canvas.delete(self.rect_id)

        # 새 사각형 그리기 (밝은 색상으로 선택 영역 표시)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            event.x, event.y,
            outline='red',
            width=2,
            fill='white',
            stipple='gray50'  # 반투명 효과
        )

    def _on_mouse_up(self, event):
        """마우스 버튼 뗌 - 영역 선택 완료"""
        if not self.is_selecting:
            return

        self.is_selecting = False
        end_x = event.x
        end_y = event.y

        # 좌표 정규화 (왼쪽 위가 시작점, 오른쪽 아래가 끝점이 되도록)
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # 너무 작은 영역은 무시 (최소 10x10 픽셀)
        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            self.hide()
            return

        # 콜백 호출
        self.callback(x1, y1, x2, y2)
        self.hide()

    def _on_escape(self, event):
        """ESC 키 - 취소"""
        self.hide()

    def hide(self):
        """오버레이 숨기기"""
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
            self.canvas = None
            self.rect_id = None
            self.start_x = None
            self.start_y = None
            self.is_selecting = False
