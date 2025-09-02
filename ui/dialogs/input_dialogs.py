import tkinter as tk
from tkinter import messagebox, simpledialog
import pyautogui
from typing import Callable, Optional

from core.screen import grab_rgb_at


class InputDialogs:
    def __init__(self, parent: tk.Tk, insert_callback: Callable[[str], None]):
        self.parent = parent
        self.insert_callback = insert_callback

    def add_keyboard(self):
        key_window = tk.Toplevel(self.parent)
        key_window.geometry("320x190+520+320")

        frame = tk.Frame(key_window, bd=2, relief=tk.RAISED)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="원하는 키를 눌러주세요", font=("맑은 고딕", 12)).pack(pady=6)

        action_var = tk.StringVar(value="press")
        tk.Radiobutton(frame, text="누르기 (press)", variable=action_var, value="press").pack(anchor="w", padx=10)
        tk.Radiobutton(frame, text="누르고 있기 (down)", variable=action_var, value="down").pack(anchor="w", padx=10)
        tk.Radiobutton(frame, text="떼기 (up)", variable=action_var, value="up").pack(anchor="w", padx=10)

        tk.Button(frame, text="취소", command=key_window.destroy).pack(pady=8)

        def on_key(event):
            key = event.keysym
            action = action_var.get()
            line = f"키보드:{key}:{action}"
            self.insert_callback(line)
            key_window.destroy()

        key_window.bind("<Key>", on_key)
        key_window.focus_set()

    def add_mouse(self):
        mouse_win = tk.Toplevel(self.parent)
        mouse_win.title("마우스 입력")
        mouse_win.geometry("400x330+540+320")
        mouse_win.resizable(False, False)

        mouse_win.transient(self.parent)
        mouse_win.lift()
        mouse_win.attributes("-topmost", True)
        mouse_win.grab_set()
        mouse_win.focus_force()
        mouse_win.bind("<Map>", lambda e: mouse_win.focus_force())
        mouse_win.after(200, lambda: mouse_win.attributes("-topmost", False))

        frame = tk.Frame(mouse_win, bd=2, relief=tk.RAISED)
        frame.pack(expand=True, fill="both", padx=6, pady=6)
        frame.focus_set()

        info = tk.Label(frame, text="커서를 원하는 위치로 옮긴 뒤\n[좌표 캡처] 또는 Enter 키를 누르세요.", justify="center")
        info.pack(pady=4)

        pos_var = tk.StringVar(value="현재 좌표: (---, ---)")
        tk.Label(frame, textvariable=pos_var, font=("맑은 고딕", 11)).pack(pady=4)

        # 버튼 타입 선택
        btn_var = tk.StringVar(value="left")
        btn_frame = tk.LabelFrame(frame, text="버튼 타입", font=("맑은 고딕", 10))
        btn_frame.pack(pady=6, padx=10, fill="x")

        tk.Radiobutton(btn_frame, text="왼쪽", variable=btn_var, value="left").grid(row=0, column=0, sticky="w", padx=5)
        tk.Radiobutton(btn_frame, text="오른쪽", variable=btn_var, value="right").grid(row=0, column=1, sticky="w", padx=5)
        tk.Radiobutton(btn_frame, text="가운데", variable=btn_var, value="middle").grid(row=0, column=2, sticky="w",
                                                                                     padx=5)
        # 동작 타입 선택
        action_var = tk.StringVar(value="click")
        action_frame = tk.LabelFrame(frame, text="동작 타입", font=("맑은 고딕", 10))
        action_frame.pack(pady=6, padx=10, fill="x")
        
        tk.Radiobutton(action_frame, text="좌표 클릭", variable=action_var, value="click").grid(row=0, column=0, sticky="w", padx=5)
        tk.Radiobutton(action_frame, text="좌표로 이동하기", variable=action_var, value="move").grid(row=0, column=1, sticky="w", padx=5)
        tk.Radiobutton(action_frame, text="누르고있기", variable=action_var, value="down").grid(row=1, column=0, sticky="w", padx=5)
        tk.Radiobutton(action_frame, text="떼기", variable=action_var, value="up").grid(row=1, column=1, sticky="w", padx=5)



        captured = {"x": None, "y": None}

        def update_ui_state():
            """동작 타입에 따라 UI 상태 업데이트"""
            action = action_var.get()
            
            if action == "move":
                # 이동하기: 버튼 타입 비활성화
                for widget in btn_frame.winfo_children():
                    widget.configure(state="disabled")
                info.config(text="커서를 원하는 위치로 옮긴 뒤\n[좌표 캡처] 또는 Enter 키를 누르세요.")
            elif action in ("down", "up"):
                # 누르고있기/떼기: 버튼 타입 활성화, 좌표 캡처 불필요
                for widget in btn_frame.winfo_children():
                    widget.configure(state="normal")
                if action == "down":
                    info.config(text="현재 마우스 위치에서\n선택한 버튼을 누르고 유지합니다.")
                else:
                    info.config(text="현재 마우스 위치에서\n선택한 버튼을 뗍니다.")
            else:  # action == "click"
                # 클릭: 모든 요소 활성화
                for widget in btn_frame.winfo_children():
                    widget.configure(state="normal")
                info.config(text="커서를 원하는 위치로 옮긴 뒤\n[좌표 캡처] 또는 Enter 키를 누르세요.")
        
        # 동작 타입 변경 시 UI 상태 업데이트
        for widget in action_frame.winfo_children():
            if isinstance(widget, tk.Radiobutton):
                widget.configure(command=update_ui_state)
        
        # 초기 상태 설정
        update_ui_state()

        def tick():
            x, y = pyautogui.position()
            pos_var.set(f"현재 좌표: ({x}, {y})")
            mouse_win.after(80, tick)

        tick()

        def capture():
            x, y = pyautogui.position()
            rgb = grab_rgb_at(x, y)
            if rgb is None:
                messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                return
            r, g, b = rgb
            captured.update({"x": x, "y": y, "r": r, "g": g, "b": b})
            info.config(text=f"캡처됨: ({x}, {y}) / RGB=({r},{g},{b})")

        def add_item():
            action = action_var.get()
            button = btn_var.get()
            
            # 누르고있기와 떼기는 좌표가 필요없음 (현재 위치에서 동작)
            if action in ("down", "up"):
                if action == "down":
                    line = f"마우스:누름:{button}"
                else:  # action == "up"
                    line = f"마우스:떼기:{button}"
                self.insert_callback(line)
                on_close()
                return
            
            # 클릭과 이동하기는 좌표가 필요함
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표를 캡처하세요.")
                return
                
            x, y = captured['x'], captured['y']
            if action == "click":
                line = f"마우스:{x},{y}:{button}"
            elif action == "move":
                line = f"마우스:{x},{y}:이동"
            else:
                # 기본값
                line = f"마우스:{x},{y}:{button}"
                
            self.insert_callback(line)
            on_close()

        def on_close():
            try:
                mouse_win.grab_release()
            except Exception:
                pass
            mouse_win.destroy()

        mouse_win.bind("<Return>", lambda e: capture())
        mouse_win.bind("<Control-Return>", lambda e: add_item())
        mouse_win.bind("<Escape>", lambda e: on_close())

        btns = tk.Frame(frame)
        btns.pack(pady=10)
        tk.Button(btns, text="좌표 캡처 (Enter)", width=16, command=capture).grid(row=0, column=0, padx=5)
        tk.Button(btns, text="추가 (Ctrl+Enter)", width=16, command=add_item).grid(row=0, column=1, padx=5)
        tk.Button(frame, text="취소 (Esc)", command=on_close).pack(pady=6)

    def add_delay(self):
        sec = simpledialog.askfloat("대기 시간", "대기할 초를 입력하세요:", minvalue=0, maxvalue=3600)
        if sec:
            line = f"시간:{sec}"
            self.insert_callback(line)