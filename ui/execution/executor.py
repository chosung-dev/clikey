import time
import threading
import tkinter as tk
import pyautogui
from typing import Callable, Optional

from core.mouse import mouse_move_click
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
            delay = max(0, int(settings.get("start_delay", 0)))
            if delay > 0:
                for _ in range(delay * 10):
                    if self.stop_flag:
                        break
                    time.sleep(0.1)
            if self.stop_flag:
                return

            repeat = int(settings.get("repeat", 1))
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
            body = item.split(":", 1)[1]
            coord, button = body.split(":")
            x_str, y_str = coord.split(",")
            x, y = int(x_str), int(y_str)
            mouse_move_click(self.root, x, y, button)

        elif item.startswith("시간:"):
            sec = float(item.split(":", 1)[1])
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