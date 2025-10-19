# core/macro_executor.py
from __future__ import annotations
import time
from typing import List, Optional, Callable

from core.macro_block import MacroBlock
from core.event_types import EventType, ConditionType
from core.mouse import mouse_move_click, mouse_move_only, mouse_down_at_current, mouse_up_at_current
from core.screen import grab_rgb_at
from core.state import GlobalState
from core.image_matcher import ImageMatcher
from core.keyboard_hotkey import normalize_key_for_keyboard
import keyboard


class MacroExecutor:
    def __init__(self, stop_callback: Optional[Callable[[], bool]] = None,
                 highlight_callback: Optional[Callable[[int], None]] = None):
        self.stop_callback = stop_callback
        self.highlight_callback = highlight_callback
        self.step_delay = 0.0
        self.current_block_index = 0

    def should_stop(self) -> bool:
        return self.stop_callback() if self.stop_callback else False

    def execute_macro_blocks(self, macro_blocks: List[MacroBlock], flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        for i, macro_block in enumerate(macro_blocks):
            if self.should_stop():
                return False

            if flat_blocks:
                current_flat_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index)
                if current_flat_index >= 0 and self.highlight_callback:
                    self.highlight_callback(current_flat_index)

            if not self._execute_single_block(macro_block, flat_blocks, base_index):
                return False

            if self.step_delay > 0 and i < len(macro_blocks) - 1 and not self.should_stop():
                time.sleep(self.step_delay)

        return True

    def _execute_single_block(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
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
                return self._execute_condition(macro_block, flat_blocks, base_index)

            elif macro_block.event_type == EventType.EXIT:
                return self._execute_exit(macro_block)

        except Exception:
            return False

        return True

    def _execute_keyboard(self, macro_block: MacroBlock):
        if not macro_block.event_data:
            return

        normalized_key = normalize_key_for_keyboard(macro_block.event_data)
        if not normalized_key:
            return

        action = macro_block.action or "press"
        try:
            if action == "press":
                keyboard.press_and_release(normalized_key)
            elif action == "down":
                keyboard.press(normalized_key)
            elif action == "up":
                keyboard.release(normalized_key)
        except Exception:
            pass

    def _execute_mouse(self, macro_block: MacroBlock):
        button = macro_block.event_data or "left"
        action = macro_block.action or "click"

        if action == "down":
            mouse_down_at_current(button)
        elif action == "up":
            mouse_up_at_current(button)
        else:
            x, y = self._resolve_mouse_position(macro_block)
            if x is None or y is None:
                return

            if action == "click":
                mouse_move_click(x, y, button)
            elif action == "move":
                mouse_move_only(x, y)

    def _execute_delay(self, macro_block: MacroBlock):
        delay_time = float(macro_block.action or 0)
        if delay_time <= 0:
            return

        while delay_time > 0 and not self.should_stop():
            sleep_time = min(delay_time, 0.1)
            time.sleep(sleep_time)
            delay_time -= sleep_time

    def _execute_if(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        condition_met = self._evaluate_condition(macro_block)
        if condition_met:
            return self._execute_nested_blocks(macro_block, flat_blocks, base_index)
        return True

    def _execute_exit(self, macro_block: MacroBlock) -> bool:
        return not bool(macro_block.action)

    def _execute_nested_blocks(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        if not macro_block.macro_blocks:
            return True

        nested_base_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index) + 1 if flat_blocks else 0

        try:
            return self.execute_macro_blocks(macro_block.macro_blocks, flat_blocks, nested_base_index)
        except Exception:
            return True

    def _execute_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        if macro_block.condition_type == ConditionType.IMAGE_MATCH:
            return self._execute_image_match_condition(macro_block, flat_blocks, base_index)
        elif macro_block.condition_type == ConditionType.RGB_MATCH:
            return self._execute_rgb_match_condition(macro_block, flat_blocks, base_index)
        elif macro_block.condition_type == ConditionType.COORDINATE_CONDITION:
            return self._execute_coordinate_condition(macro_block, flat_blocks, base_index)
        else:
            return self._execute_if(macro_block, flat_blocks, base_index)

    def _execute_image_match_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        if not macro_block.action:
            return True

        search_region = self._parse_search_region(macro_block.position)
        result = ImageMatcher.find_image_on_screen(macro_block.action, search_region=search_region)

        if result:
            self._store_image_match_result(macro_block.action, result, macro_block.event_data)
            return self._execute_nested_blocks(macro_block, flat_blocks, base_index)

        return True

    def _parse_search_region(self, position: Optional[str]) -> Optional[tuple[int, int, int, int]]:
        if not position:
            return None

        try:
            parts = position.split(",")
            if len(parts) == 4:
                return tuple(map(int, parts))
        except (ValueError, AttributeError):
            pass

        return None

    def _store_image_match_result(self, template_path: str, result: tuple[int, int], event_data: str):
        context_data = ImageMatcher.create_context_data(template_path, result)

        if not hasattr(GlobalState, 'image_match_results'):
            GlobalState.image_match_results = {}

        if len(GlobalState.image_match_results) > 100:
            oldest_key = next(iter(GlobalState.image_match_results))
            del GlobalState.image_match_results[oldest_key]

        GlobalState.image_match_results[event_data] = context_data

    def _execute_rgb_match_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        if not macro_block.action:
            return True

        try:
            actual_rgb = self._get_rgb_for_condition(macro_block)
            if actual_rgb is None:
                return True

            if self._compare_rgb(macro_block.action, actual_rgb):
                return self._execute_nested_blocks(macro_block, flat_blocks, base_index)

            return True

        except Exception:
            return True

    def _get_rgb_for_condition(self, macro_block: MacroBlock) -> Optional[tuple[int, int, int]]:
        if macro_block.position and macro_block.position.strip() == "@parent":
            if hasattr(GlobalState, 'current_coordinate_rgb') and GlobalState.current_coordinate_rgb:
                return GlobalState.current_coordinate_rgb
            return None

        coords = macro_block.parse_position()
        if not coords:
            return None

        return grab_rgb_at(*coords)

    def _compare_rgb(self, expected: str, actual: tuple[int, int, int]) -> bool:
        if not isinstance(expected, str):
            return False

        parts = expected.split(',')
        if len(parts) != 3:
            return False

        try:
            expected_rgb = tuple(map(int, parts))
            return expected_rgb == actual
        except ValueError:
            return False

    def _execute_coordinate_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        coords = macro_block.parse_position()
        if not coords:
            return True

        try:
            actual_rgb = grab_rgb_at(*coords)
            if actual_rgb is None:
                return True

            GlobalState.current_coordinate_rgb = actual_rgb

            try:
                return self._execute_nested_blocks(macro_block, flat_blocks, base_index)
            finally:
                GlobalState.current_coordinate_rgb = None

        except Exception:
            return True

    def _resolve_mouse_position(self, macro_block: MacroBlock) -> tuple[Optional[int], Optional[int]]:
        if macro_block.position and (macro_block.position.strip() == "@parent" or "." in macro_block.position):
            return self._resolve_position_reference(macro_block.position)

        position = macro_block.parse_position()
        return position if position else (None, None)

    def _resolve_position_reference(self, position_str: str) -> tuple[Optional[int], Optional[int]]:
        try:
            if position_str.strip() == "@parent":
                return self._get_parent_image_coordinates()

            parts = position_str.split(",")
            if len(parts) != 2:
                return None, None

            x = self._resolve_coordinate_part(parts[0].strip(), "x")
            y = self._resolve_coordinate_part(parts[1].strip(), "y")

            return (x, y) if x is not None and y is not None else (None, None)

        except (ValueError, AttributeError):
            return None, None

    def _resolve_coordinate_part(self, part: str, coord_type: str) -> Optional[int]:
        if "." not in part:
            return int(part)

        ref_name, coord = part.split(".", 1)
        if coord != coord_type or not hasattr(GlobalState, 'image_match_results'):
            return None

        return GlobalState.image_match_results[ref_name].get(coord_type) if ref_name in GlobalState.image_match_results else None

    def _get_parent_image_coordinates(self) -> tuple[Optional[int], Optional[int]]:
        if not hasattr(GlobalState, 'image_match_results') or not GlobalState.image_match_results:
            return None, None

        for context_data in reversed(list(GlobalState.image_match_results.values())):
            x, y = context_data.get("x"), context_data.get("y")
            if x is not None and y is not None:
                return x, y

        return None, None

    def _find_block_index_in_flat_list(self, target_block: MacroBlock, flat_blocks: List, base_index: int = 0) -> int:
        for i, (block, depth) in enumerate(flat_blocks):
            if block.key == target_block.key:
                return i
        return -1