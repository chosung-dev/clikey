# core/macro_executor.py
from __future__ import annotations
import time
from typing import List, Optional, Callable

from core.macro_block import MacroBlock
from core.event_types import EventType, ConditionType
from core.mouse import mouse_move_click, mouse_move_only, mouse_down_at_current, mouse_up_at_current
import keyboard
from core.screen import grab_rgb_at
from core.state import GlobalState
from core.image_matcher import ImageMatcher


class MacroExecutor:
    def __init__(self, stop_callback: Optional[Callable[[], bool]] = None,
                 highlight_callback: Optional[Callable[[int], None]] = None):
        """
        Initialize macro executor.

        Args:
            stop_callback: Function that returns True if execution should stop
            highlight_callback: Function to call when highlighting a block by index
        """
        self.stop_callback = stop_callback
        self.highlight_callback = highlight_callback
        self.step_delay = 0.0  # Delay between macro blocks
        self.current_block_index = 0  # Track current block index for highlighting

    def should_stop(self) -> bool:
        """Check if execution should stop."""
        if self.stop_callback:
            return self.stop_callback()
        return False

    def execute_macro_blocks(self, macro_blocks: List[MacroBlock], flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """
        Execute a list of macro blocks recursively.

        Args:
            macro_blocks: List of macro blocks to execute
            flat_blocks: Flat list of all blocks for highlighting indexing
            base_index: Base index for highlighting in flat list

        Returns:
            True if execution completed successfully, False if stopped
        """
        for i, macro_block in enumerate(macro_blocks):
            if self.should_stop():
                return False

            # Calculate current index in flat list for highlighting
            if flat_blocks:
                current_flat_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index)
                if current_flat_index >= 0 and self.highlight_callback:
                    self.highlight_callback(current_flat_index)

            if not self._execute_single_block(macro_block, flat_blocks, base_index):
                return False

            # Add step delay between blocks (except after the last block)
            if self.step_delay > 0 and i < len(macro_blocks) - 1 and not self.should_stop():
                time.sleep(self.step_delay)

        return True

    def _execute_single_block(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
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
                return self._execute_condition(macro_block, flat_blocks, base_index)

            elif macro_block.event_type == EventType.EXIT:
                return self._execute_exit(macro_block)

        except Exception:
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
            elif action == "down":
                keyboard.press(normalized_key)
            elif action == "up":
                keyboard.release(normalized_key)
        except Exception:
            pass

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
            "Control_L": "ctrl",
            "Control_R": "ctrl",
            "Shift_L": "shift",
            "Shift_R": "shift",
            "Alt_L": "alt",
            "Alt_R": "alt",
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
            # 상위좌표 참조인지 확인
            if macro_block.position and (macro_block.position.strip() == "@parent" or "." in macro_block.position):
                x, y = self._resolve_position_reference(macro_block.position)
                if x is None or y is None:
                    return
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

    def _execute_if(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """Execute conditional block recursively."""
        condition_met = self._evaluate_condition(macro_block)

        if condition_met and macro_block.macro_blocks:
            # Recursively execute the nested macro blocks
            try:
                result = self.execute_macro_blocks(macro_block.macro_blocks, flat_blocks, base_index)
                if not result:
                    return False  # EXIT 블록으로 인한 중지
            except Exception:
                pass

        return True

    def _execute_exit(self, macro_block: MacroBlock) -> bool:
        """Execute exit action."""
        should_exit = bool(macro_block.action)
        if should_exit:
            return False  # Stop execution
        return True


    def _execute_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """Execute conditional block based on condition type."""
        if macro_block.condition_type == ConditionType.IMAGE_MATCH:
            return self._execute_image_match_condition(macro_block, flat_blocks, base_index)
        elif macro_block.condition_type == ConditionType.RGB_MATCH:
            return self._execute_rgb_match_condition(macro_block, flat_blocks, base_index)
        elif macro_block.condition_type == ConditionType.COORDINATE_CONDITION:
            return self._execute_coordinate_condition(macro_block, flat_blocks, base_index)
        else:
            # 기존 IF 조건 (RGB 체크) - 하위 호환성을 위해
            return self._execute_if(macro_block, flat_blocks, base_index)

    def _execute_image_match_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """Execute image match condition."""
        if not macro_block.action:  # action contains the image path
            return True

        template_path = macro_block.action

        # position에서 검색 영역 파싱 (x1,y1,x2,y2 형식)
        search_region = None
        if macro_block.position:
            try:
                parts = macro_block.position.split(",")
                if len(parts) == 4:
                    x1, y1, x2, y2 = map(int, parts)
                    search_region = (x1, y1, x2, y2)
            except (ValueError, AttributeError):
                pass

        result = ImageMatcher.find_image_on_screen(template_path, search_region=search_region)

        if result:
            # 이미지를 찾은 경우, 좌표 정보를 전역 상태에 저장
            context_data = ImageMatcher.create_context_data(template_path, result)

            if not hasattr(GlobalState, 'image_match_results'):
                GlobalState.image_match_results = {}

            # 메모리 누수 방지: 딕셔너리 크기 제한 (최대 100개 항목 유지)
            if len(GlobalState.image_match_results) > 100:
                # 오래된 항목부터 삭제 (FIFO 방식)
                oldest_key = next(iter(GlobalState.image_match_results))
                del GlobalState.image_match_results[oldest_key]

            GlobalState.image_match_results[macro_block.event_data] = context_data

            if macro_block.macro_blocks:
                if flat_blocks:
                    nested_base_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index) + 1
                else:
                    nested_base_index = 0

                # 중첩된 블록들 실행
                try:
                    result = self.execute_macro_blocks(macro_block.macro_blocks, flat_blocks, nested_base_index)
                    if not result:
                        return False  # EXIT 블록으로 인한 중지
                except Exception:
                    pass

            return True
        else:
            # 이미지를 찾지 못해도 다음 블록들은 계속 실행
            return True

    def _execute_rgb_match_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """Execute RGB match condition."""
        if not macro_block.action:
            return True

        expected_rgb = macro_block.action

        try:
            # 상위 좌표 참조인지 확인
            if macro_block.position and macro_block.position.strip() == "@parent":
                # 상위 좌표 조건에서 캐시된 RGB 값 사용
                if hasattr(GlobalState, 'current_coordinate_rgb') and GlobalState.current_coordinate_rgb:
                    actual_rgb = GlobalState.current_coordinate_rgb
                else:
                    return True  # 상위 좌표 RGB가 없으면 조건 건너뛰기
            else:
                # 일반적인 좌표에서 RGB 값 추출
                coords = macro_block.parse_position()
                if not coords:
                    return True
                x, y = coords
                actual_rgb = grab_rgb_at(x, y)
                if actual_rgb is None:
                    return True

            # RGB 값 비교
            if isinstance(expected_rgb, str):
                # "r,g,b" 형식의 문자열 파싱
                expected_parts = expected_rgb.split(',')
                if len(expected_parts) == 3:
                    expected_r, expected_g, expected_b = map(int, expected_parts)
                    actual_r, actual_g, actual_b = actual_rgb

                    # RGB 값이 일치하는지 확인
                    if (expected_r == actual_r and
                        expected_g == actual_g and
                        expected_b == actual_b):

                        # 조건이 맞으면 중첩된 블록들 실행
                        if macro_block.macro_blocks:
                            if flat_blocks:
                                nested_base_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index) + 1
                            else:
                                nested_base_index = 0

                            # 조건 내부 블록 실행
                            try:
                                result = self.execute_macro_blocks(macro_block.macro_blocks, flat_blocks, nested_base_index)
                                if not result:
                                    return False  # EXIT 블록으로 인한 중지
                            except Exception:
                                pass

                        return True

            # 조건이 맞지 않아도 다음 블록들은 계속 실행
            return True

        except Exception:
            return True

    def _execute_coordinate_condition(self, macro_block: MacroBlock, flat_blocks: Optional[List] = None, base_index: int = 0) -> bool:
        """Execute coordinate condition - captures RGB at coordinates and stores for child conditions."""
        if not macro_block.position:
            return True

        # 좌표 파싱
        coords = macro_block.parse_position()
        if not coords:
            return True

        x, y = coords

        try:
            # 지정된 좌표에서 RGB 값 추출
            actual_rgb = grab_rgb_at(x, y)
            if actual_rgb is None:
                return True

            # RGB 값을 글로벌 상태에 저장 (하위 색상 조건들이 참조할 수 있도록)
            GlobalState.current_coordinate_rgb = actual_rgb

            # 하위 조건 블록들 실행
            if macro_block.macro_blocks:
                if flat_blocks:
                    nested_base_index = self._find_block_index_in_flat_list(macro_block, flat_blocks, base_index) + 1
                else:
                    nested_base_index = 0

                # 하위 조건 블록들 실행
                try:
                    result = self.execute_macro_blocks(macro_block.macro_blocks, flat_blocks, nested_base_index)
                    if not result:
                        # RGB 캐시 정리
                        GlobalState.current_coordinate_rgb = None
                        return False  # EXIT 블록으로 인한 중지
                except Exception:
                    pass

            # RGB 캐시 정리
            GlobalState.current_coordinate_rgb = None

            return True

        except Exception:
            return True

    def _resolve_position_reference(self, position_str: str) -> tuple[Optional[int], Optional[int]]:
        """상위좌표 참조를 해결하여 실제 좌표를 반환"""
        try:
            # 새로운 형식: @parent
            if position_str.strip() == "@parent":
                return self._get_parent_image_coordinates()

            # 기존 형식: "image_name.x, image_name.y"
            parts = position_str.split(",")
            if len(parts) != 2:
                return None, None

            x_ref = parts[0].strip()  # "image_name.x"
            y_ref = parts[1].strip()  # "image_name.y"

            # x 좌표 해결
            if "." in x_ref:
                ref_name, coord = x_ref.split(".", 1)
                if coord == "x" and hasattr(GlobalState, 'image_match_results'):
                    if ref_name in GlobalState.image_match_results:
                        x = GlobalState.image_match_results[ref_name]["x"]
                    else:
                        return None, None
                else:
                    return None, None
            else:
                x = int(x_ref)

            # y 좌표 해결
            if "." in y_ref:
                ref_name, coord = y_ref.split(".", 1)
                if coord == "y" and hasattr(GlobalState, 'image_match_results'):
                    if ref_name in GlobalState.image_match_results:
                        y = GlobalState.image_match_results[ref_name]["y"]
                    else:
                        return None, None
                else:
                    return None, None
            else:
                y = int(y_ref)

            return x, y

        except (ValueError, AttributeError):
            return None, None

    def _get_parent_image_coordinates(self) -> tuple[Optional[int], Optional[int]]:
        """현재 실행 중인 부모 이미지 매치 조건의 좌표를 반환"""
        # 현재 실행 중인 이미지 매치 결과에서 가장 최근의 좌표를 사용
        if hasattr(GlobalState, 'image_match_results') and GlobalState.image_match_results:
            # 가장 최근에 매치된 이미지의 좌표를 사용
            for image_name, context_data in reversed(list(GlobalState.image_match_results.items())):
                if "x" in context_data and "y" in context_data:
                    return context_data["x"], context_data["y"]

        return None, None

    def _find_block_index_in_flat_list(self, target_block: MacroBlock, flat_blocks: List, base_index: int = 0) -> int:
        """Find the index of a block in the flat list using block key for identification."""
        for i, (block, depth) in enumerate(flat_blocks):
            if block.key == target_block.key:
                return i
        return -1