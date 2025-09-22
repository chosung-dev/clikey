# core/macro_executor.py
from __future__ import annotations
import time
from typing import List, Optional, Callable

from core.macro_block import MacroBlock
from core.event_types import EventType
from core.mouse import mouse_move_click, mouse_move_only, mouse_down_at_current, mouse_up_at_current
import keyboard
from core.screen import grab_rgb_at


class MacroExecutor:
    def __init__(self, stop_callback: Optional[Callable[[], bool]] = None):
        """
        Initialize macro executor.

        Args:
            stop_callback: Function that returns True if execution should stop
        """
        self.stop_callback = stop_callback
        self.step_delay = 0.0  # Delay between macro blocks

    def should_stop(self) -> bool:
        """Check if execution should stop."""
        if self.stop_callback:
            return self.stop_callback()
        return False

    def execute_macro_blocks(self, macro_blocks: List[MacroBlock]) -> bool:
        """
        Execute a list of macro blocks recursively.

        Returns:
            True if execution completed successfully, False if stopped
        """
        for i, macro_block in enumerate(macro_blocks):
            if self.should_stop():
                return False

            if not self._execute_single_block(macro_block):
                return False

            # Add step delay between blocks (except after the last block)
            if self.step_delay > 0 and i < len(macro_blocks) - 1 and not self.should_stop():
                time.sleep(self.step_delay)

        return True

    def _execute_single_block(self, macro_block: MacroBlock) -> bool:
        """Execute a single macro block."""
        if self.should_stop():
            return False

        try:
            if macro_block.event_type == EventType.KEYBOARD:
                self._execute_keyboard(macro_block)

            elif macro_block.event_type == EventType.MOUSE:
                self._execute_mouse(macro_block)

            elif macro_block.event_type == EventType.DELAY:
                self._execute_delay(macro_block)

            elif macro_block.event_type == EventType.IF:
                return self._execute_if(macro_block)

            elif macro_block.event_type == EventType.EXIT:
                return self._execute_exit(macro_block)

        except Exception as e:
            print(f"Error executing macro block: {e}")
            return False

        return True

    def _execute_keyboard(self, macro_block: MacroBlock):
        """Execute keyboard action."""
        if not macro_block.event_data:
            return
            
        key = macro_block.event_data
        action = macro_block.action or "press"

        normalized_key = self._normalize_key_for_keyboard_library(key)

        try:
            if action == "press":
                keyboard.press_and_release(normalized_key)
            else:
                print(f"지원하지 않는 키보드 액션: {action}")
        except Exception as e:
            print(f"키보드 실행 실패 '{action}' for key '{key}' (normalized: '{normalized_key}'): {e}")

    def _normalize_key_for_keyboard_library(self, key: str) -> str:
        """Normalize key name for keyboard library."""
        if not key:
            return key
            
        # Single character keys - keep as lowercase
        if len(key) == 1:
            return key.lower()
            
        # Special key mappings from Tkinter/X11 to keyboard library
        key_mapping = {
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
        
        # Function keys (F1-F12)
        if key.startswith("F") and key[1:].isdigit():
            return key.lower()
            
        # Use mapping if available, otherwise return lowercase
        return key_mapping.get(key, key.lower())

    def _execute_mouse(self, macro_block: MacroBlock):
        """Execute mouse action."""
        button = macro_block.event_data or "left"
        action = macro_block.action or "click"

        if action == "down":
            mouse_down_at_current(button)
        elif action == "up":
            mouse_up_at_current(button)
        else:
            position = macro_block.parse_position()
            if not position:
                return
            x, y = position
            if action == "click":
                mouse_move_click(x, y, button)
            elif action == "move":
                mouse_move_only(x, y)

    def _execute_delay(self, macro_block: MacroBlock):
        """Execute delay action."""
        delay_time = float(macro_block.action or 0)
        if delay_time > 0:
            # Split delay into smaller chunks to check for stop condition
            while delay_time > 0 and not self.should_stop():
                sleep_time = min(delay_time, 0.1)
                time.sleep(sleep_time)
                delay_time -= sleep_time

    def _execute_if(self, macro_block: MacroBlock) -> bool:
        """Execute conditional block recursively."""
        condition_met = self._evaluate_condition(macro_block)

        if condition_met and macro_block.macro_blocks:
            # Recursively execute the nested macro blocks
            return self.execute_macro_blocks(macro_block.macro_blocks)

        return True

    def _execute_exit(self, macro_block: MacroBlock) -> bool:
        """Execute exit action."""
        should_exit = bool(macro_block.action)
        if should_exit:
            return False  # Stop execution
        return True

    def _evaluate_condition(self, macro_block: MacroBlock) -> bool:
        """Evaluate the condition for an IF block."""
        condition_type = macro_block.event_data
        position = macro_block.parse_position()

        if condition_type == "color_match":
            if not position:
                return False

            x, y = position
            rgb = grab_rgb_at(x, y)
            if not rgb:
                return False

            # Parse expected color from action field
            try:
                expected_colors = macro_block.action.split(",")
                if len(expected_colors) >= 3:
                    expected_r = int(expected_colors[0].strip())
                    expected_g = int(expected_colors[1].strip())
                    expected_b = int(expected_colors[2].strip())

                    # Allow some tolerance in color matching
                    tolerance = 10
                    return (abs(rgb[0] - expected_r) <= tolerance and
                            abs(rgb[1] - expected_g) <= tolerance and
                            abs(rgb[2] - expected_b) <= tolerance)
            except (ValueError, AttributeError):
                pass

        return False