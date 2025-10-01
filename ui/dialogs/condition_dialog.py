import tkinter as tk
from tkinter import messagebox, filedialog
import pyautogui
from typing import Callable, Optional, Tuple
import os
import tempfile
from PIL import Image, ImageTk

from core.screen import grab_rgb_at
from core.macro_block import MacroBlock
from core.macro_factory import MacroFactory
from ui.magnifier import Magnifier


class ConditionDialog:
    def __init__(self, parent: tk.Tk, insert_callback: Callable[[MacroBlock], None], is_edit_mode_callback: Callable[[], bool] = None, cancel_edit_callback: Callable[[], None] = None, scale_factor: float = 1.0):
        self.parent = parent
        self.insert_callback = insert_callback
        self.is_edit_mode_callback = is_edit_mode_callback
        self.cancel_edit_callback = cancel_edit_callback

        # 화면이 작을수록 창을 더 크게
        if scale_factor < 0.8:
            self.window_scale = 1.5
        elif scale_factor < 1.0:
            self.window_scale = 1.2
        else:
            self.window_scale = 1.0

        self.magnifier = None
        self.macro_list = None  # 매크로 리스트에 대한 참조를 저장
        self.edit_block = None  # 편집할 블록 저장

    def set_macro_list(self, macro_list):
        """매크로 리스트 참조를 설정"""
        self.macro_list = macro_list

    def set_edit_block(self, block):
        """편집할 블록 설정"""
        self.edit_block = block

    def find_parent_coordinate_condition(self) -> Optional[Tuple[int, int]]:
        """Find the nearest parent coordinate condition and return its coordinates."""
        try:
            from core.event_types import ConditionType

            if not self.macro_list:
                return None

            if not hasattr(self.macro_list, 'get_selected_indices'):
                return None

            selected_indices = self.macro_list.get_selected_indices()
            if not selected_indices:
                return None

            current_index = selected_indices[0]

            # flat_blocks 속성 사용
            if not hasattr(self.macro_list, 'flat_blocks'):
                return None

            flat_blocks = self.macro_list.flat_blocks

            # 먼저 현재 선택된 블록이 좌표 조건인지 확인
            if current_index < len(flat_blocks):
                current_block, current_depth = flat_blocks[current_index]
                if (hasattr(current_block, 'event_type') and current_block.event_type.value == "if" and
                    hasattr(current_block, 'condition_type') and
                    current_block.condition_type == ConditionType.COORDINATE_CONDITION):
                    coords = current_block.parse_position()
                    if coords:
                        return coords

            # 현재 선택된 블록이 좌표 조건이 아니면, 역방향으로 검색
            for i in range(current_index - 1, -1, -1):
                if i < len(flat_blocks):
                    block, depth = flat_blocks[i]
                    if (hasattr(block, 'event_type') and block.event_type.value == "if" and
                        hasattr(block, 'condition_type') and
                        block.condition_type == ConditionType.COORDINATE_CONDITION):
                        coords = block.parse_position()
                        if coords:
                            return coords

            return None

        except Exception as e:
            print(f"Error finding parent coordinate condition: {e}")
            return None

    def add_image_condition(self):
        win = tk.Toplevel(self.parent)
        win.title("색상 조건")
        w = int(380 * self.window_scale)
        h = int(280 * self.window_scale)
        win.geometry(f"{w}x{h}+560+320")
        win.resizable(False, False)
        win.transient(self.parent)
        win.lift()
        win.grab_set()
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10)
        frm.pack(fill="both", expand=True)

        msg = tk.Label(frm, text="커서를 원하는 위치로 옮긴 뒤\n[좌표/색 캡처] 또는 Enter 키를 누르세요.", justify="center")
        msg.pack(pady=4)

        pos_var = tk.StringVar(value="좌표: (---, ---)")
        rgb_var = tk.StringVar(value="RGB: (---, ---, ---)")
        tk.Label(frm, textvariable=pos_var).pack()
        tk.Label(frm, textvariable=rgb_var).pack()

        captured = {"x": None, "y": None, "r": None, "g": None, "b": None}
        parent_coords = self.find_parent_coordinate_condition()
        is_parent_mode = {"enabled": False}

        # Magnifier will be initialized when needed (lazy loading)
        self.magnifier = None

        def tick():
            if not is_parent_mode["enabled"]:
                x, y = pyautogui.position()
                pos_var.set(f"좌표: ({x}, {y})")
                rgb = grab_rgb_at(x, y)
                if rgb is None:
                    rgb_var.set("RGB: (---, ---, ---)")
                else:
                    r, g, b = rgb
                    rgb_var.set(f"RGB: ({r}, {g}, {b})")
            win.after(200, tick)

        tick()

        def capture():
            x, y = pyautogui.position()
            rgb = grab_rgb_at(x, y)
            if rgb is None:
                messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                return
            r, g, b = rgb
            captured.update({"x": x, "y": y, "r": r, "g": g, "b": b})
            msg.config(text=f"캡처됨: ({x},{y}) / RGB=({r},{g},{b})")
            is_parent_mode["enabled"] = False

        def show_magnifier():
            """Show magnifier for precise color picking."""
            # Initialize magnifier only when needed
            if self.magnifier is None:
                self.magnifier = Magnifier(win, zoom_factor=10, size=200)

            def on_magnifier_click(x, y):
                rgb = grab_rgb_at(x, y)
                if rgb is None:
                    messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                    return
                r, g, b = rgb
                captured.update({"x": x, "y": y, "r": r, "g": g, "b": b})
                msg.config(text=f"캡처됨: ({x},{y}) / RGB=({r},{g},{b})")
                is_parent_mode["enabled"] = False
                self.magnifier.hide()

            self.magnifier.show(on_magnifier_click)

        def capture_parent_coordinates():
            """상위좌표 버튼 클릭 시 - 상위 좌표 조건의 좌표로 고정"""
            if parent_coords:
                x, y = parent_coords
                captured.update({"x": x, "y": y})
                pos_var.set(f"좌표: ({x}, {y}) [상위좌표 고정]")
                msg.config(text=f"상위좌표로 고정됨: ({x},{y})\n고정 좌표 색 캡처를 눌러 색상을 캡처하세요.")
                is_parent_mode["enabled"] = True
            else:
                messagebox.showwarning("오류", "상위 좌표 조건을 찾을 수 없습니다.")

        def capture_color():
            """고정 좌표 색 캡처 - 캡처된 좌표에서 색상만 다시 캡처"""
            x = captured["x"]
            y = captured["y"]
            if x is None or y is None:
                messagebox.showwarning("오류", "먼저 좌표를 캡처하거나 상위좌표를 선택해주세요.")
                return
            rgb = grab_rgb_at(x, y)
            if rgb is None:
                messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                return
            r, g, b = rgb
            captured.update({"r": r, "g": g, "b": b})
            rgb_var.set(f"RGB: ({r}, {g}, {b})")
            if is_parent_mode["enabled"]:
                msg.config(text=f"상위좌표 색상 캡처됨: ({x},{y}) / RGB=({r},{g},{b})")
            else:
                msg.config(text=f"색상 재캡처됨: ({x},{y}) / RGB=({r},{g},{b})")

        def apply_block():
            """추가 버튼 - 상위좌표 모드인지에 따라 다른 조건 생성"""
            if captured["r"] is None:
                messagebox.showwarning("안내", "먼저 색상을 캡처하세요.")
                return

            expected_color = f"{captured['r']},{captured['g']},{captured['b']}"

            # 상위좌표 모드인 경우 @parent 참조 조건 생성
            if is_parent_mode["enabled"]:
                macro_block = MacroFactory.create_rgb_match_with_parent_block(expected_color)
            else:
                # 일반 모드인 경우 좌표와 색상 모두 필요
                if captured["x"] is None:
                    messagebox.showwarning("안내", "먼저 좌표와 색상을 캡처하세요.")
                    return
                x, y = captured['x'], captured['y']
                macro_block = MacroFactory.create_rgb_match_block(x, y, expected_color)

            # 편집 모드인 경우 기존 블록의 macro_blocks 보존
            if self.is_edit_mode_callback and self.is_edit_mode_callback() and self.edit_block:
                macro_block.macro_blocks = self.edit_block.macro_blocks.copy()
                macro_block.key = self.edit_block.key  # 기존 키도 유지

            self.insert_callback(macro_block)
            try:
                win.grab_release()
            except Exception:
                pass
            if self.magnifier:
                self.magnifier.hide()
            win.destroy()

        def on_close():
            try:
                win.grab_release()
            except Exception:
                pass
            if self.magnifier:
                self.magnifier.hide()
            # 편집 모드 취소
            if self.cancel_edit_callback:
                self.cancel_edit_callback()
            win.destroy()

        def on_escape(event):
            # If magnifier is open, close it first
            if self.magnifier and self.magnifier.running:
                self.magnifier.hide()
                return "break"
            # Otherwise close the dialog
            on_close()
            return "break"

        # 1. 정밀 캡처
        tk.Button(frm, text="정밀 캡처", command=show_magnifier, width=30).pack(pady=2)

        # 2. 좌표/색 캡처
        tk.Button(frm, text="좌표/색 캡처 (Enter)", command=capture, width=30).pack(pady=2)

        # 상위좌표 버튼 임시 주석처리
        # capture_frame = tk.Frame(frm)
        # capture_frame.pack(pady=2)
        # tk.Button(capture_frame, text="좌표/색 캡처 (Enter)", command=capture, width=14).grid(row=0, column=0, padx=2)
        # parent_btn = tk.Button(capture_frame, text="상위좌표", command=capture_parent_coordinates, width=14)
        # parent_btn.grid(row=0, column=1, padx=2)
        # if not parent_coords:
        #     parent_btn.config(state=tk.DISABLED)

        # 3. 고정 좌표 색 캡처
        tk.Button(frm, text="고정 좌표 색 캡처", command=capture_color, width=30).pack(pady=2)

        # 4. 추가/수정
        button_text = "수정 (Ctrl+Enter)" if self.is_edit_mode_callback and self.is_edit_mode_callback() else "추가 (Ctrl+Enter)"
        tk.Button(frm, text=button_text, command=apply_block, width=30).pack(pady=2)

        # 5. 취소
        tk.Button(frm, text="취소 (Esc)", command=on_close, width=30).pack(pady=2)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Control-Return>", lambda e: apply_block())
        win.bind("<Escape>", on_escape)

        # X버튼 클릭 시에도 편집 모드 해제
        win.protocol("WM_DELETE_WINDOW", on_close)

    def add_image_match_condition(self):
        win = tk.Toplevel(self.parent)
        win.title("이미지 조건")
        w = int(400 * self.window_scale)
        h = int(350 * self.window_scale)
        win.geometry(f"{w}x{h}+560+320")
        win.resizable(False, False)
        win.transient(self.parent)
        win.lift()
        win.grab_set()
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10)
        frm.pack(fill="both", expand=True)

        msg = tk.Label(frm, text="매칭할 이미지를 선택하거나 클립보드에서 붙여넣으세요.", justify="center", font=("맑은 고딕", 11))
        msg.pack(pady=10)

        selected_file = {"path": None}
        file_label = tk.Label(frm, text="선택된 파일: 없음", fg="gray", wraplength=350, justify="left")
        file_label.pack(pady=5)

        # 이미지 미리보기 프레임
        preview_frame = tk.Frame(frm)
        preview_frame.pack(pady=5)
        preview_label = tk.Label(preview_frame, text="", bg="white", relief="sunken")
        preview_label.pack(fill=tk.BOTH, expand=True)

        # 고정 크기 설정
        preview_frame.configure(width=280, height=150)
        preview_frame.pack_propagate(False)

        def select_file():
            file_path = filedialog.askopenfilename(
                title="이미지 파일 선택",
                filetypes=[
                    ("이미지 파일", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif"),
                    ("PNG 파일", "*.png"),
                    ("JPEG 파일", "*.jpg *.jpeg"),
                    ("모든 파일", "*.*")
                ]
            )
            if file_path:
                selected_file["path"] = file_path
                filename = os.path.basename(file_path)
                file_label.config(text=f"선택된 파일: {filename}", fg="blue")
                self.show_image_preview(file_path, preview_label)

        def paste_from_clipboard():
            success = False

            # 방법 1: PIL의 ImageGrab 시도
            try:
                from PIL import ImageGrab
                img = ImageGrab.grabclipboard()
                if img:
                    # 프로그램 폴더의 images 디렉토리에 저장
                    import time
                    # 프로그램 루트 디렉토리 찾기
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    program_root = os.path.dirname(os.path.dirname(current_dir))  # ui/dialogs에서 두 단계 위로
                    images_dir = os.path.join(program_root, "images")

                    # images 디렉토리가 없으면 생성
                    os.makedirs(images_dir, exist_ok=True)

                    timestamp = int(time.time() * 1000000)  # 마이크로초까지 포함
                    temp_path = os.path.join(images_dir, f"clipboard_image_{timestamp}.png")
                    img.save(temp_path)

                    selected_file["path"] = temp_path
                    file_label.config(text="선택된 파일: 클립보드에서 붙여넣기", fg="green")
                    self.show_image_preview(temp_path, preview_label)
                    success = True
                else:
                    messagebox.showinfo("알림", "클립보드에 이미지가 없습니다.")
                    return
            except ImportError:
                pass
            except Exception as e:
                print(f"PIL ImageGrab 실패: {e}")

            if success:
                return

            try:
                import win32clipboard
                from PIL import Image
                import io

                win32clipboard.OpenClipboard()
                try:
                    # CF_DIB 형식 확인
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                        data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
                        # 이 부분은 복잡한 DIB 파싱이 필요하므로 생략
                        messagebox.showinfo("안내", "현재 클립보드 형식은 지원되지 않습니다.\n이미지를 파일로 저장한 후 '파일 선택' 버튼을 사용해주세요.")
                    else:
                        messagebox.showinfo("알림", "클립보드에 이미지가 없습니다.")
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                messagebox.showinfo("안내", "클립보드 기능을 사용하려면 pywin32가 필요합니다.\n'pip install pywin32'로 설치하세요.")
            except Exception as e:
                messagebox.showerror("오류", f"클립보드 접근 중 오류 발생: {str(e)}")


        def apply_block():
            if not selected_file["path"]:
                messagebox.showwarning("안내", "먼저 이미지 파일을 선택하거나 클립보드에서 붙여넣으세요.")
                return

            try:
                macro_block = MacroFactory.create_image_match_block(selected_file["path"])

                # 편집 모드인 경우 기존 블록의 macro_blocks 보존
                if self.is_edit_mode_callback and self.is_edit_mode_callback() and self.edit_block:
                    macro_block.macro_blocks = self.edit_block.macro_blocks.copy()
                    macro_block.key = self.edit_block.key  # 기존 키도 유지

                self.insert_callback(macro_block)
                on_close()
            except Exception as e:
                messagebox.showerror("오류", f"이미지 조건 블록 생성 중 오류가 발생했습니다: {str(e)}")

        def on_close():
            try:
                win.grab_release()
            except Exception:
                pass
            # 편집 모드 취소
            if self.cancel_edit_callback:
                self.cancel_edit_callback()
            win.destroy()

        def on_paste_key(event):
            """Ctrl+V 키 바인딩"""
            paste_from_clipboard()
            return "break"

        btn_frame = tk.Frame(frm)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="파일 선택", command=select_file, width=29).grid(row=0, column=0, columnspan=2, padx=5)

        # 편집 모드에 따라 버튼 텍스트 결정
        button_text = "수정" if self.is_edit_mode_callback and self.is_edit_mode_callback() else "추가"

        tk.Button(btn_frame, text=button_text, command=apply_block, width=12).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="취소", command=on_close, width=12).grid(row=1, column=1, padx=5, pady=5)

        win.bind("<Escape>", lambda e: on_close())
        win.bind("<Control-v>", on_paste_key)

        # X버튼 클릭 시에도 편집 모드 해제
        win.protocol("WM_DELETE_WINDOW", on_close)

    def show_image_preview(self, image_path, preview_label):
        """이미지 미리보기 표시"""
        try:
            # PIL로 이미지 로드 및 리사이즈
            with Image.open(image_path) as img:
                # 비율 유지하면서 300x200 안에 맞추기
                img.thumbnail((300, 200), Image.Resampling.LANCZOS)

                # tkinter에서 사용할 수 있는 형태로 변환
                photo = ImageTk.PhotoImage(img)

                # 레이블에 이미지 표시
                preview_label.configure(image=photo, text="")
                preview_label.image = photo  # 참조 유지 (가비지 컬렉션 방지)

        except Exception as e:
            preview_label.configure(image="", text=f"미리보기 오류:\n{str(e)}")
            preview_label.image = None

    def add_coordinate_condition(self):
        """Add coordinate condition dialog."""
        win = tk.Toplevel(self.parent)
        win.title("좌표 조건")
        win.geometry("380x200+560+320")
        win.resizable(False, False)
        win.transient(self.parent)
        win.lift()
        win.grab_set()
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10)
        frm.pack(fill="both", expand=True)

        msg = tk.Label(frm, text="커서를 원하는 위치로 옮긴 뒤\n[좌표 캡처] 또는 Enter 키를 누르세요.", justify="center")
        msg.pack(pady=4)

        pos_var = tk.StringVar(value="좌표: (---, ---)")
        tk.Label(frm, textvariable=pos_var).pack()

        captured = {"x": None, "y": None}

        def tick():
            x, y = pyautogui.position()
            pos_var.set(f"좌표: ({x}, {y})")
            win.after(200, tick)

        tick()

        def capture():
            x, y = pyautogui.position()
            captured.update({"x": x, "y": y})
            msg.config(text=f"캡처됨: ({x},{y})")

        def apply_block():
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표를 캡처하세요.")
                return
            x, y = captured['x'], captured['y']
            macro_block = MacroFactory.create_coordinate_condition_block(x, y)

            # 편집 모드인 경우 기존 블록의 macro_blocks 보존
            if self.is_edit_mode_callback and self.is_edit_mode_callback() and self.edit_block:
                macro_block.macro_blocks = self.edit_block.macro_blocks.copy()
                macro_block.key = self.edit_block.key  # 기존 키도 유지

            self.insert_callback(macro_block)
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def on_close():
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        capture_frame = tk.Frame(frm)
        capture_frame.pack(pady=4)
        tk.Button(capture_frame, text="좌표 캡처 (Enter)", command=capture, width=20).pack()

        tk.Button(frm, text="추가 (Ctrl+Enter)", command=apply_block, width=20).pack(pady=4)

        tk.Button(frm, text="취소 (Esc)", command=on_close, width=20).pack(pady=4)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Control-Return>", lambda e: apply_block())
        win.bind("<Escape>", lambda e: on_close())