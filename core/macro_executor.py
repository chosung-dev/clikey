# core/macro_executor.py
from __future__ import annotations
import time
from typing import List, Optional, Callable

from core.macro_block import MacroBlock
from core.event_types import EventType
from core.mouse import mouse_move_click, mouse_move_only, mouse_down_at_current, mouse_up_at_current
from core.screen import grab_rgb_at


class MacroExecutor:
    def __init__(self, stop_callback: Optional[Callable[[], bool]] = None):
        """
        Initialize macro executor.

        Args:
            stop_callback: Function that returns True if execution should stop
        """
        self.stop_callback = stop_callback

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
        for macro_block in macro_blocks:
            if self.should_stop():
                return False

            if not self._execute_single_block(macro_block):
                return False

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
        # TODO: Implement keyboard actions when keyboard library is available
        print(f"Keyboard: {macro_block.event_data} ({macro_block.action})")

    def _execute_mouse(self, macro_block: MacroBlock):
        """Execute mouse action."""
        position = macro_block.parse_position()
        if not position:
            return

        x, y = position
        button = macro_block.event_data or "left"
        action = macro_block.action or "click"

        if action == "click":
            mouse_move_click(x, y, button)
        elif action == "move":
            mouse_move_only(x, y)
        elif action == "down":
            mouse_move_only(x, y)
            mouse_down_at_current(button)
        elif action == "up":
            mouse_up_at_current(button)

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

        if condition_type == "image_match":
            # TODO: Implement image matching
            print(f"Image match condition at {position} (not implemented)")
            return False

        elif condition_type == "color_match":
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