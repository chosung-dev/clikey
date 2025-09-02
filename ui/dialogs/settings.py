import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from core.keyboard_hotkey import KEYBOARD_AVAILABLE, normalize_key_for_keyboard


class SettingsDialog:
    def __init__(self, parent: tk.Tk, settings: dict, hotkeys: dict, 
                 mark_dirty_callback: Optional[Callable[[bool], None]] = None,
                 register_hotkeys_callback: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.settings = settings
        self.hotkeys = hotkeys
        self.mark_dirty_callback = mark_dirty_callback
        self.register_hotkeys_callback = register_hotkeys_callback
        self.window = None
        
    def open_settings(self):
        if self.window and tk.Toplevel.winfo_exists(self.window):
            self.window.lift()
            self.window.focus_force()
            return

        win = tk.Toplevel(self.parent)
        self.window = win
        win.title("설정")
        win.geometry("360x250+560+360")
        win.resizable(False, False)
        win.transient(self.parent)
        win.lift()
        win.grab_set()
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(frm, text="반복 횟수 (0=무한)").grid(row=0, column=0, sticky="w")
        self.repeat_var = tk.IntVar(value=self.settings["repeat"])
        tk.Entry(frm, width=8, textvariable=self.repeat_var).grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(frm, text="시작 지연 (초)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        start_delay_val = float(self.settings["start_delay"])
        self.delay_var = tk.StringVar(value=str(int(start_delay_val)) if start_delay_val.is_integer() else str(start_delay_val))
        tk.Entry(frm, width=8, textvariable=self.delay_var).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))

        tk.Label(frm, text="매크로 사이 간격 (초)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        step_delay_val = float(self.settings.get("step_delay", 0.01))
        self.step_delay_var = tk.StringVar(value=str(int(step_delay_val)) if step_delay_val.is_integer() else str(step_delay_val))
        tk.Entry(frm, width=8, textvariable=self.step_delay_var).grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))

        self.start_key_var = tk.StringVar(value=self.hotkeys.get("start") or "")
        self.stop_key_var = tk.StringVar(value=self.hotkeys.get("stop") or "")

        row = 3

        self.beep_var = tk.BooleanVar(value=bool(self.settings.get("beep_on_finish", True)))
        tk.Checkbutton(
            frm,
            text="매크로 종료 시 알림음 재생",
            variable=self.beep_var
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))

        row += 1
        tk.Label(frm, text="시작 단축키").grid(row=row, column=0, sticky="w", pady=(10, 0))
        start_entry = tk.Entry(frm, width=12, textvariable=self.start_key_var, state="readonly", readonlybackground="white")
        start_entry.grid(row=row, column=1, sticky="w", padx=8, pady=(10, 0))
        tk.Button(frm, text="설정", command=lambda: self._capture_hotkey("start")).grid(row=row, column=2, padx=6, pady=(10, 0))

        row += 1
        tk.Label(frm, text="중지 단축키").grid(row=row, column=0, sticky="w", pady=(6, 0))
        stop_entry = tk.Entry(frm, width=12, textvariable=self.stop_key_var, state="readonly", readonlybackground="white")
        stop_entry.grid(row=row, column=1, sticky="w", padx=8, pady=(6, 0))
        tk.Button(frm, text="설정", command=lambda: self._capture_hotkey("stop")).grid(row=row, column=2, padx=6, pady=(6, 0))

        tk.Button(frm, text="닫기", command=lambda: self.apply_and_close_settings(win)).grid(row=row + 2, column=0, columnspan=3, pady=6)

        win.bind("<Return>", lambda e: self.apply_and_close_settings(win))
        win.bind("<Escape>", lambda e: self._close_settings(win))

    def apply_and_close_settings(self, win):
        try:
            repeat = int(self.repeat_var.get())
            delay = float(self.delay_var.get())
            step_delay = float(self.step_delay_var.get())
            if repeat < 0 or delay < 0 or step_delay < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("에러", "반복 횟수와 지연 시간은 0 이상 이여야 합니다.")
            return
        
        self.settings["repeat"] = repeat
        self.settings["start_delay"] = delay
        self.settings["step_delay"] = step_delay
        self.settings["beep_on_finish"] = bool(self.beep_var.get())
        
        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)
            
        self._close_settings(win)

    def _close_settings(self, win):
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        self.window = None

    def _capture_hotkey(self, which: str):
        cap = tk.Toplevel(self.parent)
        cap.title("단축키 입력")
        cap.geometry("260x110+600+400")
        cap.transient(self.window or self.parent)
        cap.lift()
        cap.grab_set()
        cap.focus_force()

        tk.Label(cap, text="설정할 키를 한 번 눌러주세요", font=("맑은 고딕", 11)).pack(pady=10)
        tk.Label(cap, text="(ESC: 취소)").pack()

        def close_cap():
            try:
                cap.grab_release()
            except Exception:
                pass
            cap.destroy()

        def on_key(e):
            keysym = e.keysym
            key_for_keyboard = normalize_key_for_keyboard(keysym)
            if not key_for_keyboard:
                messagebox.showwarning("지원하지 않는 키", f"이 키는 전역 단축키로 설정하기 어렵습니다: {keysym}")
                return
            if which == "start":
                self.start_key_var.set(keysym)
                self.hotkeys["start"] = key_for_keyboard
            else:
                self.stop_key_var.set(keysym)
                self.hotkeys["stop"] = key_for_keyboard
                
            if self.mark_dirty_callback:
                self.mark_dirty_callback(True)
                
            if self.register_hotkeys_callback:
                self.register_hotkeys_callback()
                
            close_cap()

        cap.bind("<Key>", on_key)
        cap.bind("<Escape>", lambda e: close_cap())