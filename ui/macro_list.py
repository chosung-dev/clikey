import tkinter as tk
from typing import Callable, Optional, Tuple, List

from ui.styled_list import StyledList
from utils.inline_edit import InlineEditHandler
from core.macro_block import MacroBlock
from core.event_types import EventType
from core.state import GlobalState


class MacroListManager:
    def __init__(self, parent: tk.Widget, mark_dirty_callback: Optional[Callable[[bool], None]] = None):
        self.parent = parent
        self.mark_dirty_callback = mark_dirty_callback

        self.macro_listbox = StyledList(
            parent,
            split_cb=self._split_raw_desc,
            join_cb=self._join_raw_desc,
            desc_color="#1a7f37",
        )

        self.inline_edit = InlineEditHandler(
            self.macro_listbox, 
            mark_dirty_callback, 
            self._update_block_description
        )
        self.macro_blocks: List[MacroBlock] = []
        self.selected_indices: List[int] = []
        self.flat_blocks: List[Tuple[MacroBlock, int]] = []  # (block, depth) pairs
        self.clipboard: List[MacroBlock] = []  # Clipboard for copy/cut/paste
        
        # Undo functionality - store up to 5 states
        self.undo_history: List[List[MacroBlock]] = []
        self.max_undo_levels = 5

        # Bind click events for selection
        self.macro_listbox.bind('<Button-1>', self._on_click)
        
        # Bind delete key for deletion
        self.macro_listbox.bind('<Delete>', self._on_delete_key)
        self.macro_listbox.bind('<KeyPress-Delete>', self._on_delete_key)
        
        # Bind copy/cut/paste keys
        self.macro_listbox.bind('<Control-c>', self._on_copy)
        self.macro_listbox.bind('<Control-x>', self._on_cut)
        self.macro_listbox.bind('<Control-v>', self._on_paste)
        
        # Bind undo key
        self.macro_listbox.bind('<Control-z>', self._on_undo)
        
        # Make listbox focusable
        self.macro_listbox.config(takefocus=True)

    def pack(self, **kwargs):
        self.macro_listbox.pack(**kwargs)

    def insert_macro_block(self, macro_block: MacroBlock):
        """Insert a MacroBlock into the list."""
        # Save state for undo before making changes
        self._save_state_for_undo()
        
        sel = self.get_selected_indices()

        if sel:
            selected_idx = sel[0]
            selected_block, selected_depth = self.flat_blocks[selected_idx]
            if selected_block.event_type == EventType.IF:
                # 조건 내부에 추가: 이미지 매치 조건이 아니면 상위좌표 참조 정리
                is_image_match_copy = (macro_block.event_type == EventType.IF and
                                     hasattr(macro_block, 'condition_type') and
                                     macro_block.condition_type and
                                     macro_block.condition_type.value == 'image_match')
                self._clear_reference_positions_if_needed(macro_block, selected_block, is_image_match_copy)
                selected_block.macro_blocks.append(macro_block)
            else:
                self._insert_after_selected_block(macro_block, selected_idx, selected_block, selected_depth)
        else:
            # No selection, add to end: 루트 레벨이므로 상위좌표 참조 정리
            is_image_match_copy = (macro_block.event_type == EventType.IF and
                                 hasattr(macro_block, 'condition_type') and
                                 macro_block.condition_type and
                                 macro_block.condition_type.value == 'image_match')
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.append(macro_block)

        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

    def get_macro_blocks(self) -> List[MacroBlock]:
        """Get all macro blocks."""
        return self.macro_blocks.copy()

    def clear(self):
        self.macro_listbox.delete(0, tk.END)
        self.macro_blocks.clear()

    def size(self) -> int:
        return self.macro_listbox.size()

    def load_macro_blocks(self, macro_blocks: List[MacroBlock]):
        """Load macro blocks into the list."""
        self.macro_blocks = macro_blocks.copy()
        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

    def _split_raw_desc(self, s: str) -> Tuple[str, str]:
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw

    def _on_click(self, event):
        index = self.macro_listbox.nearest(event.y)

        self.selected_indices = [] if index == -1 else [index]
        self._update_selection_display()
        
        # Give focus to listbox for keyboard events
        self.macro_listbox.focus_set()

    def _update_selection_display(self):
        """Update the visual display of selected items."""
        self.macro_listbox.selection_clear(0, tk.END)
        for index in self.selected_indices:
            self.macro_listbox.selection_set(index)

    def get_selected_indices(self) -> List[int]:
        """Get the indices of selected macro blocks."""
        return self.selected_indices.copy()

    def get_selected_macro_blocks(self) -> List[MacroBlock]:
        """Get the selected macro blocks."""
        result = []
        for index in self.selected_indices:
            if 0 <= index < len(self.flat_blocks):
                block, _ = self.flat_blocks[index]
                result.append(block)
        return result

    def delete_selected(self):
        """Delete the selected macro blocks."""
        if not self.selected_indices:
            return

        # Save state for undo before making changes
        self._save_state_for_undo()

        # Collect blocks to delete
        blocks_to_delete = []
        for index in self.selected_indices:
            if 0 <= index < len(self.flat_blocks):
                block, _ = self.flat_blocks[index]
                blocks_to_delete.append(block)

        # Remove blocks from their parent containers
        for block in blocks_to_delete:
            self._remove_block_from_tree(block)

        self.selected_indices.clear()
        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

    def _rebuild_flat_list(self):
        """Rebuild the flat list from the hierarchical structure."""
        self.flat_blocks.clear()
        self._flatten_blocks(self.macro_blocks, 0)

    def _flatten_blocks(self, blocks: List[MacroBlock], depth: int):
        """Recursively flatten the block hierarchy."""
        for block in blocks:
            self.flat_blocks.append((block, depth))
            if block.macro_blocks:
                self._flatten_blocks(block.macro_blocks, depth + 1)

    def _refresh_display(self):
        """Refresh the listbox display with indented text."""
        self.macro_listbox.delete(0, tk.END)

        for block, depth in self.flat_blocks:
            indent = "    " * depth  # 4 spaces per depth level
            display_text = indent + block.get_display_text()
            if block.description:
                display_text = self._join_raw_desc(display_text, block.description)
            self.macro_listbox.insert(tk.END, display_text)

    def _find_root_block(self, flat_index: int) -> MacroBlock:
        """Find the root block for a given flat index."""
        if flat_index < len(self.flat_blocks):
            block, depth = self.flat_blocks[flat_index]

            # If it's already at depth 0, it's a root block
            if depth == 0:
                return block

            # Search backwards for the parent root block
            for i in range(flat_index - 1, -1, -1):
                parent_block, parent_depth = self.flat_blocks[i]
                if parent_depth == 0:
                    return parent_block

        # Fallback to first root block
        return self.macro_blocks[0] if self.macro_blocks else None

    def _remove_block_from_tree(self, target_block: MacroBlock):
        """Remove a block from the tree structure."""
        # Try to remove from root level
        if target_block in self.macro_blocks:
            self.macro_blocks.remove(target_block)
            return

        # Recursively search in nested blocks
        self._remove_from_nested_blocks(self.macro_blocks, target_block)

    def _remove_from_nested_blocks(self, blocks: List[MacroBlock], target_block: MacroBlock) -> bool:
        """Recursively remove a block from nested structures."""
        for block in blocks:
            if target_block in block.macro_blocks:
                block.macro_blocks.remove(target_block)
                return True
            if self._remove_from_nested_blocks(block.macro_blocks, target_block):
                return True
        return False

    def get_raw_items(self) -> List[str]:
        """Get raw text items for backward compatibility."""
        items = []
        for block, depth in self.flat_blocks:
            indent = "    " * depth
            display_text = indent + block.get_display_text()
            if block.description:
                display_text = self._join_raw_desc(display_text, block.description)
            items.append(display_text)
        return items

    def _insert_after_selected_block(self, macro_block: MacroBlock, selected_idx: int, selected_block: MacroBlock, selected_depth: int):
        """Insert a macro block after the selected block at the correct position."""
        # 이미지 매치 조건 블록인지 확인
        is_image_match_copy = (macro_block.event_type == EventType.IF and
                             hasattr(macro_block, 'condition_type') and
                             macro_block.condition_type and
                             macro_block.condition_type.value == 'image_match')

        if selected_depth == 0:
            # Selected block is at root level: 루트 레벨이므로 상위좌표 참조 정리
            root_idx = self.macro_blocks.index(selected_block)
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.insert(root_idx + 1, macro_block)

        else:
            # Selected block is nested, find its parent and insert after the selected block
            parent_block = self._find_parent_block(selected_idx, selected_block)
            if parent_block and hasattr(parent_block, 'macro_blocks'):
                # Find the index of selected_block in parent's macro_blocks
                if selected_block in parent_block.macro_blocks:
                    child_idx = parent_block.macro_blocks.index(selected_block)
                    # 부모가 이미지 매치 조건이 아니면 상위좌표 참조 정리
                    self._clear_reference_positions_if_needed(macro_block, parent_block, is_image_match_copy)
                    parent_block.macro_blocks.insert(child_idx + 1, macro_block)
                else:
                    # Fallback: add to end of parent's macro_blocks
                    self._clear_reference_positions_if_needed(macro_block, parent_block, is_image_match_copy)
                    parent_block.macro_blocks.append(macro_block)

            else:
                # Fallback: add to root level: 루트 레벨이므로 상위좌표 참조 정리
                self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
                self.macro_blocks.append(macro_block)


    def _find_parent_block(self, selected_idx: int, selected_block: MacroBlock) -> Optional[MacroBlock]:
        """Find the parent block of the selected block."""
        if selected_idx <= 0:
            return None

        selected_depth = self.flat_blocks[selected_idx][1]

        # Search backwards for a block with depth one level up
        for i in range(selected_idx - 1, -1, -1):
            block, depth = self.flat_blocks[i]
            if depth == selected_depth - 1:
                return block

        return None

    def _update_block_description(self, flat_index: int, new_description: str):
        """Update the description of a MacroBlock based on flat list index."""
        if 0 <= flat_index < len(self.flat_blocks):
            block, _ = self.flat_blocks[flat_index]
            block.description = new_description

    def _on_delete_key(self, event):
        """Handle delete key press to delete selected items."""
        # Don't delete if inline editing is active
        if self.inline_edit.is_editing():
            return
            
        selected_blocks = self.get_selected_macro_blocks()
        if not selected_blocks:
            return
            
        # Delete the selected items
        self.delete_selected()
        self.macro_listbox.selection_clear(0, tk.END)

        return "break"

    def _on_copy(self, event):
        """Handle Ctrl+C to copy selected items."""
        # Don't copy if inline editing is active
        if self.inline_edit.is_editing():
            return
            
        selected_blocks = self.get_selected_macro_blocks()
        if not selected_blocks:
            return
            
        # Copy selected blocks to clipboard
        self.clipboard = [block.copy() for block in selected_blocks]
        return "break"

    def _on_cut(self, event):
        """Handle Ctrl+X to cut selected items."""
        # Don't cut if inline editing is active
        if self.inline_edit.is_editing():
            return
            
        selected_blocks = self.get_selected_macro_blocks()
        if not selected_blocks:
            return
            
        # Save state for undo before making changes
        self._save_state_for_undo()
            
        # Copy to clipboard first
        self.clipboard = [block.copy() for block in selected_blocks]
        
        # Then delete the selected items
        self.delete_selected()
        self.macro_listbox.selection_clear(0, tk.END)
        
        # Mark as dirty
        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)
            
        return "break"

    def _on_paste(self, event):
        """Handle Ctrl+V to paste items from clipboard."""
        # Don't paste if inline editing is active
        if self.inline_edit.is_editing():
            return
            
        if not self.clipboard:
            return
            
        # Save state for undo before making changes
        self._save_state_for_undo()
            
        # Get insertion point
        sel = self.get_selected_indices()
        
        # Insert copies of clipboard items
        for i, block in enumerate(self.clipboard):
            copied_block = block.copy()

            # 이미지 매치 조건 블록인지 확인
            is_image_match_copy = (copied_block.event_type == EventType.IF and
                                 hasattr(copied_block, 'condition_type') and
                                 copied_block.condition_type and
                                 copied_block.condition_type.value == 'image_match')

            if sel:
                selected_idx = sel[0] + i
                if selected_idx < len(self.flat_blocks):
                    selected_block, selected_depth = self.flat_blocks[selected_idx]
                    if selected_block.event_type == EventType.IF:
                        # 조건 내부에 추가: 이미지 매치 조건이 아니면 상위좌표 참조 정리
                        self._clear_reference_positions_if_needed(copied_block, selected_block, is_image_match_copy)
                        selected_block.macro_blocks.append(copied_block)
                    else:
                        self._insert_after_selected_block(copied_block, selected_idx, selected_block, selected_depth)
                else:
                    # Insert at end if beyond current range: 루트 레벨이므로 상위좌표 참조 정리
                    self._clear_reference_positions_if_needed(copied_block, None, is_image_match_copy)
                    self.macro_blocks.append(copied_block)
            else:
                # No selection, add to end: 루트 레벨이므로 상위좌표 참조 정리
                self._clear_reference_positions_if_needed(copied_block, None, is_image_match_copy)
                self.macro_blocks.append(copied_block)
        
        self._rebuild_flat_list()
        self._refresh_display()
        
        # Mark as dirty
        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)
            
        return "break"

    def _save_state_for_undo(self):
        """Save current state to undo history."""
        # Deep copy the current macro blocks state
        current_state = [block.copy() for block in self.macro_blocks]
        
        # Add to history
        self.undo_history.append(current_state)
        
        # Keep only the last max_undo_levels states
        if len(self.undo_history) > self.max_undo_levels:
            self.undo_history.pop(0)

    def _on_undo(self, event):
        """Handle Ctrl+Z to undo last action."""
        # Don't undo if inline editing is active
        if self.inline_edit.is_editing():
            return
            
        if not self.undo_history:
            return  # No states to undo
            
        # Restore the last saved state
        last_state = self.undo_history.pop()
        self.macro_blocks = last_state
        
        # Rebuild and refresh display
        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

        # Clear selection
        self.selected_indices.clear()
        self.macro_listbox.selection_clear(0, tk.END)

        # Mark as dirty
        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)
            
        return "break"


    def _clear_reference_positions_if_needed(self, block: MacroBlock, target_parent: MacroBlock = None, is_image_match_block_copy: bool = False):
        """Clear reference positions for mouse blocks if they are not inside an image match condition."""
        # 이미지 매치 조건 블록 자체를 복사하는 경우, 내부 참조는 그대로 유지
        if is_image_match_block_copy:
            return

        # 현재 블록이 마우스 블록이고 상위좌표 참조를 가지고 있는지 확인
        if (block.event_type == EventType.MOUSE and
            hasattr(block, 'clear_reference_position') and
            block.has_reference_position()):

            # 대상 부모가 이미지 매치 조건이 아니면 참조를 0,0으로 변경
            if not (target_parent and
                   target_parent.event_type == EventType.IF and
                   hasattr(target_parent, 'condition_type') and
                   target_parent.condition_type and
                   target_parent.condition_type.value == 'image_match'):
                block.clear_reference_position()

        # 중첩된 블록들도 재귀적으로 처리
        if hasattr(block, 'macro_blocks') and block.macro_blocks:
            for child_block in block.macro_blocks:
                # 현재 블록이 이미지 매치 조건이면 하위 블록들의 참조는 유지
                child_is_image_match_copy = (block.event_type == EventType.IF and
                                           hasattr(block, 'condition_type') and
                                           block.condition_type and
                                           block.condition_type.value == 'image_match')

                self._clear_reference_positions_if_needed(child_block, target_parent, child_is_image_match_copy)




    def _update_global_state(self):
        """Update global state with current macro information."""
        # 현재 매크로 정보를 객체로 만들어 GlobalState에 저장
        class CurrentMacro:
            def __init__(self, macro_blocks):
                self.macro_blocks = macro_blocks

        GlobalState.current_macro = CurrentMacro(self.macro_blocks)