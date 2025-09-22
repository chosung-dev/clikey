import time
import threading
import tkinter as tk
from typing import Callable, Optional, List

from core.macro_executor import MacroExecutor as CoreMacroExecutor
from core.macro_block import MacroBlock


class MacroExecutor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.running = False
        self.stop_flag = False
        self.worker_thread = None
        self.highlight_callback: Optional[Callable[[int], None]] = None
        self.clear_highlight_callback: Optional[Callable[[], None]] = None
        self.finish_callback: Optional[Callable[[], None]] = None
        self.core_executor = None
        self.current_flat_blocks = []

    def set_callbacks(self, 
                     highlight_cb: Callable[[int], None],
                     clear_highlight_cb: Callable[[], None],
                     finish_cb: Callable[[], None]):
        self.highlight_callback = highlight_cb
        self.clear_highlight_callback = clear_highlight_cb  
        self.finish_callback = finish_cb

    def start_execution(self, macro_blocks: List[MacroBlock], settings: dict):
        if self.running:
            return False
            
        if not macro_blocks:
            return False

        self.running = True
        self.stop_flag = False
        
        self.worker_thread = threading.Thread(
            target=self._execute_worker, 
            args=(macro_blocks, settings), 
            daemon=True
        )
        self.worker_thread.start()
        return True

    def stop_execution(self):
        if not self.running:
            return
        self.stop_flag = True

    def _execute_worker(self, macro_blocks: List[MacroBlock], settings: dict):
        try:
            # Create flat list for highlighting
            self.current_flat_blocks = self._create_flat_list(macro_blocks)
            
            # Initial delay
            delay_sec = max(0, float(settings.get("start_delay", 0)))
            self._sleep(delay_sec)
            if self.stop_flag:
                return

            # Setup repeat and step delay
            repeat = int(settings.get("repeat", 1))
            step_delay = float(settings.get("step_delay", 0.001))
            loop_inf = (repeat == 0)
            loops = 0

            # Create core executor with stop callback and step delay
            self.core_executor = CoreMacroExecutor(stop_callback=lambda: self.stop_flag)
            self.core_executor.step_delay = step_delay

            while (loop_inf or loops < repeat) and not self.stop_flag:
                # Execute macro blocks using core executor
                if not self.core_executor.execute_macro_blocks(macro_blocks):
                    break  # Execution was stopped or failed
                
                if self.stop_flag:
                    break
                loops += 1
                
                # Add step delay between loops
                if step_delay > 0 and not self.stop_flag and (loop_inf or loops < repeat):
                    self._sleep(step_delay)
                    
        finally:
            self.root.after(0, self._finish_execution)

    def _create_flat_list(self, macro_blocks: List[MacroBlock], depth: int = 0) -> List[tuple]:
        """Create a flat list of (block, depth) tuples for highlighting."""
        flat_list = []
        for block in macro_blocks:
            flat_list.append((block, depth))
            if block.macro_blocks:
                flat_list.extend(self._create_flat_list(block.macro_blocks, depth + 1))
        return flat_list

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