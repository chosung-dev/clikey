import os
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
import threading
import time
import json

import pyautogui

from core.state import default_settings, default_hotkeys
from core.keyboard_hotkey import (
    KEYBOARD_AVAILABLE, keyboard, register_hotkeys,
    normalize_key_for_keyboard, display_key_name
)
from core.mouse import mouse_move_click
from core.screen import grab_rgb_at
from core.persistence import is_valid_macro_line, export_data, load_app_state, save_app_state

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


# ========================= StyledList (Text 기반 Listbox 어댑터) =========================
class StyledList(tk.Text):
    """
    Text 기반으로 Listbox 유사 API를 제공하는 어댑터.
    - 각 줄을 (raw, desc)로 관리
    - 화면에는 'raw - desc'로 렌더하며 desc 부분은 초록색 태그로 표시
    - selection / nearest / bbox / see / insert / delete 등 Listbox 호환 메서드 제공
    """

    def __init__(self, master, split_cb, join_cb, desc_color="#1a7f37", **kwargs):
        kwargs.setdefault("wrap", "none")
        kwargs.setdefault("undo", False)
        kwargs.setdefault("cursor", "arrow")
        kwargs.setdefault("height", 1)
        super().__init__(master, **kwargs)

        self._split_cb = split_cb
        self._join_cb = join_cb
        self._desc_color = desc_color
        self._lines: list[tuple[str, str]] = []  # (raw, desc)
        self._cur_index: int | None = None

        # 스타일 태그
        self.tag_configure("desc", foreground=self._desc_color)
        self.tag_configure("selrow", background="lightblue", foreground="black")

        # 직접 타이핑 방지
        self.configure(state="disabled")

    # ---------- 내부 렌더 ----------
    def _render_all(self):
        # Text의 delete/insert를 직접 호출(우리가 오버라이드한 delete를 피함)
        self.configure(state="normal")
        tk.Text.delete(self, "1.0", "end")
        for raw, desc in self._lines:
            tk.Text.insert(self, "end", raw)
            if desc:
                tk.Text.insert(self, "end", " - ")
                tk.Text.insert(self, "end", desc, ("desc",))
            tk.Text.insert(self, "end", "\n")
        self.configure(state="disabled")

        # 선택 복원
        if self._cur_index is not None and 0 <= self._cur_index < len(self._lines):
            self._apply_selection(self._cur_index)

    def _apply_selection(self, idx: int | None):
        self.tag_remove("selrow", "1.0", "end")
        if idx is None or idx < 0 or idx >= len(self._lines):
            self._cur_index = None
            return
        self._cur_index = idx
        ln = idx + 1
        self.tag_add("selrow", f"{ln}.0", f"{ln}.0 lineend")

    # ---------- Listbox 호환 ----------
    def size(self):
        return len(self._lines)

    def get(self, idx: int) -> str:
        raw, desc = self._lines[idx]
        return self._join_cb(raw, desc)

    def insert(self, index, s: str):
        # index: 정수 또는 tk.END
        if index in (tk.END, "end"):
            index = len(self._lines)
        index = max(0, min(int(index), len(self._lines)))

        raw, desc = self._split_cb(s)
        self._lines.insert(index, (raw, desc))
        self._render_all()

    def delete(self, start, end=None):
        """Listbox 호환 삭제: (idx) 또는 (start, end) / (0, tk.END) 등 지원.
           Text 인덱스("1.0")가 들어와도 방어적으로 처리."""
        def _to_int(val):
            if val in (tk.END, "end"):
                return len(self._lines) - 1
            if isinstance(val, str):
                if "." in val:  # "1.0" → 0
                    try:
                        return max(0, min(int(val.split(".", 1)[0]) - 1, len(self._lines) - 1))
                    except Exception:
                        return 0
                try:
                    return int(val)
                except Exception:
                    return 0
            return int(val)

        if end is None:
            idx = _to_int(start)
            if 0 <= idx < len(self._lines):
                del self._lines[idx]
        else:
            s = _to_int(start)
            e = _to_int(end)
            # 전체 삭제
            if (start in (0, "0", "1.0")) and (end in (tk.END, "end")):
                self._lines.clear()
            else:
                if s <= e and len(self._lines) > 0:
                    del self._lines[s:e + 1]

        self._render_all()

    def selection_clear(self, *_):
        self._apply_selection(None)

    def selection_set(self, idx: int):
        self._apply_selection(int(idx))

    def activate(self, idx: int):
        self._apply_selection(int(idx))

    def curselection(self):
        return () if self._cur_index is None else (self._cur_index,)

    def see(self, idx: int):
        ln = int(idx) + 1
        tk.Text.see(self, f"{ln}.0")

    def bbox(self, idx: int):
        ln = int(idx) + 1
        info = self.dlineinfo(f"{ln}.0")
        if not info:
            return None
        x, y, w, h, _baseline = info
        return (x, y, w, h)

    def nearest(self, y: int):
        idx = self.index(f"@0,{int(y)}")
        line = int(str(idx).split(".")[0]) - 1
        if line < 0:
            line = 0
        if line >= len(self._lines):
            line = len(self._lines) - 1 if self._lines else 0
        return line

    def cget(self, key):
        return super().cget(key)


