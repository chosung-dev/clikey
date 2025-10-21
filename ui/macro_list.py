import tkinter as tk
from typing import Callable, Optional, Tuple, List

from ui.macro_tree_view import MacroTreeView
from utils.inline_edit import InlineEditHandler
from core.macro_block import MacroBlock
from core.event_types import EventType
from core.state import GlobalState


class MacroListManager:
    """매크로 블록 리스트 관리 및 UI 제어를 담당하는 클래스."""

    # 상수
    MAX_UNDO_LEVELS = 5
    INDENT_SPACES = 4

    def __init__(
        self,
        parent: tk.Widget,
        mark_dirty_callback: Optional[Callable[[bool], None]] = None,
        save_callback: Optional[Callable[[], None]] = None
    ):
        self.parent = parent
        self.mark_dirty_callback = mark_dirty_callback
        self.save_callback = save_callback
        self.edit_mode_callback = None

        # UI 컴포넌트 초기화
        self._init_ui_components()

        # 데이터 구조 초기화
        self._init_data_structures()

        # 이벤트 바인딩
        self._bind_events()

    def _init_ui_components(self):
        """UI 컴포넌트 초기화."""
        self.container_frame = tk.Frame(self.parent)
        self.scrollbar = tk.Scrollbar(self.container_frame, orient=tk.VERTICAL, width=10)

        self.macro_listbox = MacroTreeView(
            self.container_frame,
            split_cb=self._split_raw_desc,
            join_cb=self._join_raw_desc,
            desc_color="#1a7f37",
            yscrollcommand=self.scrollbar.set
        )

        self.scrollbar.config(command=self.macro_listbox.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.macro_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inline_edit = InlineEditHandler(
            self.macro_listbox,
            self.mark_dirty_callback,
            self._update_block_description
        )

        self.macro_listbox.config(takefocus=True)

    def _init_data_structures(self):
        """데이터 구조 초기화."""
        self.macro_blocks: List[MacroBlock] = []
        self.selected_indices: List[int] = []
        self.flat_blocks: List[Tuple[MacroBlock, int]] = []
        self.clipboard: List[MacroBlock] = []
        self.last_selected_index: Optional[int] = None
        self.range_anchor: Optional[int] = None
        self.undo_history: List[List[MacroBlock]] = []

    def _bind_events(self):
        """키보드 및 마우스 이벤트 바인딩."""
        bindings = {
            '<Button-1>': self._on_click,
            '<Shift-Button-1>': self._on_shift_click,
            '<Delete>': self._on_delete_key,
            '<KeyPress-Delete>': self._on_delete_key,
            '<Control-c>': self._on_copy,
            '<Control-x>': self._on_cut,
            '<Control-v>': self._on_paste,
            '<Control-z>': self._on_undo,
            '<Control-s>': self._on_save,
            '<Control-a>': self._on_select_all,
            '<Double-Button-1>': self._on_double_click,
            '<Up>': self._on_up_arrow,
            '<Down>': self._on_down_arrow,
            '<Shift-Up>': self._on_shift_up_arrow,
            '<Shift-Down>': self._on_shift_down_arrow,
            '<Shift-Tab>': self._on_move_outside,
        }

        for event, handler in bindings.items():
            self.macro_listbox.bind(event, handler)

    def pack(self, **kwargs):
        """컨테이너 프레임 pack."""
        self.container_frame.pack(**kwargs)

    # ========== 블록 관리 메서드 ==========

    def insert_macro_block(self, macro_block: MacroBlock):
        """매크로 블록 삽입."""
        self._save_state_for_undo()

        sel = self.get_selected_indices()
        is_image_match_copy = self._is_image_match_block(macro_block)

        if sel:
            self._insert_at_selection(macro_block, sel[0], is_image_match_copy)
        else:
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.append(macro_block)

        self._rebuild_and_refresh()
        self._select_newly_added_block(macro_block)
        self._mark_dirty()

    def _insert_at_selection(self, macro_block: MacroBlock, selected_idx: int, is_image_match_copy: bool):
        """선택된 위치에 블록 삽입."""
        selected_block, selected_depth = self.flat_blocks[selected_idx]

        if selected_block.event_type == EventType.IF:
            self._clear_reference_positions_if_needed(macro_block, selected_block, is_image_match_copy)
            selected_block.macro_blocks.insert(0, macro_block)
        else:
            self._insert_after_selected_block(macro_block, selected_idx, selected_block, selected_depth)

    def delete_selected(self):
        """선택된 매크로 블록 삭제."""
        self.selected_indices = self.macro_listbox.get_selected_indices()

        if not self.selected_indices:
            return

        self._save_state_for_undo()
        first_selected = min(self.selected_indices)

        # 삭제할 블록 수집
        blocks_to_delete = [
            self.flat_blocks[idx][0]
            for idx in self.selected_indices
            if 0 <= idx < len(self.flat_blocks)
        ]

        # 블록 제거
        for block in blocks_to_delete:
            self._remove_block_from_tree(block)

        self.selected_indices.clear()
        self._rebuild_and_refresh()

        # 삭제 후 선택 위치 조정
        if self.flat_blocks:
            self._select_after_deletion(first_selected)

        self._mark_dirty()

    def _select_after_deletion(self, original_index: int):
        """삭제 후 적절한 위치 선택."""
        new_index = min(original_index, len(self.flat_blocks) - 1)
        self.selected_indices = [new_index]
        self.last_selected_index = new_index
        self._update_selection_display()
        self._scroll_to_index(new_index)

    def clear(self):
        """모든 매크로 블록 제거."""
        self.macro_listbox.clear_all()
        self.macro_blocks.clear()
        self.flat_blocks.clear()
        self.selected_indices.clear()
        self.last_selected_index = -1

    def load_macro_blocks(self, macro_blocks: List[MacroBlock]):
        """매크로 블록 로드."""
        self.macro_blocks = macro_blocks.copy()
        self.selected_indices.clear()
        self.last_selected_index = -1
        self._rebuild_and_refresh()

    # ========== 조회 메서드 ==========

    def get_macro_blocks(self) -> List[MacroBlock]:
        """모든 매크로 블록 반환."""
        return self.macro_blocks.copy()

    def get_selected_indices(self) -> List[int]:
        """선택된 인덱스 반환."""
        indices = self.macro_listbox.get_selected_indices()
        self.selected_indices = indices
        return indices.copy()

    def get_selected_macro_blocks(self) -> List[MacroBlock]:
        """선택된 매크로 블록 반환."""
        return self.macro_listbox.get_selected_blocks()

    def size(self) -> int:
        """전체 블록 수 반환."""
        return self.macro_listbox.size()

    def get_raw_items(self) -> List[str]:
        """인덴트가 포함된 텍스트 리스트 반환 (하위 호환성)."""
        items = []
        for block, depth in self.flat_blocks:
            indent = " " * (self.INDENT_SPACES * depth)
            display_text = indent + block.get_display_text()
            if block.description:
                display_text = self._join_raw_desc(display_text, block.description)
            items.append(display_text)
        return items

    # ========== 내부 헬퍼 메서드 ==========

    def _rebuild_and_refresh(self):
        """flat_blocks 재구성 및 화면 갱신."""
        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

    def _rebuild_flat_list(self):
        """계층 구조를 평면 리스트로 변환."""
        self.flat_blocks.clear()
        self._flatten_blocks(self.macro_blocks, 0)

    def _flatten_blocks(self, blocks: List[MacroBlock], depth: int):
        """재귀적으로 블록 평면화."""
        for block in blocks:
            self.flat_blocks.append((block, depth))
            if block.macro_blocks:
                self._flatten_blocks(block.macro_blocks, depth + 1)

    def _refresh_display(self):
        """Treeview 디스플레이 갱신."""
        self.macro_listbox.clear_all()
        self.macro_listbox.load_blocks(self.macro_blocks)

    def _update_selection_display(self):
        """선택 상태 화면 업데이트."""
        if self.selected_indices:
            self.macro_listbox.selection_set_multiple(self.selected_indices)

    def _scroll_to_index(self, index: int):
        """특정 인덱스로 스크롤."""
        all_items = self.macro_listbox._get_all_items_flat()
        if 0 <= index < len(all_items):
            self.macro_listbox.see(all_items[index])

    def _mark_dirty(self):
        """변경 사항 표시."""
        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

    # ========== 블록 트리 조작 메서드 ==========

    def _insert_after_selected_block(
        self,
        macro_block: MacroBlock,
        selected_idx: int,
        selected_block: MacroBlock,
        selected_depth: int
    ):
        """선택된 블록 다음에 삽입."""
        is_image_match_copy = self._is_image_match_block(macro_block)

        if selected_depth == 0:
            # 루트 레벨
            root_idx = self.macro_blocks.index(selected_block)
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.insert(root_idx + 1, macro_block)
        else:
            # 중첩 레벨
            parent_block = self._find_parent_block(selected_idx, selected_block)
            if parent_block and hasattr(parent_block, 'macro_blocks'):
                if selected_block in parent_block.macro_blocks:
                    child_idx = parent_block.macro_blocks.index(selected_block)
                    self._clear_reference_positions_if_needed(macro_block, parent_block, is_image_match_copy)
                    parent_block.macro_blocks.insert(child_idx + 1, macro_block)
                else:
                    self._clear_reference_positions_if_needed(macro_block, parent_block, is_image_match_copy)
                    parent_block.macro_blocks.append(macro_block)
            else:
                self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
                self.macro_blocks.append(macro_block)

    def _find_parent_block(self, selected_idx: int, selected_block: MacroBlock) -> Optional[MacroBlock]:
        """선택된 블록의 부모 찾기."""
        if selected_idx <= 0:
            return None

        selected_depth = self.flat_blocks[selected_idx][1]

        for i in range(selected_idx - 1, -1, -1):
            block, depth = self.flat_blocks[i]
            if depth == selected_depth - 1:
                return block

        return None

    def _remove_block_from_tree(self, target_block: MacroBlock):
        """트리 구조에서 블록 제거."""
        if target_block in self.macro_blocks:
            self.macro_blocks.remove(target_block)
            return

        self._remove_from_nested_blocks(self.macro_blocks, target_block)

    def _remove_from_nested_blocks(self, blocks: List[MacroBlock], target_block: MacroBlock) -> bool:
        """중첩 구조에서 재귀적으로 블록 제거."""
        for block in blocks:
            if target_block in block.macro_blocks:
                block.macro_blocks.remove(target_block)
                return True
            if self._remove_from_nested_blocks(block.macro_blocks, target_block):
                return True
        return False

    def move_selected_blocks_outside(self):
        """선택된 블록을 상위 레벨로 이동."""
        if not self.selected_indices:
            return

        self._save_state_for_undo()

        blocks_to_move = self._collect_movable_blocks()

        if not blocks_to_move:
            return

        for block, parent_block, depth in blocks_to_move:
            self._move_block_outside(block, parent_block, depth)

        self._rebuild_and_refresh()

        if blocks_to_move:
            self._select_newly_added_block(blocks_to_move[0][0])

        self._mark_dirty()

    def _collect_movable_blocks(self) -> List[Tuple[MacroBlock, MacroBlock, int]]:
        """이동 가능한 블록 수집."""
        blocks_to_move = []

        for idx in sorted(self.selected_indices, reverse=True):
            if idx >= len(self.flat_blocks):
                continue

            block, depth = self.flat_blocks[idx]

            if depth == 0:
                continue

            parent_block = self._find_parent_block(idx, block)
            if parent_block:
                blocks_to_move.append((block, parent_block, depth))

        return blocks_to_move

    def _move_block_outside(self, block: MacroBlock, parent_block: MacroBlock, depth: int):
        """블록을 상위 레벨로 이동."""
        if block in parent_block.macro_blocks:
            parent_block.macro_blocks.remove(block)

        if depth == 1:
            # 최상위 레벨로 이동
            parent_root_idx = self._find_root_index(parent_block)
            if parent_root_idx is not None:
                self.macro_blocks.insert(parent_root_idx + 1, block)
        else:
            # 조부모 레벨로 이동
            grandparent_block = self._find_grandparent_block(parent_block)
            if grandparent_block and hasattr(grandparent_block, 'macro_blocks'):
                try:
                    parent_idx = grandparent_block.macro_blocks.index(parent_block)
                    grandparent_block.macro_blocks.insert(parent_idx + 1, block)
                except ValueError:
                    grandparent_block.macro_blocks.append(block)

    def _find_grandparent_block(self, parent_block: MacroBlock) -> Optional[MacroBlock]:
        """조부모 블록 찾기."""
        for root_block in self.macro_blocks:
            if root_block is parent_block:
                return None

            if hasattr(root_block, 'macro_blocks'):
                if parent_block in root_block.macro_blocks:
                    return root_block

                grandparent = self._find_grandparent_recursive(parent_block, root_block)
                if grandparent:
                    return grandparent

        return None

    def _find_grandparent_recursive(
        self,
        target_parent: MacroBlock,
        current: MacroBlock
    ) -> Optional[MacroBlock]:
        """재귀적으로 조부모 찾기."""
        if not hasattr(current, 'macro_blocks'):
            return None

        for child in current.macro_blocks:
            if child is target_parent:
                return current

            if hasattr(child, 'macro_blocks'):
                result = self._find_grandparent_recursive(target_parent, child)
                if result:
                    return result

        return None

    def _find_root_index(self, target_block: MacroBlock) -> Optional[int]:
        """루트 레벨에서 블록 인덱스 찾기."""
        for i, block in enumerate(self.macro_blocks):
            if block is target_block:
                return i
            if hasattr(block, 'macro_blocks') and block.macro_blocks:
                if self._is_block_in_children(target_block, block):
                    return i
        return None

    def _is_block_in_children(self, target_block: MacroBlock, parent: MacroBlock) -> bool:
        """블록이 자식 중에 있는지 확인."""
        if not hasattr(parent, 'macro_blocks'):
            return False

        for child in parent.macro_blocks:
            if child is target_block:
                return True
            if hasattr(child, 'macro_blocks') and self._is_block_in_children(target_block, child):
                return True
        return False

    # ========== 이미지 매치 및 참조 위치 처리 ==========

    def _is_image_match_block(self, block: MacroBlock) -> bool:
        """이미지 매치 조건 블록인지 확인."""
        return (
            block.event_type == EventType.IF and
            hasattr(block, 'condition_type') and
            block.condition_type and
            block.condition_type.value == 'image_match'
        )

    def _clear_reference_positions_if_needed(
        self,
        block: MacroBlock,
        target_parent: Optional[MacroBlock] = None,
        is_image_match_block_copy: bool = False
    ):
        """필요한 경우 참조 위치 제거."""
        if is_image_match_block_copy:
            return

        if (block.event_type == EventType.MOUSE and
            hasattr(block, 'clear_reference_position') and
            block.has_reference_position()):

            if not (target_parent and
                   target_parent.event_type == EventType.IF and
                   hasattr(target_parent, 'condition_type') and
                   target_parent.condition_type and
                   target_parent.condition_type.value == 'image_match'):
                block.clear_reference_position()

        if hasattr(block, 'macro_blocks') and block.macro_blocks:
            for child_block in block.macro_blocks:
                child_is_image_match_copy = self._is_image_match_block(block)
                self._clear_reference_positions_if_needed(
                    child_block,
                    target_parent,
                    child_is_image_match_copy
                )

    # ========== 이벤트 핸들러 ==========

    def _on_click(self, event):
        """클릭 이벤트 - Treeview 기본 처리 후 동기화."""
        self.macro_listbox.after_idle(self._sync_selection_after_click)

    def _on_shift_click(self, event):
        """Shift+클릭 이벤트 - Treeview 기본 처리 후 동기화."""
        self.macro_listbox.after_idle(self._sync_selection_after_click)

    def _sync_selection_after_click(self):
        """Treeview 선택 상태 동기화."""
        self.selected_indices = self.macro_listbox.get_selected_indices()
        if self.selected_indices:
            self.last_selected_index = self.selected_indices[0]
            self.range_anchor = self.selected_indices[0]
        else:
            self.last_selected_index = None
            self.range_anchor = None
        self.macro_listbox.focus_set()

    def _on_delete_key(self, event):
        """Delete 키 이벤트."""
        if self.inline_edit.is_editing():
            return

        if self.get_selected_macro_blocks():
            self.delete_selected()
        return "break"

    def _on_copy(self, event):
        """Ctrl+C 이벤트 - 복사."""
        if self.inline_edit.is_editing():
            return

        selected_blocks = self.get_selected_macro_blocks()
        if selected_blocks:
            self.clipboard = [block.copy() for block in selected_blocks]
        return "break"

    def _on_cut(self, event):
        """Ctrl+X 이벤트 - 잘라내기."""
        if self.inline_edit.is_editing():
            return

        selected_blocks = self.get_selected_macro_blocks()
        if selected_blocks:
            self._save_state_for_undo()
            self.clipboard = [block.copy() for block in selected_blocks]
            self.delete_selected()
        return "break"

    def _on_paste(self, event):
        """Ctrl+V 이벤트 - 붙여넣기."""
        if self.inline_edit.is_editing() or not self.clipboard:
            return

        self._save_state_for_undo()
        sel = self.get_selected_indices()

        if sel:
            self._paste_at_selection(sel[0])
        else:
            self._paste_at_end()

        self._rebuild_and_refresh()
        self._select_pasted_blocks(sel)
        self._mark_dirty()

        return "break"

    def _paste_at_selection(self, selected_idx: int):
        """선택된 위치에 붙여넣기."""
        selected_block, selected_depth = self.flat_blocks[selected_idx]

        if selected_block.event_type == EventType.IF:
            parent_block = selected_block
            insert_list = parent_block.macro_blocks
            insert_position = 0
        else:
            if selected_depth == 0:
                parent_block = None
                insert_list = self.macro_blocks
                insert_position = self.macro_blocks.index(selected_block) + 1
            else:
                parent_block = self._find_parent_block(selected_idx, selected_block)
                if parent_block and hasattr(parent_block, 'macro_blocks'):
                    insert_list = parent_block.macro_blocks
                    insert_position = parent_block.macro_blocks.index(selected_block) + 1
                else:
                    parent_block = None
                    insert_list = self.macro_blocks
                    insert_position = len(self.macro_blocks)

        for i, block in enumerate(self.clipboard):
            copied_block = block.copy()
            is_image_match_copy = self._is_image_match_block(copied_block)
            self._clear_reference_positions_if_needed(copied_block, parent_block, is_image_match_copy)
            insert_list.insert(insert_position + i, copied_block)

    def _paste_at_end(self):
        """맨 끝에 붙여넣기."""
        for block in self.clipboard:
            copied_block = block.copy()
            is_image_match_copy = self._is_image_match_block(copied_block)
            self._clear_reference_positions_if_needed(copied_block, None, is_image_match_copy)
            self.macro_blocks.append(copied_block)

    def _select_pasted_blocks(self, original_selection: Optional[List[int]]):
        """붙여넣은 블록 선택."""
        if original_selection and self.clipboard:
            original_selected_idx = original_selection[0]

            if original_selected_idx < len(self.flat_blocks):
                paste_start_idx = original_selected_idx + 1
                paste_end_idx = paste_start_idx + len(self.clipboard) - 1

                if paste_start_idx < len(self.flat_blocks):
                    paste_end_idx = min(paste_end_idx, len(self.flat_blocks) - 1)
                    self.selected_indices = list(range(paste_start_idx, paste_end_idx + 1))
                    self.last_selected_index = paste_start_idx
                    self._update_selection_display()
                    self._scroll_to_index(paste_start_idx)
                    self.macro_listbox.focus_set()
        elif self.clipboard:
            total_blocks = len(self.flat_blocks)
            clipboard_size = len(self.clipboard)
            paste_start_idx = total_blocks - clipboard_size
            paste_end_idx = total_blocks - 1

            if paste_start_idx >= 0:
                self.selected_indices = list(range(paste_start_idx, paste_end_idx + 1))
                self.last_selected_index = paste_start_idx
                self._update_selection_display()
                self._scroll_to_index(paste_start_idx)
                self.macro_listbox.focus_set()

    def _on_undo(self, event):
        """Ctrl+Z 이벤트 - 실행 취소."""
        if self.inline_edit.is_editing() or not self.undo_history:
            return

        last_state = self.undo_history.pop()
        self.macro_blocks = last_state

        self._rebuild_and_refresh()

        self.selected_indices.clear()
        self.macro_listbox.selection_remove(*self.macro_listbox.selection())

        self._mark_dirty()

        return "break"

    def _on_save(self, event):
        """Ctrl+S 이벤트 - 저장."""
        if self.inline_edit.is_editing():
            return

        if self.save_callback:
            self.save_callback()

        return "break"

    def _on_select_all(self, event):
        """Ctrl+A 이벤트 - 전체 선택."""
        if self.inline_edit.is_editing():
            return

        if self.flat_blocks:
            self.selected_indices = list(range(len(self.flat_blocks)))
            self.last_selected_index = 0 if self.flat_blocks else None
            self._update_selection_display()
            self._scroll_to_index(0)

        return "break"

    def _on_double_click(self, event):
        """더블클릭 이벤트 - 편집."""
        if self.inline_edit.is_editing():
            return

        index = self.macro_listbox.nearest(event.y)
        if 0 <= index < len(self.flat_blocks):
            block, depth = self.flat_blocks[index]

            if self.edit_mode_callback:
                self.edit_mode_callback(block, index)

        return "break"

    def _on_move_outside(self, event):
        """Shift+Tab 이벤트 - 블록 밖으로 이동."""
        self.move_selected_blocks_outside()
        return "break"

    # ========== 화살표 키 네비게이션 ==========

    def _on_up_arrow(self, event):
        """위 화살표 키."""
        if self.inline_edit.is_editing():
            return

        if not self.selected_indices:
            if self.flat_blocks:
                self.selected_indices = [len(self.flat_blocks) - 1]
                self.last_selected_index = len(self.flat_blocks) - 1
        else:
            current_idx = self.selected_indices[0]
            if current_idx > 0:
                self.selected_indices = [current_idx - 1]
                self.last_selected_index = current_idx - 1
                self.range_anchor = current_idx - 1

        self._update_selection_display()
        if self.selected_indices:
            self._scroll_to_index(self.selected_indices[0])
        return "break"

    def _on_down_arrow(self, event):
        """아래 화살표 키."""
        if self.inline_edit.is_editing():
            return

        if not self.selected_indices:
            if self.flat_blocks:
                self.selected_indices = [0]
                self.last_selected_index = 0
        else:
            current_idx = self.selected_indices[0]
            if current_idx < len(self.flat_blocks) - 1:
                self.selected_indices = [current_idx + 1]
                self.last_selected_index = current_idx + 1
                self.range_anchor = current_idx + 1

        self._update_selection_display()
        if self.selected_indices:
            self._scroll_to_index(self.selected_indices[0])
        return "break"

    def _on_shift_up_arrow(self, event):
        """Shift+위 화살표 키 - 범위 선택 확장 (위로)."""
        if self.inline_edit.is_editing() or not self.selected_indices:
            return

        if self.range_anchor is None:
            self.range_anchor = self.selected_indices[0]

        min_selected = min(self.selected_indices)
        max_selected = max(self.selected_indices)

        active_end = max_selected if self.range_anchor == min_selected else min_selected
        new_active_end = active_end - 1

        if new_active_end >= 0:
            start = min(self.range_anchor, new_active_end)
            end = max(self.range_anchor, new_active_end)
            self.selected_indices = list(range(start, end + 1))
            self.last_selected_index = new_active_end
            self._update_selection_display()
            self._scroll_to_index(new_active_end)

        return "break"

    def _on_shift_down_arrow(self, event):
        """Shift+아래 화살표 키 - 범위 선택 확장 (아래로)."""
        if self.inline_edit.is_editing() or not self.selected_indices:
            return

        if self.range_anchor is None:
            self.range_anchor = self.selected_indices[0]

        min_selected = min(self.selected_indices)
        max_selected = max(self.selected_indices)

        active_end = max_selected if self.range_anchor == min_selected else min_selected
        new_active_end = active_end + 1

        if new_active_end < len(self.flat_blocks):
            start = min(self.range_anchor, new_active_end)
            end = max(self.range_anchor, new_active_end)
            self.selected_indices = list(range(start, end + 1))
            self.last_selected_index = new_active_end
            self._update_selection_display()
            self._scroll_to_index(new_active_end)

        return "break"

    # ========== 실행 취소 및 기타 ==========

    def _save_state_for_undo(self):
        """실행 취소를 위한 상태 저장."""
        current_state = [block.copy() for block in self.macro_blocks]
        self.undo_history.append(current_state)

        if len(self.undo_history) > self.MAX_UNDO_LEVELS:
            self.undo_history.pop(0)

    def _update_block_description(self, flat_index: int, new_description: str):
        """블록 설명 업데이트."""
        if 0 <= flat_index < len(self.flat_blocks):
            block, _ = self.flat_blocks[flat_index]
            block.description = new_description

    def _update_global_state(self):
        """전역 상태 업데이트."""
        class CurrentMacro:
            def __init__(self, macro_blocks):
                self.macro_blocks = macro_blocks

        GlobalState.current_macro = CurrentMacro(self.macro_blocks)

    def _select_newly_added_block(self, new_block: MacroBlock):
        """새로 추가된 블록 선택."""
        self.macro_listbox.select_block(new_block)
        self.selected_indices = self.macro_listbox.get_selected_indices()
        if self.selected_indices:
            self.last_selected_index = self.selected_indices[0]
        self.macro_listbox.focus_set()

    def _replace_block(self, old_block: MacroBlock, new_block: MacroBlock, block_index: int):
        """블록 교체."""
        self._save_state_for_undo()

        if block_index < len(self.flat_blocks):
            flat_block, depth = self.flat_blocks[block_index]

            if depth == 0:
                for i, root_block in enumerate(self.macro_blocks):
                    if root_block is old_block:
                        self.macro_blocks[i] = new_block
                        break
            else:
                parent_block = self._find_parent_block(block_index, flat_block)
                if parent_block and hasattr(parent_block, 'macro_blocks'):
                    for i, child_block in enumerate(parent_block.macro_blocks):
                        if child_block is old_block:
                            parent_block.macro_blocks[i] = new_block
                            break

        self._rebuild_and_refresh()
        self._select_newly_added_block(new_block)
        self._mark_dirty()

    # ========== 유틸리티 메서드 ==========

    def _split_raw_desc(self, s: str) -> Tuple[str, str]:
        """텍스트에서 내용과 설명 분리."""
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        """내용과 설명 결합."""
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw
