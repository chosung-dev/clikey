import tkinter as tk
from tkinter import messagebox
import pyautogui
from typing import Callable

from core.screen import grab_rgb_at
from core.macro_block import MacroBlock
from core.macro_factory import MacroFactory
from ui.magnifier import Magnifier


class ConditionDialog:
    def __init__(self, parent: tk.Tk, insert_callback: Callable[[MacroBlock], None]):
        self.parent = parent
        self.insert_callback = insert_callback
        self.magnifier = None

    def add_image_condition(self):
        win = tk.Toplevel(self.parent)
        win.title("색상 조건")
        win.geometry("380x280+560+320")
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

        # Initialize magnifier
        self.magnifier = Magnifier(win, zoom_factor=10, size=200)

        def tick():
            x, y = pyautogui.position()
            pos_var.set(f"좌표: ({x}, {y})")
            rgb = grab_rgb_at(x, y)
            if rgb is None:
                rgb_var.set("RGB: (---, ---, ---)")
            else:
                r, g, b = rgb
                rgb_var.set(f"RGB: ({r}, {g}, {b})")
            win.after(120, tick)

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

        def show_magnifier():
            """Show magnifier for precise color picking."""
            def on_magnifier_click(x, y):
                rgb = grab_rgb_at(x, y)
                if rgb is None:
                    messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                    return
                r, g, b = rgb
                captured.update({"x": x, "y": y, "r": r, "g": g, "b": b})
                msg.config(text=f"캡처됨: ({x},{y}) / RGB=({r},{g},{b})")
                self.magnifier.hide()
            
            self.magnifier.show(on_magnifier_click)

        def capture_color():
            x = captured["x"]
            y = captured["y"]
            if x is None or y is None:
                messagebox.showwarning("오류", "좌표를 먼저 캡처 해 주세요")
                return
            rgb = grab_rgb_at(x, y)
            if rgb is None:
                messagebox.showwarning("오류", "화면 캡처에 실패했습니다.")
                return
            r, g, b = rgb
            captured.update({"x": x, "y": y, "r": r, "g": g, "b": b})
            msg.config(text=f"캡처됨: ({x},{y}) / RGB=({r},{g},{b})")

        def apply_block():
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표/색을 캡처하세요.")
                return
            x, y = captured['x'], captured['y']
            expected_color = f"{captured['r']},{captured['g']},{captured['b']}"
            macro_block = MacroFactory.create_if_block("color_match", x, y, expected_color)
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
            win.destroy()

        def on_escape(event):
            # If magnifier is open, close it first
            if self.magnifier and self.magnifier.running:
                self.magnifier.hide()
                return "break"
            # Otherwise close the dialog
            on_close()
            return "break"

        magnifier_frame = tk.Frame(frm)
        magnifier_frame.pack(pady=4)
        tk.Button(magnifier_frame, text="🔍 정밀 캡처", command=show_magnifier, width=20).pack()

        capture_frame = tk.Frame(frm)
        capture_frame.pack(pady=4)
        tk.Button(capture_frame, text="좌표/색 캡처 (Enter)", command=capture).grid(row=0, column=0, padx=4)
        tk.Button(capture_frame, text="고정 좌표 색 캡처", command=capture_color).grid(row=0, column=1, padx=4)

        tk.Button(frm, text="추가 (Ctrl+Enter)", command=apply_block, width=20).pack(pady=4)

        tk.Button(frm, text="취소 (Esc)", command=on_close, width=20).pack(pady=4)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Control-Return>", lambda e: apply_block())
        win.bind("<Escape>", on_escape)