# =================================== MacroUI ===================================
class MacroUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Namaan's Macro")
        self.root.geometry("500x450")

        # --------- 실행 상태/설정 ---------
        self.running = False
        self.stop_flag = False
        self.worker_thread = None
        self.settings_window = None
        self._drag_moved = False
        self._drop_preview_insert_at = None  # 드래그 중 계산된 최종 삽입 index(미리보기)

        # 설정/단축키 기본값
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        self.hotkey_handles = {"start": None, "stop": None}

        # 현재 경로 & 더티 플래그
        self.current_path: str | None = None
        self.is_dirty: bool = False

        # ---------------- 메뉴바 ----------------
        menubar = tk.Menu(root)

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

        root.config(menu=menubar)

        # ---------------- 메인 레이아웃 ----------------
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 오른쪽: 버튼들
        right_frame = tk.Frame(main_frame, bd=2, relief=tk.GROOVE)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)

        # 왼쪽: 매크로 리스트
        left_frame = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Listbox 대체: StyledList 사용 (설명만 초록색)
        self.macro_listbox = StyledList(
            left_frame,
            split_cb=self._split_raw_desc,
            join_cb=self._join_raw_desc,
            desc_color="#1a7f37",
        )
        self.macro_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        lb = self.macro_listbox

        # 인라인 설명 편집 (더블클릭)
        self._inline_edit_entry = None
        lb.bind("<Double-Button-1>", self._begin_desc_inline_edit, add="+")

        # 드래그 상태 & 클립보드 상태
        self._drag_start_index = None
        self._drag_preview_index = None
        self._clipboard = []  # list[str]
        self._clipboard_is_block = False

        # 드래그&드롭 바인딩
        lb.bind("<Button-1>", self._on_drag_start, add="+")
        lb.bind("<B1-Motion>", self._on_drag_motion, add="+")
        lb.bind("<ButtonRelease-1>", self._on_drag_release, add="+")

        # 드롭 위치 가이드 바 (2px)
        self._insert_bar = tk.Frame(self.root, height=2, bd=0, highlightthickness=0)
        self._insert_bar.place_forget()  # 평소엔 숨김
        self._insert_line_visible = False

        # 단축키(Ctrl+C/X/V, Delete)
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
            )
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

        # 실행/중지 버튼
        self.run_btn = tk.Button(right_frame, text="▶ 실행하기", width=18, command=self.run_macros)
        self.run_btn.pack(pady=6)
        self.stop_btn = tk.Button(right_frame, text="■ 중지", width=18, state=tk.DISABLED, command=self.stop_execution)
        self.stop_btn.pack(pady=6)

        # 앱 시작 시 기본 핫키 등록
        if KEYBOARD_AVAILABLE:
            register_hotkeys(self.root, self)
        else:
            self.root.after(500, lambda: messagebox.showwarning(
                "전역 단축키 비활성화",
                "keyboard 라이브러리가 없거나 권한이 없어 전역 단축키를 사용할 수 없습니다.\n"
                "필요 시 다음을 설치하세요:\n\npip install keyboard"
            ))

        # ▶ 앱 시작 시 마지막 파일 자동 복구
        try:
            app_state = load_app_state() or {}
            last_path = app_state.get("last_file_path")
            if last_path and os.path.exists(last_path):
                self._open_path(last_path)
        except Exception:
            pass

    # ▶ 내부: 제목 갱신 및 더티 표기
    def _update_title(self):
        name = self.current_path if self.current_path else "Untitled"
        mark = "*" if self.is_dirty else ""
        self.root.title(f"Namaan's Macro - {name}{mark}")

    def _open_path(self, file_path: str) -> bool:
        """JSON 파일을 열어 리스트/설정/단축키를 복원한다.
        - items: 실행 '원본' 문자열
        - descriptions: 각 라인의 설명(없으면 빈 문자열)
        화면에는 '원본 - 설명' 형태로 합쳐서 표시한다.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ---------- 리스트 복원 (원본 + 설명 병합 표시) ----------
            self.macro_listbox.delete(0, tk.END)

            items = data.get("items", [])
            descs = data.get("descriptions", [""] * len(items))

            # 길이 보정
            if len(descs) != len(items):
                if len(descs) < len(items):
                    descs = descs + [""] * (len(items) - len(descs))
                else:
                    descs = descs[:len(items)]

            # 화면에는 '원본 - 설명'으로 표시
            for raw, d in zip(items, descs):
                if is_valid_macro_line(raw):
                    display = self._join_raw_desc(raw, d)
                    self.macro_listbox.insert(tk.END, display)

            # ---------- 설정 복원 ----------
            settings = data.get("settings", {})
            if "repeat" in settings:
                self.settings["repeat"] = int(settings["repeat"])
            if "start_delay" in settings:
                self.settings["start_delay"] = int(settings["start_delay"])

            # ---------- 단축키 복원 ----------
            hotkeys = data.get("hotkeys", {})
            if hotkeys:
                self.hotkeys.update(hotkeys)
                if KEYBOARD_AVAILABLE:
                    register_hotkeys(self.root, self)

            # ---------- 경로/상태 ----------
            self.current_path = file_path
            self._mark_dirty(False)
            try:
                save_app_state({"last_file_path": file_path})
            except Exception:
                pass

            return True

            # noqa: E722
        except Exception as e:
            messagebox.showerror("불러오기 실패", f"파일을 불러오는 중 오류 발생:\n{e}")
            return False

    def _mark_dirty(self, flag=True):
        self.is_dirty = bool(flag)
        self._update_title()

    # ---------------- 메뉴 이벤트 ----------------
    def new_file(self):
        if self.running:
            messagebox.showwarning("경고", "실행 중에는 초기화할 수 없습니다. 중지 후 다시 시도하세요.")
            return
        if not self._confirm_save_if_dirty():
            return
        self.macro_listbox.delete(0, tk.END)
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        if KEYBOARD_AVAILABLE:
            register_hotkeys(self.root, self)
        self.current_path = None
        self._mark_dirty(False)

    def _collect_export_data(self) -> dict:
        # 화면 문자열들을 (원본, 설명)으로 분리
        items_only_raw = []
        descs = []
        for i in range(self.macro_listbox.size()):
            raw, desc = self._split_raw_desc(self.macro_listbox.get(i))
            items_only_raw.append(raw)
            descs.append(desc)

        data = export_data(items_only_raw, self.settings, self.hotkeys)
        data["descriptions"] = descs  # 설명도 함께 저장
        return data

    # 저장 확인 공통
    def _confirm_save_if_dirty(self) -> bool:
        if not self.is_dirty:
            return True
        res = messagebox.askyesnocancel("변경사항 저장", "변경사항을 저장하시겠습니까?")
        if res is None:
            return False
        if res is True:
            return self.save_file()
        return True  # 저장 안 함

    # 앱 종료 요청 (메뉴/창 닫기 훅에서 사용)
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
            filetypes=[("Macro JSON", "*.json"), ("All files", "*.*")]
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
            filetypes=[("Macro JSON", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return False
        self.current_path = path
        self._update_title()
        return self.save_file()

    # ============== 설정창 ==============
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

            if KEYBOARD_AVAILABLE:
                register_hotkeys(self.root, self)
            else:
                messagebox.showwarning("전역 단축키 비활성화", "keyboard 라이브러리가 없어 단축키가 적용되지 않습니다.")
            close_cap()

        cap.bind("<Key>", on_key)
        cap.bind("<Escape>", lambda e: close_cap())

    # ---------------- 리스트 조작 ----------------
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
        # 버튼/메뉴에서 삭제 눌렀을 때도 동일 로직 사용
        return self._on_delete()

    # ---------------- 실행/중지 ----------------
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
                items = [self._split_raw_desc(self.macro_listbox.get(i))[0]
                         for i in range(self.macro_listbox.size())]
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

    # -------- 내부 유틸 --------
    def _insert_smart(self, line: str):
        lb = self.macro_listbox
        size = lb.size()
        sel = lb.curselection()

        # 리스트가 비면 맨 끝에
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

        # 선택 인덱스
        idx = sel[0] if sel else (size - 1)
        line_at_idx = lb.get(idx)

        # 선택한 줄이 속한 '조건 블록' 범위
        blk = self._find_block_bounds(idx)

        if blk is not None:
            # 블록 내부로 삽입
            start, end = blk  # end는 footer 인덱스(삽입 시 그 '앞'에 들어감)

            if self._is_body(line_at_idx):
                # ▶ 본문 줄을 선택했으면: 그 줄 '바로 아래' 위치로 (footer 넘지 않게)
                insert_at = idx + 1
                if insert_at > end:
                    insert_at = end
            else:
                # ▶ 헤더나 풋터 선택 시: 블록 맨 끝(footer 바로 위)
                insert_at = end

            # 블록 내부이므로 들여쓰기 보정
            line = self._ensure_body_indent(line, going_into_block=True)

        else:
            # 블록 바깥(레벨0): 현재 줄 '바로 아래' (선택 없으면 맨 끝)
            insert_at = (idx + 1) if sel else size
            # 레벨0이므로 들여쓰기 제거/보정 필요 없음
            line = self._ensure_body_indent(line, going_into_block=False)

        # 삽입
        lb.insert(insert_at, line)

        # 선택/포커스 갱신
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
        # 레벨1: 공백 2칸으로 시작하는 라인
        return line.startswith("  ") and not self._is_footer(line) and not self._is_header(line)

    def _find_block_bounds(self, idx: int) -> tuple[int, int] | None:
        """idx가 블록에 속하면 (start_idx, end_idx) 반환. 아니면 None."""
        size = self.macro_listbox.size()
        if size == 0 or idx < 0 or idx >= size:
            return None
        line = self.macro_listbox.get(idx)
        # 헤더에서 시작
        if self._is_header(line):
            start = idx
            j = idx + 1
            while j < size and not self._is_footer(self.macro_listbox.get(j)):
                j += 1
            if j < size and self._is_footer(self.macro_listbox.get(j)):
                return (start, j)
            return None  # 잘못된 형식(끝을 못 찾음)
        # 바디에서 위로 올라가 헤더 찾기
        if self._is_body(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return self._find_block_bounds(i)
            return None
        # 풋터에서 위로 올라가 헤더 찾기
        if self._is_footer(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return (i, idx)
            return None
        # 일반(레벨0) 라인은 블록 아님
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

        # 실제로 움직였는지 판정
        if not self._drag_moved:
            if at_end or idx != self._drag_start_index:
                self._drag_moved = True

        # 소스 정보
        src = self._drag_start_index
        src_line = lb.get(src)
        src_blk = self._find_block_bounds(src)

        # 타겟 블록 판단
        tgt_blk = None if at_end else self._find_block_bounds(idx)

        # == 미리보기 insert_at 계산 ==
        if at_end:
            preview_insert_at = size  # 맨 끝
        elif tgt_blk is not None:
            # 블록 내부: footer 바로 앞(= end index)에 들어간다
            t_start, t_end = tgt_blk
            if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk:
                # 같은 블록 내부 본문 한 줄 재배치 → 바디 영역으로 클램프
                body_start, body_end = t_start + 1, t_end - 1
                if body_start > body_end:
                    self._hide_insert_indicator()
                    return
                preview_insert_at = max(body_start, min(idx, body_end + 1))
            else:
                preview_insert_at = t_end
        else:
            # 블록 외부(레벨0): 커서 위치로
            preview_insert_at = idx

        # 기록 & 가이드 라인 표시
        self._drop_preview_insert_at = preview_insert_at
        self._show_insert_indicator(preview_insert_at)

        # 선택 보조
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
                return  # 클릭만

            lb = self.macro_listbox
            size = lb.size()
            src = self._drag_start_index
            src_line = lb.get(src)
            src_blk = self._find_block_bounds(src)

            # 페이로드 구성: 헤더/풋터 선택 시 '블록', 그 외는 '단일 라인'
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

            # 드롭 위치 산정
            idx, at_end = self._nearest_index_allow_end(event)
            tgt_blk = None if at_end else self._find_block_bounds(idx)

            # === 삽입 위치 & 변환 규칙 ===
            if tgt_blk is not None:
                t_start, t_end = tgt_blk

                # 같은 블록에 '블록 전체'를 넣는 건 이상하니 무시
                if payload_is_block and src_blk == tgt_blk:
                    return

                if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk and not payload_is_block:
                    # 같은 블록 내부 본문 한 줄 재배치
                    body_start, body_end = t_start + 1, t_end - 1
                    if body_start > body_end:
                        return
                    insert_at = max(body_start, min(idx, body_end + 1))
                    # 삭제 → 위치 보정
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

                # 블록 내부 일반 규칙: footer 바로 앞에 '본문 형태'로 삽입
                insert_at = t_end
                if del_start < insert_at:
                    insert_at -= width
                final_lines = self._prepare_lines_for_body(payload)

            else:
                # 레벨0(블록 외부)
                insert_at = self._drop_preview_insert_at if self._drop_preview_insert_at is not None else (
                    size if at_end else idx)
                if insert_at < 0:
                    insert_at = 0
                if insert_at > size:
                    insert_at = size

                if del_start < insert_at:
                    insert_at -= width

                final_lines = self._prepare_lines_for_top(payload, payload_is_block)

            # === 실제 삭제 & 삽입 ===
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

        # 1) 조건 헤더/풋터를 클릭했을 때만 블록 전체 복사
        if blk is not None and (self._is_header(line) or self._is_footer(line)):
            s, e = blk
            self._clipboard = [lb.get(i) for i in range(s, e + 1)]
            self._clipboard_is_block = True
            return "break"

        # 2) 그 외(조건 내부 본문 줄, 혹은 레벨0 일반 줄)는 '해당 줄만' 복사
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

        # 선택 위치
        sel = lb.curselection()
        cur_idx = sel[0] if sel else (size if size > 0 else 0)

        cur_block = self._find_block_bounds(cur_idx)

        if cur_block is not None:
            # ▶ 이미지 조건 블록 내부로 붙여넣기
            start, end = cur_block
            insert_at = end  # footer 바로 앞

            # 클립보드를 '본문 레벨'용으로 변환
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
            # ▶ 레벨0(블록 외부)로 붙여넣기
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

        # 변경 플래그
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
            # 레벨0(블록 바깥) 단일 라인 삭제
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

        # 블록 안에 있음
        start, end = blk
        if self._is_header(line) or self._is_footer(line):
            # 헤더/풋터를 지우면 블록 전체 삭제
            width = end - start + 1
            for _ in range(width):
                lb.delete(start)
            # 선택 재배치
            size = lb.size()
            new_idx = min(start, size - 1)
            if new_idx >= 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(new_idx)
                lb.activate(new_idx)
                lb.see(new_idx)
        else:
            # 본문(들여쓴 줄)만 선택된 경우: 해당 줄만 삭제
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
        """insert_at 위치 '바로 위 라인 아래쪽'에 2px 바를 그립니다.
           insert_at == 0이면 첫 라인의 '위쪽'에 표시."""
        lb = self.macro_listbox
        size = lb.size()
        if size == 0:
            self._hide_insert_indicator()
            return

        # 기준 라인 계산
        line_index = insert_at - 1
        base_top = False
        if line_index < 0:
            line_index = 0
            base_top = True

        try:
            lb.see(line_index)
            bbox = lb.bbox(line_index)  # (x, y, w, h)
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
        """Listbox.nearest 대신 사용.
        - (index, at_end) 반환
        - 마우스가 마지막 항목의 '아래'로 내려가면 (size, True) → 맨 끝에 삽입"""
        lb = self.macro_listbox
        size = lb.size()
        if size == 0:
            return 0, True
        idx = lb.nearest(event.y)

        # 마지막 항목 bbox 기준으로 '더 아래'면 끝으로 취급
        try:
            bbox_last = lb.bbox(size - 1)  # (x, y, w, h)
            if bbox_last:
                _, y, _, h = bbox_last
                if event.y > y + h:
                    return size, True
        except Exception:
            pass
        return idx, False

    def _prepare_lines_for_body(self, lines: list[str]) -> list[str]:
        """블록 내부(레벨1)에 넣기 위해:
        - 헤더/풋터는 버림
        - 들여쓰기(두 칸) 없으면 붙여줌"""
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
        """레벨0에 넣기 위해:
        - 블록이면 원형 유지(헤더/풋터/본문 그대로)
        - 블록이 아니면, 본문 들여쓰기(두 칸)는 제거"""
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
        """블록 내부에 넣을 때는 본문 들여쓰기(두 칸)를 보장"""
        if going_into_block and not s.startswith("  ") and not self._is_header(s) and not self._is_footer(s):
            return "  " + s
        return s

    # (옵션) 전체 라인 편집기 — 현재는 사용 안 함
    def _begin_inline_edit(self, event):
        if self._inline_edit_entry is not None:
            return "break"
        lb = self.macro_listbox
        idx = lb.nearest(event.y)
        size = lb.size()
        if size == 0 or idx < 0 or idx >= size:
            return "break"
        line = lb.get(idx)
        bbox = lb.bbox(idx)
        if not bbox:
            return "break"
        x, y, w, h = bbox
        entry = tk.Entry(lb)
        entry.insert(0, line)
        entry.select_range(0, tk.END)
        entry.place(x=0, y=y, width=w, height=h)
        entry.focus_set()
        self._inline_edit_entry = entry

        def _cleanup():
            try:
                entry.place_forget()
                entry.destroy()
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
            new_text = entry.get()
            lb.delete(idx)
            lb.insert(idx, new_text)
            try:
                self._mark_dirty(True)
            except Exception:
                pass
            _cleanup()

        def _cancel(e=None):
            _cleanup()

        entry.bind("<Return>", _commit)
        entry.bind("<Escape>", _cancel)
        entry.bind("<FocusOut>", _commit)
        return "break"

    # ---- 화면 문자열 ↔ (원본, 설명) ----
    def _split_raw_desc(self, s: str) -> tuple[str, str]:
        """화면 문자열을 (원본, 설명)으로 분리. 마지막 ' - '를 설명 구분자로 사용.
        원본의 선행 공백(들여쓰기)을 보존한다."""
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        """(원본, 설명) → 화면 문자열. 설명이 없으면 원본만."""
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw

    # ---- 설명 인라인 편집(더블클릭) ----
    def _begin_desc_inline_edit(self, event):
        if self._inline_edit_entry is not None:
            return "break"

        lb = self.macro_listbox
        idx = lb.nearest(event.y)
        size = lb.size()
        if size == 0 or idx < 0 or idx >= size:
            return "break"

        # 현재 줄에서 (원본, 기존 설명) 추출
        line = lb.get(idx)
        raw, cur_desc = self._split_raw_desc(line)

        # 편집창(Entry)을 그 줄 전체에 깔기
        bbox = lb.bbox(idx)
        if not bbox:
            return "break"
        x, y, w, h = bbox

        ent = tk.Entry(lb)
        # 요구: 설명이 없으면 공란으로 시작
        ent.insert(0, "" if cur_desc == "" else "")
        ent.place(x=0, y=y, width=w, height=h)
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
