import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
import time
import pyautogui
import json
from tkinter import filedialog
from PIL import ImageGrab

# 전역 핫키용
try:
    import keyboard  # pip install keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    KEYBOARD_AVAILABLE = False

# AutoIt (Windows 전용)
try:
    import autoit  # pip install pyautoit
    AUTOIT_AVAILABLE = True
except Exception:
    AUTOIT_AVAILABLE = False

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


class MacroUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("매크로 프로그램")
        self.root.geometry("700x450")

        # --------- 실행 상태/설정 ---------
        self.running = False
        self.stop_flag = False
        self.worker_thread = None
        self.settings_window = None

        # 반복: 0=무한, 기본 1회 / 시작 지연: 기본 3초
        self.settings = {"repeat": 1, "start_delay": 3}

        # 단축키 (기본값 예시: 시작=F8, 중지=F9)
        self.hotkeys = {"start": "F8", "stop": "F9"}
        self.hotkey_handles = {"start": None, "stop": None}

        # ---------------- 메뉴바 ----------------
        menubar = tk.Menu(root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="새로 만들기", command=self.new_file)
        file_menu.add_command(label="저장하기", command=self.save_file)
        file_menu.add_command(label="불러오기", command=self.load_file)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=root.quit)
        menubar.add_cascade(label="파일", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="환경 설정", command=self.open_settings)
        menubar.add_cascade(label="설정", menu=settings_menu)

        root.config(menu=menubar)

        # ---------------- 메인 레이아웃 ----------------
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 왼쪽: 매크로 리스트
        left_frame = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(left_frame, text="매크로 리스트").pack(anchor="w", padx=6, pady=4)
        # 매크로 리스트박스 생성 이후
        # 매크로 리스트박스 생성 직후
        self.macro_listbox = tk.Listbox(
            left_frame,
            activestyle="none",      # 활성 항목 밑줄 제거
            selectbackground="lightblue",  # 선택 배경 원하는 색상
            selectforeground="black"       # 선택 글자색
        )
        self.macro_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        def on_listbox_click(event):
            lb = self.macro_listbox
            # 항목 없으면 그냥 해제하고 기본 동작 차단
            if lb.size() == 0:
                lb.selection_clear(0, tk.END)
                return "break"

            # 현재 보이는 마지막 항목(스크롤 고려)
            last_vis_idx = lb.nearest(lb.winfo_height())
            bbox = lb.bbox(last_vis_idx)  # (x, y, w, h) - 보이는 항목만 유효
            if bbox:
                y_bottom = bbox[1] + bbox[3]
                if event.y > y_bottom:
                    # 빈 공간 클릭 → 선택 해제 + 기본 선택 동작 차단
                    lb.selection_clear(0, tk.END)
                    return "break"
            # 빈 공간이 아니라면 기본 동작 허용 (선택되게 둠)

        self.macro_listbox.bind("<Button-1>", on_listbox_click, add="+")
        self.root.bind("<Escape>", lambda e: self.macro_listbox.selection_clear(0, tk.END))

        # 오른쪽: 버튼들
        right_frame = tk.Frame(main_frame, bd=2, relief=tk.GROOVE)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)

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
            self._register_hotkeys()
        else:
            self.root.after(500, lambda: messagebox.showwarning(
                "전역 단축키 비활성화",
                "keyboard 라이브러리가 없거나 권한이 없어 전역 단축키를 사용할 수 없습니다.\n"
                "필요 시 다음을 설치하세요:\n\npip install keyboard"
            ))

    # ---------------- 메뉴 이벤트 ----------------
    def new_file(self):
        if self.running:
            messagebox.showwarning("경고", "실행 중에는 초기화할 수 없습니다. 중지 후 다시 시도하세요.")
            return
        self.macro_listbox.delete(0, tk.END)

    def load_file(self):
        if self.running:
            messagebox.showwarning("경고", "실행 중에는 불러올 수 없습니다. 중지 후 다시 시도하세요.")
            return

        file_path = filedialog.askopenfilename(
            title="매크로 파일 불러오기",
            filetypes=[("Macro JSON", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 리스트 복원
            self.macro_listbox.delete(0, tk.END)
            items = data.get("items", [])
            for s in items:
                if self._is_valid_macro_line(s):  # ← 여기서 조건 포함 항목까지 복원
                    self.macro_listbox.insert(tk.END, s)

            # 설정 복원
            settings = data.get("settings", {})
            if "repeat" in settings:
                self.settings["repeat"] = settings["repeat"]
            if "start_delay" in settings:
                self.settings["start_delay"] = settings["start_delay"]

            # 단축키 복원
            hotkeys = data.get("hotkeys", {})
            if hotkeys:
                self.hotkeys.update(hotkeys)
                if KEYBOARD_AVAILABLE:
                    self._register_hotkeys()

            messagebox.showinfo("불러오기 완료", "매크로 파일을 불러왔습니다.")

        except Exception as e:
            messagebox.showerror("불러오기 실패", f"파일을 불러오는 중 오류 발생:\n{e}")

    def _is_valid_macro_line(self, s: str) -> bool:
        """저장된 한 줄이 우리 포맷(조건/조건끝/들여쓰기 포함)에 맞는지 간단 검사."""
        if not isinstance(s, str):
            return False
        # 최상위 항목
        if s.startswith(("키보드:", "마우스:", "시간:", "조건:", "조건끝")):
            return True
        # 들여쓰기된 내부 항목 (조건 블록 내부)
        if s.startswith("  "):  # 공백 2칸
            inner = s[2:]
            return inner.startswith(("키보드:", "마우스:", "시간:"))
        return False


    def save_file(self):
        if self.running:
            messagebox.showwarning("저장 불가", "실행 중에는 저장할 수 없습니다. 중지 후 다시 시도하세요.")
            return

        path = filedialog.asksaveasfilename(
            title="매크로 저장하기",
            defaultextension=".json",
            filetypes=[("Macro JSON", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            data = {
                "version": 1,
                "items": [self.macro_listbox.get(i) for i in range(self.macro_listbox.size())],
                "settings": {
                    "repeat": self.settings.get("repeat", 1),
                    "start_delay": self.settings.get("start_delay", 3),
                },
                "hotkeys": {
                    "start": self.hotkeys.get("start"),
                    "stop": self.hotkeys.get("stop"),
                },
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("완료", "저장이 완료되었습니다.")
        except Exception as e:
            messagebox.showerror("에러", f"저장 실패:\n{e}")

    def _display_key_name(self, key: str | None) -> str:
        if not key:
            return ""
        # keyboard 라이브러리 표기 → Tk 표기와 크게 다르지 않으므로 그대로 표시
        # 필요 시 매핑을 추가로 구현해도 됩니다.
        return key.upper() if len(key) == 1 else key

    # ============== 설정창 ==============
    def open_settings(self):
        # 이미 열려 있으면 포커스
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

        # 반복 횟수
        tk.Label(frm, text="반복 횟수 (0=무한)").grid(row=0, column=0, sticky="w")
        self.repeat_var = tk.IntVar(value=self.settings["repeat"])
        tk.Spinbox(frm, from_=0, to=9999, width=8, textvariable=self.repeat_var).grid(row=0, column=1, sticky="w", padx=8)

        # 시작 지연
        tk.Label(frm, text="시작 지연 (초)").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.delay_var = tk.IntVar(value=self.settings["start_delay"])
        tk.Spinbox(frm, from_=0, to=600, width=8, textvariable=self.delay_var).grid(row=1, column=1, sticky="w", padx=8, pady=(8,0))

        # 단축키 (시작/중지)
        self.start_key_var = tk.StringVar(value=self.hotkeys.get("start") or "")
        self.stop_key_var  = tk.StringVar(value=self.hotkeys.get("stop")  or "")

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

        # 닫기
        tk.Button(frm, text="닫기", command=lambda: self.apply_and_close_settings(win)).grid(row=row + 2, column=0, columnspan=3, pady=6)

        # 키 바인딩
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
        self._close_settings(win)

    def _close_settings(self, win):
        try:
            win.grab_release()
        except:
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
            except:
                pass
            cap.destroy()

        def on_key(e):
            keysym = e.keysym
            key_for_keyboard = self._normalize_key_for_keyboard(keysym)
            if not key_for_keyboard:
                messagebox.showwarning("지원하지 않는 키", f"이 키는 전역 단축키로 설정하기 어렵습니다: {keysym}")
                return
            if which == "start":
                self.start_key_var.set(keysym)
                self.hotkeys["start"] = key_for_keyboard
            else:
                self.stop_key_var.set(keysym)
                self.hotkeys["stop"] = key_for_keyboard

            if KEYBOARD_AVAILABLE:
                self._register_hotkeys()
            else:
                messagebox.showwarning("전역 단축키 비활성화", "keyboard 라이브러리가 없어 단축키가 적용되지 않습니다.")
            close_cap()

        cap.bind("<Key>", on_key)
        cap.bind("<Escape>", lambda e: close_cap())

    def _normalize_key_for_keyboard(self, keysym: str):
        if not keysym:
            return None
        k = keysym
        if len(k) == 1:
            return k.lower()
        mapping = {
            "Return": "enter",
            "Escape": "esc",
            "BackSpace": "backspace",
            "Tab": "tab",
            "space": "space",
            "Up": "up",
            "Down": "down",
            "Left": "left",
            "Right": "right",
            "Home": "home",
            "End": "end",
            "Prior": "page up",
            "Next": "page down",
            "Insert": "insert",
            "Delete": "delete",
        }
        if k.startswith("F") and k[1:].isdigit():
            return k.lower()
        return mapping.get(k, None)

    def _register_hotkeys(self):
        if not KEYBOARD_AVAILABLE:
            return
        for k in ("start", "stop"):
            h = self.hotkey_handles.get(k)
            if h is not None:
                try:
                    keyboard.remove_hotkey(h)
                except:
                    pass
                self.hotkey_handles[k] = None

        if self.hotkeys.get("start"):
            self.hotkey_handles["start"] = keyboard.add_hotkey(
                self.hotkeys["start"], lambda: self.root.after(0, self.run_macros)
            )
        if self.hotkeys.get("stop"):
            self.hotkey_handles["stop"] = keyboard.add_hotkey(
                self.hotkeys["stop"], lambda: self.root.after(0, self.stop_execution)
            )

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

        key_window.bind("<Key>", on_key)
        key_window.focus_set()

    def add_mouse(self):
        mouse_win = tk.Toplevel(self.root)
        mouse_win.title("마우스 입력")
        mouse_win.geometry("320x220+540+340")
        mouse_win.resizable(False, False)

        # 포커스 & 모달 처리
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
        btnf = tk.Frame(frame); btnf.pack(pady=6)
        tk.Radiobutton(btnf, text="왼쪽 클릭",  variable=btn_var, value="left").grid(row=0, column=0, padx=6)
        tk.Radiobutton(btnf, text="오른쪽 클릭", variable=btn_var, value="right").grid(row=0, column=1, padx=6)

        captured = {"x": None, "y": None}

        def tick():
            x, y = pyautogui.position()
            pos_var.set(f"현재 좌표: ({x}, {y})")
            mouse_win.after(80, tick)
        tick()

        def capture():
            x, y = pyautogui.position()
            try:
                # ImageGrab로 화면 캡처
                img = ImageGrab.grab()
                r, g, b = img.getpixel((x, y))
            except Exception as e:
                messagebox.showwarning("오류", f"화면 캡처에 실패했습니다.\n{e}")
                return
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
            except:
                pass
            mouse_win.destroy()

        mouse_win.bind("<Return>", lambda e: capture())
        mouse_win.bind("<Control-Return>", lambda e: add_item())
        mouse_win.bind("<Escape>", lambda e: on_close())

        btns = tk.Frame(frame); btns.pack(pady=10)
        tk.Button(btns, text="좌표 캡처 (Enter)", width=16, command=capture).grid(row=0, column=0, padx=5)
        tk.Button(btns, text="추가 (Ctrl+Enter)", width=16, command=add_item).grid(row=0, column=1, padx=5)
        tk.Button(frame, text="취소 (Esc)", command=on_close).pack(pady=6)

    def add_delay(self):
        sec = simpledialog.askinteger("대기 시간", "대기할 초를 입력하세요:", minvalue=1, maxvalue=600)
        if sec:
            line = f"시간:{sec}"
            self._insert_smart(line)

    def _execute_item(self, item: str):
        """리스트 한 줄(키보드/마우스/시간)을 실행한다."""
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
            self._mouse_move_click(x, y, button)

        elif item.startswith("시간:"):
            sec = int(item.split(":", 1)[1])
            end = time.time() + sec
            while time.time() < end:
                if self.stop_flag:
                    break
                time.sleep(0.05)

    def delete_macro(self):
        if self.running:
            messagebox.showwarning("삭제 불가", "실행 중에는 삭제할 수 없습니다. 중지 후 다시 시도하세요.")
            return
        sel = self.macro_listbox.curselection()
        if not sel:
            messagebox.showwarning("삭제 실패", "선택된 매크로가 없습니다.")
            return
        idx = sel[0]
        line = self.macro_listbox.get(idx)
        if line.startswith("조건:"):
            # 블록 전체 삭제
            end = idx + 1
            size = self.macro_listbox.size()
            while end < size and not self.macro_listbox.get(end).startswith("조건끝"):
                end += 1
            if end < size:
                self.macro_listbox.delete(idx, end)  # '조건끝' 포함
            else:
                self.macro_listbox.delete(idx)
        else:
            self.macro_listbox.delete(idx)

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
            # 시작 지연
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
                items = [self.macro_listbox.get(i) for i in range(self.macro_listbox.size())]
                i = 0
                n = len(items)
                while i < n and not self.stop_flag:
                    item = items[i]

                    # ----- 이미지 조건 블록 -----
                    if item.startswith("조건:"):
                        # 헤더 표시
                        self._highlight_index(i)

                        # 1) 헤더 파싱: 조건:x,y=R,G,B
                        try:
                            cond_body = item.split(":", 1)[1]
                            pos_str, rgb_str = cond_body.split("=")
                            cx_str, cy_str = pos_str.split(",")
                            rx_str, gy_str, bz_str = rgb_str.split(",")
                            cx, cy = int(cx_str), int(cy_str)
                            r_t, g_t, b_t = int(rx_str), int(gy_str), int(bz_str)
                        except Exception:
                            # 파싱 실패: 블록을 그냥 스킵
                            i += 1
                            while i < n and not items[i].startswith("조건끝"):
                                i += 1
                            i += 1
                            continue

                        # 2) 서브아이템 수집 (인덱스와 함께)
                        sub = []  # [(index_in_items, stripped_line), ...]
                        j = i + 1
                        while j < n:
                            line = items[j]
                            if line.startswith("조건끝"):
                                break
                            if line.startswith("  "):
                                sub.append((j, line[2:]))  # 실제 인덱스, 앞 2칸 제거된 실행 라인
                            else:
                                break
                            j += 1

                        # 3) 픽셀 캡처 & 비교
                        try:
                            img = ImageGrab.grab()
                            pix = img.getpixel((cx, cy))
                            match = (pix[0] == r_t and pix[1] == g_t and pix[2] == b_t)
                        except Exception:
                            match = False

                        # 4) 일치하면 서브아이템 실행 (실제 인덱스 하이라이트)
                        if match:
                            for idx_run, sub_item in sub:
                                if self.stop_flag:
                                    break
                                self._highlight_index(idx_run)
                                self._execute_item(sub_item)

                        # 5) 블록 다음으로 이동
                        i = j + 1 if j < n and items[j].startswith("조건끝") else j
                        continue

                    # ----- 일반 항목 -----
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
        self._clear_highlight()  # 추가: 하이라이트 해제

    def _mouse_move_click(self, x: int, y: int, button: str = "left"):
        """
        마우스를 (x,y)로 이동 후 지정 버튼으로 클릭.
        가능하면 AutoIt 사용, 불가하면 pyautogui로 폴백.
        button: "left" | "right"
        """
        b = "left" if button not in ("left", "right") else button

        # (선택) 좌표 안전성: 화면 범위 밖이면 바로 리턴
        try:
            scr_w, scr_h = pyautogui.size()
            if not (0 <= x < scr_w and 0 <= y < scr_h):
                # 워커 스레드에서 뜰 수 있으니 after로 안전하게 UI 쓰기
                self.root.after(0, lambda: messagebox.showwarning(
                    "좌표 오류", f"화면 범위를 벗어난 좌표입니다: ({x}, {y})"))
                return
        except Exception:
            pass

        if AUTOIT_AVAILABLE:
            try:
                # 이동 & 클릭 (즉시)
                autoit.mouse_move(x, y, speed=0)
                autoit.mouse_click(b, x, y, clicks=1, speed=0)
                return
            except Exception as e:
                # AutoIt 호출 실패 시 pyautogui 폴백
                self.root.after(0, lambda: messagebox.showwarning(
                    "AutoIt 오류", f"AutoIt 마우스 동작 중 오류가 발생하여 pyautogui로 폴백합니다.\n\n{e}"))

        # 폴백: pyautogui
        try:
            pyautogui.moveTo(x, y)
            pyautogui.click(x=x, y=y, button=b)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "마우스 오류", f"마우스 동작 실패:\n{e}"))

    def add_image_condition(self):
        win = tk.Toplevel(self.root)
        win.title("이미지 조건")
        win.geometry("360x220+560+320")
        win.resizable(False, False)
        win.transient(self.root)
        win.lift();
        win.grab_set();
        win.focus_force()

        frm = tk.Frame(win, padx=10, pady=10);
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
            try:
                img = ImageGrab.grab()
                r, g, b = img.getpixel((x, y))
                rgb_var.set(f"RGB: ({r}, {g}, {b})")
            except Exception:
                rgb_var.set("RGB: (---, ---, ---)")
            win.after(120, tick)

        tick()

        def capture():
            x, y = pyautogui.position()
            try:
                img = ImageGrab.grab()
                r, g, b = img.getpixel((x, y))
            except Exception as e:
                messagebox.showwarning("오류", f"화면 캡처에 실패했습니다.\n{e}")
                return
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
            except:
                pass
            win.destroy()

        btns = tk.Frame(frm);
        btns.pack(pady=8)
        tk.Button(btns, text="좌표/색 캡처 (Enter)", command=capture).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="조건 추가", command=apply_block).grid(row=0, column=1, padx=6)
        tk.Button(frm, text="취소 (Esc)", command=lambda: (win.grab_release(), win.destroy())).pack(pady=4)

        win.bind("<Return>", lambda e: capture())
        win.bind("<Escape>", lambda e: (win.grab_release(), win.destroy()))

    def _get_condition_bounds_if_any(self, idx: int):
        size = self.macro_listbox.size()
        if idx < 0 or idx >= size:
            return None

        # 위로 올라가며 '조건:' 찾기
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

        # 아래로 내려가며 '조건끝' 찾기
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

    def _insert_under_condition(self, text: str, sel_idx: int | None):
        """
        sel_idx가 조건 헤더/내부라면, 들여쓰기하여 '조건끝' 앞에 삽입.
        sel_idx가 헤더면 헤더 바로 다음, 내부면 해당 라인 다음.
        sel_idx가 블록 외라면 False를 반환하여 일반 삽입 흐름으로.
        """
        if sel_idx is None:
            return False

        bounds = self._get_condition_bounds_if_any(sel_idx)
        if not bounds:
            return False

        start, end = bounds
        # 삽입 위치 결정
        cur_line = self.macro_listbox.get(sel_idx)
        if cur_line.startswith("조건:"):
            insert_pos = start + 1
        elif sel_idx < end:
            insert_pos = sel_idx + 1
        else:
            insert_pos = end

        self.macro_listbox.insert(insert_pos, "  " + text)  # 들여쓰기 2칸
        return True

    def _insert_smart(self, text: str):
        sel = self.macro_listbox.curselection()
        # 선택 없으면 맨 아래
        if not sel:
            self.macro_listbox.insert(tk.END, text)
            return

        idx = sel[0]
        line = self.macro_listbox.get(idx)

        # 1) 조건끝이면, 블록 밖으로: 들여쓰기 없이 idx+1 위치
        if line.startswith("조건끝"):
            self.macro_listbox.insert(idx + 1, text)
            return

        # 2) 선택이 블록 내부인지 판단
        bounds = self._get_condition_bounds_if_any(idx)
        if bounds:
            start, end = bounds
            # 헤더면 헤더 바로 아래, 내부라면 현재 줄 아래
            insert_pos = start + 1 if line.startswith("조건:") else (idx + 1)
            self.macro_listbox.insert(insert_pos, "  " + text)  # 들여쓰기 2칸
            return

        # 3) 블록 외부: 선택 줄 바로 아래
        self.macro_listbox.insert(idx + 1, text)

    def _highlight_index(self, idx: int):
        """리스트에서 idx를 선택/포커스해서 실행 중임을 표시."""

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
        """실행 종료/중지 시 선택 해제."""

        def do():
            try:
                self.macro_listbox.selection_clear(0, tk.END)
            except Exception:
                pass

        self.root.after(0, do)
