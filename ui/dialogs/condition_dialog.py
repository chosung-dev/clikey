import tkinter as tk
from tkinter import messagebox
import pyautogui

from core.screen import grab_rgb_at


class ConditionDialog:
    def __init__(self, parent: tk.Tk, listbox: tk.Listbox):
        self.parent = parent
        self.listbox = listbox

    def add_image_condition(self):
        win = tk.Toplevel(self.parent)
        win.title("이미지 조건")
        win.geometry("360x220+560+320")
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
            header = f"조건:{captured['x']},{captured['y']}={captured['r']},{captured['g']},{captured['b']}"
            self.listbox.insert(tk.END, header)
            self.listbox.insert(tk.END, "조건끝")
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        btns = tk.Frame(frm)
        btns.pack(pady=8)
        tk.Button(btns, text="좌표/색 캡처 (Enter)", command=capture).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="고정 좌표 색 캡처", command=capture_color).grid(row=0, column=1, padx=6)
        tk.Button(frm, text="추가 (Ctrl+Enter)", command=apply_block).pack(pady=4)
        tk.Button(frm, text="취소 (Esc)", command=lambda: (win.grab_release(), win.destroy())).pack(pady=4)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Control-Return>", lambda e: apply_block())
        win.bind("<Escape>", lambda e: (win.grab_release(), win.destroy()))