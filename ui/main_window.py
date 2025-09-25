import os
import json
import tkinter as tk
from tkinter import messagebox, filedialog
import pyautogui

from core.state import default_settings, default_hotkeys
from core.keyboard_hotkey import register_hotkeys
from core.persistence import export_data, load_macro_data, load_app_state, save_app_state
from core.macro_block import MacroBlock
from core.event_types import EventType
from ui.macro_list import MacroListManager
from ui.execution.executor import MacroExecutor
from ui.execution.highlighter import MacroHighlighter
from ui.dialogs.settings import SettingsDialog
from ui.dialogs.input_dialogs import InputDialogs
from ui.dialogs.condition_dialog import ConditionDialog


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


class MacroUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Namaan's Macro")
        self.root.geometry("500x450")

        # 상태
        self.running = False
        
        # 설정/단축키
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        self.hotkey_handles = {"start": None, "stop": None}

        # 파일 상태
        self.current_path: str | None = None
        self.is_dirty: bool = False

        # UI 컴포넌트 초기화
        self._init_components()
        
        # UI 빌드
        self._build_menu()
        self._build_layout()
        self._bind_events()
        self._register_hotkeys_if_available()
        self._restore_last_file()

    def _init_components(self):
        # 매크로 리스트 관리자는 레이아웃에서 초기화
        self.macro_list = None
        
        # 실행 엔진
        self.executor = MacroExecutor(self.root)
        self.highlighter = None  # 리스트박스 생성 후 초기화
        
        # 다이얼로그들
        self.settings_dialog = None
        self.input_dialogs = None
        self.condition_dialog = None

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="새로 만들기", command=self.new_file)
        file_menu.add_command(label="열기", command=self.load_file)
        file_menu.add_command(label="저장", command=self.save_file)
        file_menu.add_command(label="다른 이름으로 저장", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.request_quit)
        menubar.add_cascade(label="파일", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="실행취소", accelerator="Ctrl+Z", command=self._on_undo)
        edit_menu.add_separator()
        edit_menu.add_command(label="복사", accelerator="Ctrl+C", command=self._on_copy)
        edit_menu.add_command(label="잘라내기", accelerator="Ctrl+X", command=self._on_cut)
        edit_menu.add_command(label="붙여넣기", accelerator="Ctrl+V", command=self._on_paste)
        edit_menu.add_separator()
        edit_menu.add_command(label="삭제", accelerator="Delete", command=self.delete_macro)
        menubar.add_cascade(label="편집", menu=edit_menu)

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

        # 매크로 리스트 관리자 초기화
        self.macro_list = MacroListManager(left_frame, self._mark_dirty)
        self.macro_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        # 하이라이터 초기화
        self.highlighter = MacroHighlighter(self.macro_list.macro_listbox)
        
        # 실행기 콜백 설정
        self.executor.set_callbacks(
            highlight_cb=self.highlighter.highlight_index,
            clear_highlight_cb=self.highlighter.clear_highlight,
            finish_cb=self._finish_execution
        )
        
        # 다이얼로그 초기화
        self.settings_dialog = SettingsDialog(
            self.root, self.settings, self.hotkeys, 
            self._mark_dirty, self._register_hotkeys_if_available
        )
        self.input_dialogs = InputDialogs(self.root, self.macro_list.insert_macro_block)
        self.condition_dialog = ConditionDialog(self.root, self.macro_list.insert_macro_block)

        # 오른쪽 버튼들
        tk.Button(right_frame, text="키보드", width=18, command=self.add_keyboard).pack(pady=6)
        tk.Button(right_frame, text="마우스", width=18, command=self.add_mouse).pack(pady=6)
        tk.Button(right_frame, text="딜레이", width=18, command=self.add_delay).pack(pady=6)
        tk.Button(right_frame, text="색상조건", width=18, command=self.add_image_condition).pack(pady=6)
        tk.Button(right_frame, text="이미지조건", width=18, command=self.add_image_match_condition).pack(pady=6)
        tk.Button(right_frame, text="중지", width=18, command=self.add_stop_macro).pack(pady=6)
        tk.Button(right_frame, text="지우기", width=18, command=self.delete_macro).pack(pady=16)

        self.run_btn = tk.Button(right_frame, text="▶ 실행하기", width=18, command=self.run_macros)
        self.run_btn.pack(pady=6)
        self.stop_btn = tk.Button(right_frame, text="■ 중지", width=18, state=tk.DISABLED, command=self.stop_execution)
        self.stop_btn.pack(pady=6)

    def _bind_events(self):
        self.root.bind("<Control-s>", self._on_save)
        self.root.bind("<Control-c>", self._on_copy)
        self.root.bind("<Control-x>", self._on_cut)
        self.root.bind("<Control-v>", self._on_paste)
        self.root.bind("<Control-z>", self._on_undo)

    def _register_hotkeys_if_available(self):
        register_hotkeys(self.root, self)

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
            data = load_macro_data(file_path)

            macro_blocks = [MacroBlock.from_dict(block_data) for block_data in data["macro_blocks"]]
            self.macro_list.load_macro_blocks(macro_blocks)

            settings = data.get("settings", {})
            if "repeat" in settings:
                self.settings["repeat"] = int(settings["repeat"])
            if "start_delay" in settings:
                self.settings["start_delay"] = float(settings["start_delay"])
            if "step_delay" in settings:
                self.settings["step_delay"] = float(settings["step_delay"])
            if "beep_on_finish" in settings:
                self.settings["beep_on_finish"] = bool(settings["beep_on_finish"])

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

            # 설정 다이얼로그를 새로운 설정으로 다시 생성
            self.settings_dialog = SettingsDialog(
                self.root, self.settings, self.hotkeys, 
                self._mark_dirty, self._register_hotkeys_if_available
            )

            return True
        except Exception as e:
            messagebox.showerror("불러오기 실패", f"파일을 불러오는 중 오류 발생:\n{e}")
            return False

    def _collect_export_data(self) -> dict:
        """Collect data for export using MacroBlock format."""
        macro_blocks = self.macro_list.get_macro_blocks()
        return export_data(macro_blocks, self.settings, self.hotkeys)

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
        self.macro_list.clear()
        self.settings = default_settings()
        self.hotkeys = default_hotkeys()
        self._register_hotkeys_if_available()
        self.current_path = None
        self._mark_dirty(False)
        
        # 설정 다이얼로그를 새로운 설정으로 다시 생성
        self.settings_dialog = SettingsDialog(
            self.root, self.settings, self.hotkeys, 
            self._mark_dirty, self._register_hotkeys_if_available
        )

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
        self._open_path(file_path)

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
        self.settings_dialog.open_settings()

    # ---------- 매크로 추가 ----------
    def add_keyboard(self):
        self.input_dialogs.add_keyboard()

    def add_mouse(self):
        # 현재 선택된 매크로 블록이 이미지 조건인지 확인
        selected_blocks = self.macro_list.get_selected_macro_blocks()
        selected_condition_block = None

        if selected_blocks:
            for block in selected_blocks:
                if hasattr(block, 'event_type') and block.event_type == EventType.IF and hasattr(block, 'condition_type') and block.condition_type:
                    selected_condition_block = block
                    break

        self.input_dialogs.add_mouse(selected_condition_block)

    def add_delay(self):
        self.input_dialogs.add_delay()

    def add_image_condition(self):
        self.condition_dialog.add_image_condition()

    def add_image_match_condition(self):
        self.condition_dialog.add_image_match_condition()

    def add_stop_macro(self):
        from core.macro_factory import MacroFactory
        exit_block = MacroFactory.create_exit_block(True, )
        self.macro_list.insert_macro_block(exit_block)

    def delete_macro(self):
        selected_blocks = self.macro_list.get_selected_macro_blocks()
        if not selected_blocks:
            return

        self.macro_list.delete_selected()

        # Update selection after deletion
        size = self.macro_list.size()
        if size > 0:
            # Select the first available item
            self.macro_list.macro_listbox.selection_clear(0, tk.END)
            self.macro_list.macro_listbox.selection_set(0)
            self.macro_list.macro_listbox.activate(0)
            self.macro_list.macro_listbox.see(0)
            self.macro_list.selected_indices = [0]

    # ---------- 실행/중지 ----------
    def run_macros(self):
        if self.running:
            messagebox.showinfo("안내", "이미 실행 중입니다.")
            return
        if self.macro_list.size() == 0:
            messagebox.showwarning("실행 불가", "매크로 리스트가 비어있습니다.")
            return

        self.running = True
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        macro_blocks = self.macro_list.get_macro_blocks()
        if self.executor.start_execution(macro_blocks, self.settings):
            pass
        else:
            self._finish_execution()

    def stop_execution(self):
        if not self.running:
            return
        self.executor.stop_execution()

    def _finish_execution(self):
        self.running = False
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if self.settings.get("beep_on_finish", True):
            try:
                self.root.bell()
            except Exception:
                pass

    def _on_save(self, event=None):
        self.save_file()
        return "break"

    def _on_copy(self, event=None):
        if self.macro_list:
            self.macro_list._on_copy(event)
        return "break"

    def _on_cut(self, event=None):
        if self.macro_list:
            self.macro_list._on_cut(event)
        return "break"

    def _on_paste(self, event=None):
        if self.macro_list:
            self.macro_list._on_paste(event)
        return "break"

    def _on_undo(self, event=None):
        if self.macro_list:
            self.macro_list._on_undo(event)
        return "break"


if __name__ == "__main__":
    root = tk.Tk()
    app = MacroUI(root)
    root.mainloop()