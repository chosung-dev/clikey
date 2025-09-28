import tkinter as tk
from tkinter import messagebox
import pyautogui
from typing import Callable

from core.screen import grab_rgb_at
from core.macro_block import MacroBlock
from core.macro_factory import MacroFactory


class InputDialogs:
    def __init__(self, parent: tk.Tk, insert_callback: Callable[[MacroBlock], None], is_edit_mode_callback: Callable[[], bool] = None, cancel_edit_callback: Callable[[], None] = None):
        self.parent = parent
        self.insert_callback = insert_callback
        self.is_edit_mode_callback = is_edit_mode_callback
        self.cancel_edit_callback = cancel_edit_callback

    def add_keyboard(self):
        key_window = tk.Toplevel(self.parent)
        key_window.geometry("320x120+520+320")

        key_window.transient(self.parent)
        key_window.lift()
        key_window.attributes("-topmost", True)
        key_window.grab_set()
        key_window.focus_force()
        key_window.bind("<Map>", lambda e: key_window.focus_force())
        key_window.after(200, lambda: key_window.attributes("-topmost", False))

        frame = tk.Frame(key_window, bd=2, relief=tk.RAISED)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="원하는 키를 눌러주세요", font=("맑은 고딕", 12)).pack(pady=20)

        tk.Button(frame, text="취소", command=key_window.destroy).pack(pady=8)

        def on_key(event):
            key = event.keysym
            macro_block = MacroFactory.create_keyboard_block(key)
            self.insert_callback(macro_block)
            key_window.destroy()

        key_window.bind("<Key>", on_key)
        key_window.focus_set()

        # X버튼 클릭 시에도 편집 모드 해제
        def on_close_keyboard():
            if self.cancel_edit_callback:
                self.cancel_edit_callback()
            key_window.destroy()

        key_window.protocol("WM_DELETE_WINDOW", on_close_keyboard)

    def add_mouse(self, selected_condition_block=None):
        mouse_win = tk.Toplevel(self.parent)
        mouse_win.title("마우스 입력")
        mouse_win.geometry("400x380+540+320")
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
        selected_reference = {"block": None, "display_name": None}

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
            if selected_reference["block"] and selected_reference["display_name"]:
                pos_var.set(f"현재 좌표: {selected_reference['display_name']}")
            else:
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
            # 상위좌표 모드를 해제하고 일반 좌표 캡처 모드로 전환
            selected_reference["block"] = None
            selected_reference["display_name"] = None
            info.config(text=f"캡처됨: ({x}, {y}) / RGB=({r},{g},{b})")

        def add_item():
            action = action_var.get()
            button = btn_var.get()

            # 누르고있기와 뗼기는 좌표가 필요없음 (현재 위치에서 동작)
            if action in ("down", "up"):
                if action == "down":
                    macro_block = MacroFactory.create_mouse_block(button, "down", 0, 0)
                else:  # action == "up"
                    macro_block = MacroFactory.create_mouse_block(button, "up", 0, 0)
                self.insert_callback(macro_block)
                on_close()
                return

            # 상위좌표가 선택된 경우
            if selected_reference["block"] and selected_reference["display_name"]:
                if action == "move":
                    macro_block = MacroFactory.create_mouse_block("left", "move", 0, 0)
                else:  # click
                    macro_block = MacroFactory.create_mouse_block(button, "click", 0, 0)

                # 상위좌표 참조 설정
                macro_block.position = "@parent"

                self.insert_callback(macro_block)
                on_close()
                return

            # 클릭과 이동하기는 좌표가 필요함
            if captured["x"] is None:
                messagebox.showwarning("안내", "먼저 좌표를 캡처하세요.")
                return

            x, y = captured['x'], captured['y']
            if action == "click":
                macro_block = MacroFactory.create_mouse_block(button, "click", x, y)
            elif action == "move":
                macro_block = MacroFactory.create_mouse_block("left", "move", x, y)
            else:
                # 기본값
                macro_block = MacroFactory.create_mouse_block(button, "click", x, y)

            self.insert_callback(macro_block)
            on_close()

        def on_close():
            try:
                mouse_win.grab_release()
            except Exception:
                pass
            # 편집 모드 취소
            if self.cancel_edit_callback:
                self.cancel_edit_callback()
            mouse_win.destroy()

        mouse_win.bind("<Return>", lambda e: capture())
        mouse_win.bind("<Control-Return>", lambda e: add_item())
        mouse_win.bind("<Escape>", lambda e: on_close())

        # X버튼 클릭 시에도 편집 모드 해제
        mouse_win.protocol("WM_DELETE_WINDOW", on_close)

        btns = tk.Frame(frame)
        btns.pack(pady=10)
        tk.Button(btns, text="좌표 캡처 (Enter)", width=16, command=capture).grid(row=0, column=0, padx=5)

        # 상위좌표 버튼 - 선택된 조건이 있거나 다른 이미지 조건이 있을 때 활성화
        def on_reference_click():
            if selected_condition_block:
                # 선택된 조건을 상위좌표로 설정
                selected_reference["block"] = selected_condition_block
                selected_reference["display_name"] = selected_condition_block.event_data
                # 캡처된 좌표 정보 초기화
                captured["x"] = None
                captured["y"] = None
                info.config(text=f"상위좌표 선택됨: {selected_condition_block.event_data}\n[추가] 버튼을 클릭하세요.")
            else:
                # 다른 이미지 조건을 선택할 수 있도록 기존 함수 호출
                def on_reference_selected(block):
                    # 선택된 블록을 상위좌표로 설정
                    selected_reference["block"] = block
                    selected_reference["display_name"] = block.event_data
                    # 캡처된 좌표 정보 초기화
                    captured["x"] = None
                    captured["y"] = None
                    info.config(text=f"상위좌표 선택됨: {block.event_data}\n[추가] 버튼을 클릭하세요.")

                self.show_reference_selector_with_callback(mouse_win, on_reference_selected)

        ref_btn = tk.Button(btns, text="상위좌표", width=16, command=on_reference_click)
        ref_btn.grid(row=0, column=1, padx=5)

        # 초기 상태에서 버튼 상태 확인
        self.update_reference_button_state(ref_btn, selected_condition_block)

        # 편집 모드에 따라 버튼 텍스트 결정
        button_text = "수정 (Ctrl+Enter)" if self.is_edit_mode_callback and self.is_edit_mode_callback() else "추가 (Ctrl+Enter)"
        tk.Button(btns, text=button_text, width=16, command=add_item).grid(row=1, column=0, columnspan=2, padx=5, pady=5)
        tk.Button(frame, text="취소 (Esc)", command=on_close).pack(pady=6)

    def add_delay(self):
        delay_window = tk.Toplevel(self.parent)
        delay_window.title("딜레이 시간")
        delay_window.geometry("300x150+540+320")
        delay_window.resizable(False, False)

        delay_window.transient(self.parent)
        delay_window.lift()
        delay_window.attributes("-topmost", True)
        delay_window.grab_set()
        delay_window.focus_force()
        delay_window.bind("<Map>", lambda e: delay_window.focus_force())
        delay_window.after(200, lambda: delay_window.attributes("-topmost", False))

        frame = tk.Frame(delay_window, bd=2, relief=tk.RAISED)
        frame.pack(expand=True, fill="both", padx=6, pady=6)

        tk.Label(frame, text="대기할 초를 입력하세요:", font=("맑은 고딕", 12)).pack(pady=10)

        entry = tk.Entry(frame, font=("맑은 고딕", 10), width=15)
        entry.pack(pady=5)

        # 창이 완전히 로드된 후 입력칸에 포커스 설정
        def set_entry_focus():
            entry.focus_force()
            entry.select_range(0, tk.END)

        delay_window.after(100, set_entry_focus)

        def add_delay_item():
            try:
                sec = float(entry.get())
                if sec < 0 or sec > 3600:
                    messagebox.showwarning("오류", "0~3600 사이의 값을 입력하세요.")
                    return
                macro_block = MacroFactory.create_delay_block(sec)
                self.insert_callback(macro_block)
                delay_window.destroy()
            except ValueError:
                messagebox.showwarning("오류", "유효한 숫자를 입력하세요.")

        def on_close():
            try:
                delay_window.grab_release()
            except:
                pass
            # 편집 모드 취소
            if self.cancel_edit_callback:
                self.cancel_edit_callback()
            delay_window.destroy()

        # 버튼들
        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=10)

        # 편집 모드에 따라 버튼 텍스트 결정
        button_text = "수정" if self.is_edit_mode_callback and self.is_edit_mode_callback() else "추가"

        tk.Button(btn_frame, text=button_text, command=add_delay_item).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="취소", command=on_close).pack(side=tk.LEFT, padx=5)

        # 키 바인딩
        delay_window.bind("<Return>", lambda e: add_delay_item())
        delay_window.bind("<Escape>", lambda e: on_close())

        # X버튼 클릭 시에도 편집 모드 해제
        delay_window.protocol("WM_DELETE_WINDOW", on_close)

    def show_reference_selector(self, parent_win, btn_var, action_var, add_callback, cancel_callback):
        """상위좌표 선택 다이얼로그를 표시"""
        from core.state import GlobalState

        # 사용 가능한 조건 블록들 찾기
        condition_blocks = []
        if hasattr(GlobalState, 'current_macro') and GlobalState.current_macro and hasattr(GlobalState.current_macro, 'macro_blocks'):
            for block in GlobalState.current_macro.macro_blocks:
                if (hasattr(block, 'event_type') and block.event_type.value == 'if' and
                    hasattr(block, 'condition_type') and block.condition_type):
                    condition_blocks.append(block)

        if not condition_blocks:
            messagebox.showinfo("안내", "먼저 조건 블록을 추가해야 합니다.")
            return

        selector_win = tk.Toplevel(parent_win)
        selector_win.title("상위좌표 선택")
        selector_win.geometry("350x300+600+350")
        selector_win.resizable(False, False)
        selector_win.transient(parent_win)
        selector_win.lift()
        selector_win.grab_set()
        selector_win.focus_force()

        frame = tk.Frame(selector_win, padx=10, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="참조할 조건을 선택하세요:", font=("맑은 고딕", 11)).pack(pady=(0, 10))

        # 리스트박스로 image_match 블록들 표시
        listbox = tk.Listbox(frame, height=8)
        listbox.pack(fill="both", expand=True, pady=(0, 10))

        for block in condition_blocks:
            if hasattr(block, 'condition_type') and block.condition_type:
                condition_type_name = "이미지매치" if block.condition_type.value == "image_match" else "RGB매치"
                display_text = f"{block.event_data} ({condition_type_name})"
            else:
                display_text = f"{block.event_data} (조건)"
            listbox.insert(tk.END, display_text)

        selected_block = {"value": None}

        def on_select():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("안내", "조건을 선택하세요.")
                return

            selected_block["value"] = condition_blocks[selection[0]]

            # 마우스 블록 생성
            button = btn_var.get()
            action = action_var.get()

            if action in ("down", "up"):
                macro_block = MacroFactory.create_mouse_block(button, action, 0, 0)
            else:
                # 상위좌표 참조 설정
                reference_text = f"{selected_block['value'].event_data}.x, {selected_block['value'].event_data}.y"
                if action == "move":
                    macro_block = MacroFactory.create_mouse_block("left", "move", 0, 0)
                else:  # click
                    macro_block = MacroFactory.create_mouse_block(button, "click", 0, 0)

                macro_block.position = reference_text

            self.insert_callback(macro_block)
            selector_win.destroy()

        def on_cancel():
            selected_block["value"] = None
            selector_win.destroy()

        btn_frame = tk.Frame(frame)
        btn_frame.pack()
        tk.Button(btn_frame, text="선택", command=on_select, width=10).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="취소", command=on_cancel, width=10).grid(row=0, column=1, padx=5)

        selector_win.bind("<Escape>", lambda e: on_cancel())

    def show_reference_selector_with_callback(self, parent_win, on_select_callback):
        """상위좌표 선택 다이얼로그를 표시하고 선택시 콜백 함수 호출"""
        from core.state import GlobalState

        # 사용 가능한 조건 블록들 찾기
        condition_blocks = []
        if hasattr(GlobalState, 'current_macro') and GlobalState.current_macro and hasattr(GlobalState.current_macro, 'macro_blocks'):
            for block in GlobalState.current_macro.macro_blocks:
                if (hasattr(block, 'event_type') and block.event_type.value == 'if' and
                    hasattr(block, 'condition_type') and block.condition_type):
                    condition_blocks.append(block)

        if not condition_blocks:
            messagebox.showinfo("안내", "먼저 조건 블록을 추가해야 합니다.")
            return

        selector_win = tk.Toplevel(parent_win)
        selector_win.title("상위좌표 선택")
        selector_win.geometry("350x300+600+350")
        selector_win.resizable(False, False)
        selector_win.transient(parent_win)
        selector_win.lift()
        selector_win.grab_set()
        selector_win.focus_force()

        frame = tk.Frame(selector_win, padx=10, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="참조할 조건을 선택하세요:", font=("맑은 고딕", 11)).pack(pady=(0, 10))

        # 리스트박스로 image_match 블록들 표시
        listbox = tk.Listbox(frame, height=8)
        listbox.pack(fill="both", expand=True, pady=(0, 10))

        for block in condition_blocks:
            if hasattr(block, 'condition_type') and block.condition_type:
                condition_type_name = "이미지매치" if block.condition_type.value == "image_match" else "RGB매치"
                display_text = f"{block.event_data} ({condition_type_name})"
            else:
                display_text = f"{block.event_data} (조건)"
            listbox.insert(tk.END, display_text)

        def on_select():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("안내", "조건을 선택하세요.")
                return

            selected_block = condition_blocks[selection[0]]
            on_select_callback(selected_block)
            selector_win.destroy()

        def on_cancel():
            selector_win.destroy()

        btn_frame = tk.Frame(frame)
        btn_frame.pack()
        tk.Button(btn_frame, text="선택", command=on_select, width=10).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="취소", command=on_cancel, width=10).grid(row=0, column=1, padx=5)

        selector_win.bind("<Escape>", lambda e: on_cancel())

    def update_reference_button_state(self, button, selected_condition_block=None):
        """이미지 조건 블록이 있는지 확인하여 버튼 상태 업데이트"""
        # 선택된 조건이 있을 때만 활성화
        if selected_condition_block:
            button.config(state="normal")
        else:
            button.config(state="disabled")