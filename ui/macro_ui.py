import os
import threading
import time
import json
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog

import pyautogui
from ui.styled_list import StyledList

from core.state import default_settings, default_hotkeys
from core.keyboard_hotkey import (
    KEYBOARD_AVAILABLE,
    register_hotkeys,
    normalize_key_for_keyboard,
)
from core.mouse import mouse_move_click
from core.screen import grab_rgb_at
from core.persistence import is_valid_macro_line, export_data, load_app_state, save_app_state


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02

# =================================== MacroUI ===================================
class MacroUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Namaan's Macro")
        self.root.geometry("500x450")

        # 상태
        self.running = False
        self.stop_flag = False
        self.worker_thread = None
        self.settings_window = None
        self._drag_moved = False
        self._drop_preview_insert_at = None

        # 설정/단축키
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        self.hotkey_handles = {"start": None, "stop": None}

        # 파일 상태
        self.current_path: str | None = None
        self.is_dirty: bool = False

        self._build_menu()
        self._build_layout()
        self._bind_events()
        self._register_hotkeys_if_available()
        self._restore_last_file()

    # ---------- UI 빌드 ----------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="새로 만들기", command=self.new_file)
        file_menu.add_command(label="저장하기", command=self.save_file)
        file_menu.add_command(label="새로 저장하기", command=self.save_file_as)
        file_menu.add_command(label="불러오기", command=self.load_file)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.request_quit)
        menubar.add_cascade(label="파일", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="환경 설정", command=self.open_settings)
        menubar.add_cascade(label="설정", menu=settings_menu)

        self.root.config(menu=menubar)

    def _build_layout(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(main_frame, bd=2, relief=tk.GROOVE)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)

        left_frame = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.macro_listbox = StyledList(
            left_frame,
            split_cb=self._split_raw_desc,
            join_cb=self._join_raw_desc,
            desc_color="#1a7f37",
        )
        self.macro_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._inline_edit_entry = None
        self.macro_listbox.bind("<Double-Button-1>", self._begin_desc_inline_edit, add="+")

        self._drag_start_index = None
        self._drag_preview_index = None
        self._clipboard = []
        self._clipboard_is_block = False

        self.macro_listbox.bind("<Button-1>", self._on_drag_start, add="+")
        self.macro_listbox.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.macro_listbox.bind("<ButtonRelease-1>", self._on_drag_release, add="+")

        self._insert_bar = tk.Frame(self.root, height=2, bd=0, highlightthickness=0)
        self._insert_bar.place_forget()
        self._insert_line_visible = False

        self.root.bind("<Control-c>", self._on_copy)
        self.root.bind("<Control-x>", self._on_cut)
        self.root.bind("<Control-v>", self._on_paste)
        self.root.bind("<Delete>", self._on_delete)

        self.macro_listbox.bind(
            "<Configure>",
            lambda e: (
                self._show_insert_indicator(self._drag_preview_index)
                if self._insert_line_visible and self._drag_preview_index is not None
                else None
            ),
        )

        def on_listbox_click(event):
            lb = self.macro_listbox
            if lb.size() == 0:
                lb.selection_clear(0, tk.END)
                return "break"
            last_vis_idx = lb.nearest(lb.winfo_height())
            bbox = lb.bbox(last_vis_idx)
            if bbox:
                y_bottom = bbox[1] + bbox[3]
                if event.y > y_bottom:
                    lb.selection_clear(0, tk.END)
                    return "break"

        self.macro_listbox.bind("<Button-1>", on_listbox_click, add="+")
        self.root.bind("<Escape>", lambda e: self.macro_listbox.selection_clear(0, tk.END))

        tk.Button(right_frame, text="키보드", width=18, command=self.add_keyboard).pack(pady=6)
        tk.Button(right_frame, text="마우스", width=18, command=self.add_mouse).pack(pady=6)
        tk.Button(right_frame, text="시간", width=18, command=self.add_delay).pack(pady=6)
        tk.Button(right_frame, text="이미지조건", width=18, command=self.add_image_condition).pack(pady=6)
        tk.Button(right_frame, text="지우기", width=18, command=self.delete_macro).pack(pady=16)

        self.run_btn = tk.Button(right_frame, text="▶ 실행하기", width=18, command=self.run_macros)
        self.run_btn.pack(pady=6)
        self.stop_btn = tk.Button(right_frame, text="■ 중지", width=18, state=tk.DISABLED, command=self.stop_execution)
        self.stop_btn.pack(pady=6)

    def _bind_events(self):
        pass

    def _register_hotkeys_if_available(self):
        if KEYBOARD_AVAILABLE:
            register_hotkeys(self.root, self)
        else:
            self.root.after(
                500,
                lambda: messagebox.showwarning(
                    "전역 단축키 비활성화",
                    "keyboard 라이브러리가 없거나 권한이 없어 전역 단축키를 사용할 수 없습니다.\n"
                    "필요 시 다음을 설치하세요:\n\npip install keyboard",
                ),
            )

    def _restore_last_file(self):
        try:
            app_state = load_app_state() or {}
            last_path = app_state.get("last_file_path")
            if last_path and os.path.exists(last_path):
                self._open_path(last_path)
        except Exception:
            pass

    # ---------- 타이틀/더티 ----------
    def _update_title(self):
        name = self.current_path if self.current_path else "Untitled"
        mark = "*" if self.is_dirty else ""
        self.root.title(f"Namaan's Macro - {name}{mark}")

    def _mark_dirty(self, flag=True):
        self.is_dirty = bool(flag)
        self._update_title()

    # ---------- 파일 I/O ----------
    def _open_path(self, file_path: str) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.macro_listbox.delete(0, tk.END)

            items = data.get("items", [])
            descs = data.get("descriptions", [""] * len(items))
            if len(descs) != len(items):
                if len(descs) < len(items):
                    descs = descs + [""] * (len(items) - len(descs))
                else:
                    descs = descs[:len(items)]

            for raw, d in zip(items, descs):
                if is_valid_macro_line(raw):
                    display = self._join_raw_desc(raw, d)
                    self.macro_listbox.insert(tk.END, display)

            settings = data.get("settings", {})
            if "repeat" in settings:
                self.settings["repeat"] = int(settings["repeat"])
            if "start_delay" in settings:
                self.settings["start_delay"] = int(settings["start_delay"])

            hotkeys = data.get("hotkeys", {})
            if hotkeys:
                self.hotkeys.update(hotkeys)
                self._register_hotkeys_if_available()

            self.current_path = file_path
            self._mark_dirty(False)
            try:
                save_app_state({"last_file_path": file_path})
            except Exception:
                pass

            return True
        except Exception as e:
            messagebox.showerror("불러오기 실패", f"파일을 불러오는 중 오류 발생:\n{e}")
            return False

    def _collect_export_data(self) -> dict:
        items_only_raw, descs = [], []
        for i in range(self.macro_listbox.size()):
            raw, desc = self._split_raw_desc(self.macro_listbox.get(i))
            items_only_raw.append(raw)
            descs.append(desc)

        data = export_data(items_only_raw, self.settings, self.hotkeys)
        data["descriptions"] = descs
        return data

    def _confirm_save_if_dirty(self) -> bool:
        if not self.is_dirty:
            return True
        res = messagebox.askyesnocancel("변경사항 저장", "변경사항을 저장하시겠습니까?")
        if res is None:
            return False
        if res is True:
            return self.save_file()
        return True

    def new_file(self):
        if self.running:
            messagebox.showwarning("경고", "실행 중에는 초기화할 수 없습니다. 중지 후 다시 시도하세요.")
            return
        if not self._confirm_save_if_dirty():
            return
        self.macro_listbox.delete(0, tk.END)
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        self._register_hotkeys_if_available()
        self.current_path = None
        self._mark_dirty(False)

    def request_quit(self):
        if self.running:
            messagebox.showwarning("종료 불가", "실행 중에는 종료할 수 없습니다. 중지 후 다시 시도하세요.")
            return
        if not self._confirm_save_if_dirty():
            return
        self.root.quit()

    def load_file(self):
        if self.running:
            messagebox.showwarning("경고", "실행 중에는 불러올 수 없습니다. 중지 후 다시 시도하세요.")
            return
        if not self._confirm_save_if_dirty():
            return
        file_path = filedialog.askopenfilename(
            title="매크로 파일 불러오기",
            filetypes=[("Macro JSON", "*.json"), ("All files", "*.*")],
        )
        if not file_path:
            return
        if self._open_path(file_path):
            messagebox.showinfo("불러오기 완료", "매크로 파일을 불러왔습니다.")

    def save_file(self) -> bool:
        if self.running:
            messagebox.showwarning("저장 불가", "실행 중에는 저장할 수 없습니다. 중지 후 다시 시도하세요.")
            return False
        path = self.current_path
        if not path:
            return self.save_file_as()
        try:
            data = self._collect_export_data()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._mark_dirty(False)
            try:
                save_app_state({"last_file_path": path})
            except Exception:
                pass
            messagebox.showinfo("완료", "저장이 완료되었습니다.")
            return True
        except Exception as e:
            messagebox.showerror("에러", f"저장 실패:\n{e}")
            return False

    def save_file_as(self) -> bool:
        if self.running:
            messagebox.showwarning("저장 불가", "실행 중에는 저장할 수 없습니다. 중지 후 다시 시도하세요.")
            return False
        path = filedialog.asksaveasfilename(
            title="다른 이름으로 저장",
            defaultextension=".json",
            filetypes=[("Macro JSON", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return False
        self.current_path = path
        self._update_title()
        return self.save_file()

    # ---------- 설정 ----------
    def open_settings(self):
        if self.settings_window and tk.Toplevel.winfo_exists(self.settings_window):
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("설정")
        win.geometry("360x220+560+360")
        win.resizable(False, False)
        win.transient(self.root)
        win.lift()
        win.grab_set()
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(frm, text="반복 횟수 (0=무한)").grid(row=0, column=0, sticky="w")
        self.repeat_var = tk.IntVar(value=self.settings["repeat"])
        tk.Spinbox(frm, from_=0, to=9999, width=8, textvariable=self.repeat_var).grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(frm, text="시작 지연 (초)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.delay_var = tk.IntVar(value=self.settings["start_delay"])
        tk.Spinbox(frm, from_=0, to=600, width=8, textvariable=self.delay_var).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))

        self.start_key_var = tk.StringVar(value=self.hotkeys.get("start") or "")
        self.stop_key_var = tk.StringVar(value=self.hotkeys.get("stop") or "")

        row = 2
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
            delay = int(self.delay_var.get())
            if repeat < 0 or delay < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("에러", "반복 횟수와 지연 시간은 0 이상의 정수여야 합니다.")
            return
        self.settings["repeat"] = repeat
        self.settings["start_delay"] = delay
        self._mark_dirty(True)
        self._close_settings(win)

    def _close_settings(self, win):
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        self.settings_window = None

    def _capture_hotkey(self, which: str):
        cap = tk.Toplevel(self.root)
        cap.title("단축키 입력")
        cap.geometry("260x110+600+400")
        cap.transient(self.settings_window or self.root)
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
            self._mark_dirty(True)
            self._register_hotkeys_if_available()
            close_cap()

        cap.bind("<Key>", on_key)
        cap.bind("<Escape>", lambda e: close_cap())

    # ---------- 리스트 조작 ----------
    def add_keyboard(self):
        key_window = tk.Toplevel(self.root)
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
            self._insert_smart(line)
            key_window.destroy()

        key_window.bind("<Key>", on_key)
        key_window.focus_set()

    def add_mouse(self):
        mouse_win = tk.Toplevel(self.root)
        mouse_win.title("마우스 입력")
        mouse_win.geometry("320x220+540+340")
        mouse_win.resizable(False, False)

        mouse_win.transient(self.root)
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

        btn_var = tk.StringVar(value="left")
        btnf = tk.Frame(frame)
        btnf.pack(pady=6)
        tk.Radiobutton(btnf, text="왼쪽 클릭", variable=btn_var, value="left").grid(row=0, column=0, padx=6)
        tk.Radiobutton(btnf, text="오른쪽 클릭", variable=btn_var, value="right").grid(row=0, column=1, padx=6)

        captured = {"x": None, "y": None}

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
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표를 캡처하세요.")
                return
            b = btn_var.get()
            line = f"마우스:{captured['x']},{captured['y']}:{b}"
            self._insert_smart(line)
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
        sec = simpledialog.askinteger("대기 시간", "대기할 초를 입력하세요:", minvalue=1, maxvalue=600)
        if sec:
            line = f"시간:{sec}"
            self._insert_smart(line)

    # ---------- 실행 단위 ----------
    def _execute_item(self, item: str):
        if self.stop_flag:
            return

        if item.startswith("키보드:"):
            try:
                _, key, action = item.split(":")
            except ValueError:
                return
            if action == "press":
                pyautogui.press(key)
            elif action == "down":
                pyautogui.keyDown(key)
            elif action == "up":
                pyautogui.keyUp(key)

        elif item.startswith("마우스:"):
            body = item.split(":", 1)[1]
            coord, button = body.split(":")
            x_str, y_str = coord.split(",")
            x, y = int(x_str), int(y_str)
            mouse_move_click(self.root, x, y, button)

        elif item.startswith("시간:"):
            sec = int(item.split(":", 1)[1])
            end = time.time() + sec
            while time.time() < end:
                if self.stop_flag:
                    break
                time.sleep(0.05)

    def delete_macro(self):
        return self._on_delete()

    # ---------- 실행/중지 ----------
    def run_macros(self):
        if self.running:
            messagebox.showinfo("안내", "이미 실행 중입니다.")
            return
        if self.macro_listbox.size() == 0:
            messagebox.showwarning("실행 불가", "매크로 리스트가 비어있습니다.")
            return

        self.running = True
        self.stop_flag = False
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        self.worker_thread = threading.Thread(target=self._execute_worker, daemon=True)
        self.worker_thread.start()

    def stop_execution(self):
        if not self.running:
            return
        self.stop_flag = True

    def _execute_worker(self):
        try:
            delay = max(0, int(self.settings.get("start_delay", 0)))
            if delay > 0:
                for _ in range(delay * 10):
                    if self.stop_flag:
                        break
                    time.sleep(0.1)
            if self.stop_flag:
                return

            repeat = int(self.settings.get("repeat", 1))
            loop_inf = (repeat == 0)
            loops = 0

            while (loop_inf or loops < repeat) and not self.stop_flag:
                items = [self._split_raw_desc(self.macro_listbox.get(i))[0] for i in range(self.macro_listbox.size())]
                i = 0
                n = len(items)
                while i < n and not self.stop_flag:
                    item = items[i]

                    if item.startswith("조건:"):
                        self._highlight_index(i)
                        try:
                            cond_body = item.split(":", 1)[1]
                            pos_str, rgb_str = cond_body.split("=")
                            cx_str, cy_str = pos_str.split(",")
                            rx_str, gy_str, bz_str = rgb_str.split(",")
                            cx, cy = int(cx_str), int(cy_str)
                            r_t, g_t, b_t = int(rx_str), int(gy_str), int(bz_str)
                        except Exception:
                            i += 1
                            while i < n and not items[i].startswith("조건끝"):
                                i += 1
                            i += 1
                            continue

                        sub = []
                        j = i + 1
                        while j < n:
                            line = items[j]
                            if line.startswith("조건끝"):
                                break
                            if line.startswith("  "):
                                sub.append((j, line[2:]))
                            else:
                                break
                            j += 1

                        pix = grab_rgb_at(cx, cy)
                        match = (pix == (r_t, g_t, b_t))

                        if match:
                            for idx_run, sub_item in sub:
                                if self.stop_flag:
                                    break
                                self._highlight_index(idx_run)
                                self._execute_item(sub_item)

                        i = j + 1 if j < n and items[j].startswith("조건끝") else j
                        continue

                    self._highlight_index(i)
                    self._execute_item(item)
                    i += 1

                if self.stop_flag:
                    break
                loops += 1
        finally:
            self.root.after(0, self._finish_execution)

    def _finish_execution(self):
        self.running = False
        self.stop_flag = False
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._clear_highlight()

    # ---------- 이미지 조건 ----------
    def add_image_condition(self):
        win = tk.Toplevel(self.root)
        win.title("이미지 조건")
        win.geometry("360x220+560+320")
        win.resizable(False, False)
        win.transient(self.root)
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

        def apply_block():
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표/색을 캡처하세요.")
                return
            header = f"조건:{captured['x']},{captured['y']}={captured['r']},{captured['g']},{captured['b']}"
            self.macro_listbox.insert(tk.END, header)
            self.macro_listbox.insert(tk.END, "조건끝")
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        btns = tk.Frame(frm)
        btns.pack(pady=8)
        tk.Button(btns, text="좌표/색 캡처 (Enter)", command=capture).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="조건 추가", command=apply_block).grid(row=0, column=1, padx=6)
        tk.Button(frm, text="취소 (Esc)", command=lambda: (win.grab_release(), win.destroy())).pack(pady=4)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Escape>", lambda e: (win.grab_release(), win.destroy()))

    # ---------- 내부 유틸 ----------
    def _insert_smart(self, line: str):
        lb = self.macro_listbox
        size = lb.size()
        sel = lb.curselection()

        if size == 0:
            lb.insert(tk.END, line)
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)
            lb.activate(0)
            lb.see(0)
            try:
                self._mark_dirty(True)
            except Exception:
                pass
            return

        idx = sel[0] if sel else (size - 1)
        line_at_idx = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is not None:
            start, end = blk
            if self._is_body(line_at_idx):
                insert_at = min(idx + 1, end)
            else:
                insert_at = end
            line = self._ensure_body_indent(line, going_into_block=True)
        else:
            insert_at = (idx + 1) if sel else size
            line = self._ensure_body_indent(line, going_into_block=False)

        lb.insert(insert_at, line)
        lb.selection_clear(0, tk.END)
        lb.selection_set(insert_at)
        lb.activate(insert_at)
        lb.see(insert_at)

        try:
            self._mark_dirty(True)
        except Exception:
            pass

    def _get_condition_bounds_if_any(self, idx: int):
        size = self.macro_listbox.size()
        if idx < 0 or idx >= size:
            return None
        start = None
        i = idx
        while i >= 0:
            line = self.macro_listbox.get(i)
            if line.startswith("조건:"):
                start = i
                break
            if not (line.startswith("  ") or line.startswith("조건끝")):
                return None
            i -= 1
        if start is None:
            return None
        end = None
        j = start + 1
        while j < size:
            if self.macro_listbox.get(j).startswith("조건끝"):
                end = j
                break
            j += 1
        if end is None:
            end = start
        return (start, end)

    def _highlight_index(self, idx: int):
        def do():
            try:
                self.macro_listbox.selection_clear(0, tk.END)
                self.macro_listbox.activate(idx)
                self.macro_listbox.selection_set(idx)
                self.macro_listbox.see(idx)
            except Exception:
                pass

        self.root.after(0, do)

    def _clear_highlight(self):
        def do():
            try:
                self.macro_listbox.selection_clear(0, tk.END)
            except Exception:
                pass

        self.root.after(0, do)

    def _is_header(self, line: str) -> bool:
        return line.startswith("조건:")

    def _is_footer(self, line: str) -> bool:
        return line.startswith("조건끝")

    def _is_body(self, line: str) -> bool:
        return line.startswith("  ") and not self._is_footer(line) and not self._is_header(line)

    def _find_block_bounds(self, idx: int) -> tuple[int, int] | None:
        size = self.macro_listbox.size()
        if size == 0 or idx < 0 or idx >= size:
            return None
        line = self.macro_listbox.get(idx)
        if self._is_header(line):
            start = idx
            j = idx + 1
            while j < size and not self._is_footer(self.macro_listbox.get(j)):
                j += 1
            if j < size and self._is_footer(self.macro_listbox.get(j)):
                return (start, j)
            return None
        if self._is_body(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return self._find_block_bounds(i)
            return None
        if self._is_footer(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return (i, idx)
            return None
        return None

    def _in_same_block(self, i: int, j: int) -> bool:
        b1 = self._find_block_bounds(i)
        b2 = self._find_block_bounds(j)
        return b1 is not None and b1 == b2

    def _nearest_index(self, event) -> int:
        idx = self.macro_listbox.nearest(event.y)
        size = self.macro_listbox.size()
        if idx < 0:
            idx = 0
        if idx >= size:
            idx = size - 1 if size > 0 else 0
        return idx

    def _on_drag_start(self, event):
        self._drag_start_index = self._nearest_index(event)
        self._drag_preview_index = None
        self._drag_moved = False
        try:
            self.macro_listbox.selection_clear(0, tk.END)
            self.macro_listbox.selection_set(self._drag_start_index)
            self.macro_listbox.activate(self._drag_start_index)
        except Exception:
            pass

    def _on_drag_motion(self, event):
        if self._drag_start_index is None:
            self._hide_insert_indicator()
            return

        lb = self.macro_listbox
        size = lb.size()
        idx, at_end = self._nearest_index_allow_end(event)

        if not self._drag_moved:
            if at_end or idx != self._drag_start_index:
                self._drag_moved = True

        src = self._drag_start_index
        src_line = lb.get(src)
        src_blk = self._find_block_bounds(src)

        tgt_blk = None if at_end else self._find_block_bounds(idx)

        if at_end:
            preview_insert_at = size
        elif tgt_blk is not None:
            t_start, t_end = tgt_blk
            if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk:
                body_start, body_end = t_start + 1, t_end - 1
                if body_start > body_end:
                    self._hide_insert_indicator()
                    return
                preview_insert_at = max(body_start, min(idx, body_end + 1))
            else:
                preview_insert_at = t_end
        else:
            preview_insert_at = idx

        self._drop_preview_insert_at = preview_insert_at
        self._show_insert_indicator(preview_insert_at)

        try:
            lb.selection_clear(0, tk.END)
            if size > 0:
                sel_idx = size - 1 if at_end else idx
                lb.selection_set(sel_idx)
                lb.activate(sel_idx)
                lb.see(sel_idx)
        except Exception:
            pass

    def _on_drag_release(self, event):
        try:
            if self._drag_start_index is None:
                return
            if not self._drag_moved:
                return

            lb = self.macro_listbox
            size = lb.size()
            src = self._drag_start_index
            src_line = lb.get(src)
            src_blk = self._find_block_bounds(src)

            if src_blk is not None and (self._is_header(src_line) or self._is_footer(src_line)):
                s, e = src_blk
                payload = [lb.get(i) for i in range(s, e + 1)]
                payload_is_block = True
                del_start, del_end = s, e
            else:
                payload = [src_line]
                payload_is_block = False
                del_start, del_end = src, src

            width = del_end - del_start + 1

            idx, at_end = self._nearest_index_allow_end(event)
            tgt_blk = None if at_end else self._find_block_bounds(idx)

            if tgt_blk is not None:
                t_start, t_end = tgt_blk

                if payload_is_block and src_blk == tgt_blk:
                    return

                if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk and not payload_is_block:
                    body_start, body_end = t_start + 1, t_end - 1
                    if body_start > body_end:
                        return
                    insert_at = max(body_start, min(idx, body_end + 1))
                    lb.delete(src)
                    if src < insert_at:
                        insert_at -= 1
                    lb.insert(insert_at, payload[0])
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(insert_at)
                    lb.activate(insert_at)
                    lb.see(insert_at)
                    try:
                        self._mark_dirty(True)
                    except Exception:
                        pass
                    return

                insert_at = t_end
                if del_start < insert_at:
                    insert_at -= width
                final_lines = self._prepare_lines_for_body(payload)

            else:
                insert_at = self._drop_preview_insert_at if self._drop_preview_insert_at is not None else (
                    size if at_end else idx)
                if insert_at < 0:
                    insert_at = 0
                if insert_at > size:
                    insert_at = size

                if del_start < insert_at:
                    insert_at -= width

                final_lines = self._prepare_lines_for_top(payload, payload_is_block)

            for _ in range(width):
                lb.delete(del_start)

            for i, s in enumerate(final_lines):
                lb.insert(insert_at + i, s)

            lb.selection_clear(0, tk.END)
            lb.selection_set(max(0, min(lb.size() - 1, insert_at)))
            lb.activate(max(0, min(lb.size() - 1, insert_at)))
            lb.see(insert_at)

            try:
                self._mark_dirty(True)
            except Exception:
                pass

        finally:
            self._hide_insert_indicator()
            self._drag_start_index = None
            self._drag_preview_index = None
            self._drop_preview_insert_at = None
            self._drag_moved = False

    def _on_copy(self, event=None):
        lb = self.macro_listbox
        sel = lb.curselection()
        if not sel:
            return "break"

        idx = sel[0]
        line = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is not None and (self._is_header(line) or self._is_footer(line)):
            s, e = blk
            self._clipboard = [lb.get(i) for i in range(s, e + 1)]
            self._clipboard_is_block = True
            return "break"

        self._clipboard = [line]
        self._clipboard_is_block = False
        return "break"

    def _on_cut(self, event=None):
        self._on_copy()
        self._on_delete()
        return "break"

    def _on_paste(self, event=None):
        lb = self.macro_listbox
        size = lb.size()

        if not self._clipboard:
            self.root.bell()
            return "break"

        sel = lb.curselection()
        cur_idx = sel[0] if sel else (size if size > 0 else 0)

        cur_block = self._find_block_bounds(cur_idx)

        if cur_block is not None:
            start, end = cur_block
            insert_at = end
            payload = self._prepare_lines_for_body(self._clipboard)
            if not payload:
                return "break"
            for i, s in enumerate(payload):
                lb.insert(insert_at + i, s)
            lb.selection_clear(0, tk.END)
            lb.selection_set(insert_at)
            lb.activate(insert_at)
            lb.see(insert_at)
        else:
            insert_at = cur_idx + 1 if (size > 0 and cur_idx < size) else size
            payload = self._prepare_lines_for_top(self._clipboard, self._clipboard_is_block)
            if not payload:
                return "break"
            for i, s in enumerate(payload):
                lb.insert(insert_at + i, s)
            lb.selection_clear(0, tk.END)
            lb.selection_set(insert_at)
            lb.activate(insert_at)
            lb.see(insert_at)

        try:
            self._mark_dirty(True)
        except Exception:
            pass

        return "break"

    def _on_delete(self, event=None):
        lb = self.macro_listbox
        sel = lb.curselection()
        if not sel:
            return "break"

        idx = sel[0]
        line = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is None:
            lb.delete(idx)
            size = lb.size()
            if idx >= size:
                idx = size - 1
            if idx >= 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
                lb.see(idx)
            try:
                self._mark_dirty(True)
            except Exception:
                pass
            return "break"

        start, end = blk
        if self._is_header(line) or self._is_footer(line):
            width = end - start + 1
            for _ in range(width):
                lb.delete(start)
            size = lb.size()
            new_idx = min(start, size - 1)
            if new_idx >= 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(new_idx)
                lb.activate(new_idx)
                lb.see(new_idx)
        else:
            lb.delete(idx)
            size = lb.size()
            new_idx = idx
            if new_idx >= size:
                new_idx = size - 1
            lb.selection_clear(0, tk.END)
            if new_idx >= 0:
                lb.selection_set(new_idx)
                lb.activate(new_idx)
                lb.see(new_idx)

        try:
            self._mark_dirty(True)
        except Exception:
            pass

        return "break"

    def _hide_insert_indicator(self):
        if self._insert_line_visible:
            try:
                self._insert_bar.place_forget()
            except Exception:
                pass
            self._insert_line_visible = False

    def _show_insert_indicator(self, insert_at: int):
        lb = self.macro_listbox
        size = lb.size()
        if size == 0:
            self._hide_insert_indicator()
            return

        line_index = insert_at - 1
        base_top = False
        if line_index < 0:
            line_index = 0
            base_top = True

        try:
            lb.see(line_index)
            bbox = lb.bbox(line_index)
            if not bbox:
                self._hide_insert_indicator()
                return
            x, y, w, h = bbox
            y_line = y if base_top else (y + h - 1)

            try:
                self._insert_bar.configure(bg="#2a7fff")
            except Exception:
                pass

            self._insert_bar.place(in_=lb, x=0, y=y_line, relwidth=1, height=2)
            self._insert_line_visible = True
        except Exception:
            self._hide_insert_indicator()

    def _nearest_index_allow_end(self, event) -> tuple[int, bool]:
        lb = self.macro_listbox
        size = lb.size()
        if size == 0:
            return 0, True
        idx = lb.nearest(event.y)
        try:
            bbox_last = lb.bbox(size - 1)
            if bbox_last:
                _, y, _, h = bbox_last
                if event.y > y + h:
                    return size, True
        except Exception:
            pass
        return idx, False

    def _prepare_lines_for_body(self, lines: list[str]) -> list[str]:
        out = []
        for s in lines:
            if self._is_header(s) or self._is_footer(s):
                continue
            if s.startswith("  "):
                out.append(s)
            else:
                out.append("  " + s)
        return out

    def _prepare_lines_for_top(self, lines: list[str], clipboard_is_block: bool) -> list[str]:
        if clipboard_is_block:
            return list(lines)
        out = []
        for s in lines:
            if self._is_header(s) or self._is_footer(s):
                out.append(s)
            elif s.startswith("  "):
                out.append(s[2:])
            else:
                out.append(s)
        return out

    def _ensure_body_indent(self, s: str, going_into_block: bool) -> str:
        if going_into_block and not s.startswith("  ") and not self._is_header(s) and not self._is_footer(s):
            return "  " + s
        return s

    # ---- 화면 문자열 ↔ (원본, 설명) ----
    def _split_raw_desc(self, s: str) -> tuple[str, str]:
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw

    # ---- 설명 인라인 편집 ----
    def _begin_desc_inline_edit(self, event):
        if self._inline_edit_entry is not None:
            return "break"

        lb = self.macro_listbox
        idx = lb.nearest(event.y)
        size = lb.size()
        if size == 0 or idx < 0 or idx >= size:
            return "break"

        line = lb.get(idx)
        raw, cur_desc = self._split_raw_desc(line)

        bbox = lb.bbox(idx)
        if not bbox:
            return "break"
        x, y, w, h = bbox

        ent = tk.Entry(lb)
        ent.insert(0, cur_desc)  # 기존 설명을 올바르게 프리필
        lb.update_idletasks()
        entry_w = max(w + 16, lb.winfo_width() - 4)

        ent.place(x=0, y=y-2, width=entry_w, height=h)
        ent.focus_set()
        self._inline_edit_entry = ent

        def _cleanup():
            try:
                ent.place_forget()
                ent.destroy()
            except Exception:
                pass
            self._inline_edit_entry = None
            try:
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
                lb.see(idx)
            except Exception:
                pass

        def _commit(e=None):
            new_desc = ent.get().strip()
            lb.delete(idx)
            lb.insert(idx, self._join_raw_desc(raw, new_desc))
            try:
                self._mark_dirty(True)
            except Exception:
                pass
            _cleanup()

        def _cancel(e=None):
            _cleanup()

        ent.bind("<Return>", _commit)
        ent.bind("<Escape>", _cancel)
        ent.bind("<FocusOut>", _commit)
        return "break"


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroUI(root)
    root.mainloop()
