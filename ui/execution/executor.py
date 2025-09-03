import time
import threading
import tkinter as tk
import pyautogui
from typing import Callable, Optional

from core.screen import grab_rgb_at


class MacroExecutor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.running = False
        self.stop_flag = False
        self.worker_thread = None
        self.highlight_callback: Optional[Callable[[int], None]] = None
        self.clear_highlight_callback: Optional[Callable[[], None]] = None
        self.finish_callback: Optional[Callable[[], None]] = None

    def set_callbacks(self, 
                     highlight_cb: Callable[[int], None],
                     clear_highlight_cb: Callable[[], None],
                     finish_cb: Callable[[], None]):
        self.highlight_callback = highlight_cb
        self.clear_highlight_callback = clear_highlight_cb  
        self.finish_callback = finish_cb

    def start_execution(self, items: list[str], settings: dict):
        if self.running:
            return False
            
        if not items:
            return False

        self.running = True
        self.stop_flag = False
        
        self.worker_thread = threading.Thread(
            target=self._execute_worker, 
            args=(items, settings), 
            daemon=True
        )
        self.worker_thread.start()
        return True

    def stop_execution(self):
        if not self.running:
            return
        self.stop_flag = True

    def _execute_worker(self, items: list[str], settings: dict):
        try:
            delay_sec = max(0, float(settings.get("start_delay", 0)))
            self._sleep(delay_sec)
            if self.stop_flag:
                return

            repeat = int(settings.get("repeat", 1))
            step_delay = float(settings.get("step_delay", 0.001))
            loop_inf = (repeat == 0)
            loops = 0

            while (loop_inf or loops < repeat) and not self.stop_flag:
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
                            # 조건 파싱 실패 시 들여쓰기된 블록 전체를 건너뛰기
                            i += 1
                            while i < n and items[i].startswith("  "):
                                i += 1
                            continue

                        sub = []
                        j = i + 1
                        while j < n:
                            line = items[j]
                            if line.startswith("  "):
                                sub.append((j, line[2:]))
                                j += 1
                            else:
                                break

                        pix = grab_rgb_at(cx, cy)
                        match = (pix == (r_t, g_t, b_t))

                        if match:
                            for idx_run, sub_item in sub:
                                if self.stop_flag:
                                    break
                                self._highlight_index(idx_run)
                                self._execute_item(sub_item)
                                if step_delay > 0 and not self.stop_flag:
                                    time.sleep(step_delay)

                        i = j
                        continue

                    self._highlight_index(i)
                    self._execute_item(item)
                    if step_delay > 0 and not self.stop_flag:
                        time.sleep(step_delay)
                    i += 1

                if self.stop_flag:
                    break
                loops += 1
        finally:
            self.root.after(0, self._finish_execution)

    def _execute_item(self, item: str):
        if self.stop_flag:
            return

        if item.strip() == "매크로중지":
            self.stop_flag = True
            return

        elif item.startswith("키보드:"):
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
            from core.mouse import mouse_move_click, mouse_move_only, mouse_down_at_current, mouse_up_at_current
            
            body = item.split(":", 1)[1]
            parts = body.split(":")
            
            # 현재 위치에서 동작하는 명령들: 마우스:누름:button, 마우스:떼기:button
            if len(parts) == 2 and parts[0] in ("누름", "떼기"):
                action, button = parts
                if action == "누름":
                    mouse_down_at_current(button)
                elif action == "떼기":
                    mouse_up_at_current(button)
            else:
                # 좌표가 포함된 명령들: 마우스:x,y:button, 마우스:x,y:이동
                try:
                    coord_part = parts[0]
                    x_str, y_str = coord_part.split(",")
                    x, y = int(x_str), int(y_str)
                    
                    if len(parts) >= 2:
                        action_or_button = parts[1]
                        if action_or_button == "이동":
                            mouse_move_only(x, y)
                        else:
                            mouse_move_click(x, y, action_or_button)
                    else:
                        mouse_move_click(x, y, "left")
                except (ValueError, IndexError):
                    pass

        elif item.startswith("시간:"):
            sec = float(item.split(":", 1)[1])
            self._sleep(sec)

    def _sleep(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if self.stop_flag:
                break
            time.sleep(0.05)

    def _highlight_index(self, idx: int):
        if self.highlight_callback:
            self.root.after(0, lambda: self.highlight_callback(idx))

    def _finish_execution(self):
        self.running = False
        self.stop_flag = False
        if self.clear_highlight_callback:
            self.clear_highlight_callback()
        if self.finish_callback:
            self.finish_callback()