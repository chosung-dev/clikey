import tkinter as tk
from typing import Callable, Optional, Tuple, List

from ui.styled_list import StyledList
from utils.inline_edit import InlineEditHandler
from core.macro_block import MacroBlock
from core.event_types import EventType
from core.state import GlobalState


class MacroListManager:
    def __init__(self, parent: tk.Widget, mark_dirty_callback: Optional[Callable[[bool], None]] = None, save_callback: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.mark_dirty_callback = mark_dirty_callback
        self.save_callback = save_callback

        self.container_frame = tk.Frame(parent)

        self.scrollbar = tk.Scrollbar(self.container_frame, orient=tk.VERTICAL, width=10)

        self.macro_listbox = StyledList(
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
            mark_dirty_callback, 
            self._update_block_description
        )
        self.macro_blocks: List[MacroBlock] = []
        self.selected_indices: List[int] = []
        self.flat_blocks: List[Tuple[MacroBlock, int]] = []  # (block, depth) pairs
        self.clipboard: List[MacroBlock] = []  # Clipboard for copy/cut/paste
        self.last_selected_index: Optional[int] = None  # For range selection
        self.range_anchor: Optional[int] = None  # Fixed anchor point for range selection
        
        # Undo functionality - store up to 5 states
        self.undo_history: List[List[MacroBlock]] = []
        self.max_undo_levels = 5

        # Bind click events for selection
        self.macro_listbox.bind('<Button-1>', self._on_click)
        self.macro_listbox.bind('<Shift-Button-1>', self._on_shift_click)
        
        # Bind delete key for deletion
        self.macro_listbox.bind('<Delete>', self._on_delete_key)
        self.macro_listbox.bind('<KeyPress-Delete>', self._on_delete_key)
        
        # Bind copy/cut/paste keys
        self.macro_listbox.bind('<Control-c>', self._on_copy)
        self.macro_listbox.bind('<Control-x>', self._on_cut)
        self.macro_listbox.bind('<Control-v>', self._on_paste)
        
        # Bind undo key
        self.macro_listbox.bind('<Control-z>', self._on_undo)

        # Bind save key
        self.macro_listbox.bind('<Control-s>', self._on_save)

        # Bind select all key
        self.macro_listbox.bind('<Control-a>', self._on_select_all)

        # Bind arrow keys for navigation
        self.macro_listbox.bind('<Up>', self._on_up_arrow)
        self.macro_listbox.bind('<Down>', self._on_down_arrow)
        self.macro_listbox.bind('<Shift-Up>', self._on_shift_up_arrow)
        self.macro_listbox.bind('<Shift-Down>', self._on_shift_down_arrow)

        # Make listbox focusable
        self.macro_listbox.config(takefocus=True)

    def pack(self, **kwargs):
        self.container_frame.pack(**kwargs)

    def insert_macro_block(self, macro_block: MacroBlock):
        """Insert a MacroBlock into the list."""
        self._save_state_for_undo()

        sel = self.get_selected_indices()
        is_image_match_copy = self._is_image_match_block(macro_block)

        if sel:
            selected_idx = sel[0]
            selected_block, selected_depth = self.flat_blocks[selected_idx]
            if selected_block.event_type == EventType.IF:
                self._clear_reference_positions_if_needed(macro_block, selected_block, is_image_match_copy)
                selected_block.macro_blocks.append(macro_block)
            else:
                self._insert_after_selected_block(macro_block, selected_idx, selected_block, selected_depth)
        else:
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.append(macro_block)

        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()
        self._select_newly_added_block(macro_block)

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

    def get_macro_blocks(self) -> List[MacroBlock]:
        """Get all macro blocks."""
        return self.macro_blocks.copy()

    def _is_image_match_block(self, block: MacroBlock) -> bool:
        """Check if block is an image match condition."""
        return (block.event_type == EventType.IF and
                hasattr(block, 'condition_type') and
                block.condition_type and
                block.condition_type.value == 'image_match')

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

        if index != -1:
            self.selected_indices = [index]
            self.last_selected_index = index
            self.range_anchor = index  # Reset anchor on single click
        else:
            self.selected_indices = []
            self.last_selected_index = None
            self.range_anchor = None

        self._update_selection_display()

        # Give focus to listbox for keyboard events
        self.macro_listbox.focus_set()

    def _on_shift_click(self, event):
        """Handle Shift+click for range selection."""
        index = self.macro_listbox.nearest(event.y)

        if index == -1:
            return

        if self.last_selected_index is None:
            # No previous selection, treat as normal click
            self.selected_indices = [index]
            self.last_selected_index = index
        else:
            # Select range from last selected to current
            start = min(self.last_selected_index, index)
            end = max(self.last_selected_index, index)
            self.selected_indices = list(range(start, end + 1))

        self._update_selection_display()

        # Give focus to listbox for keyboard events
        self.macro_listbox.focus_set()

    def _update_selection_display(self):
        """Update the visual display of selected items."""
        if hasattr(self.macro_listbox, 'selection_set_multiple'):
            # Use the new multiple selection method
            self.macro_listbox.selection_set_multiple(self.selected_indices)
        else:
            # Fallback to the old method
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

        # Remember the first selected index for positioning after deletion
        first_selected = min(self.selected_indices)

        # Collect blocks to delete
        blocks_to_delete = []
        for index in self.selected_indices:
            if 0 <= index < len(self.flat_blocks):
                block, _ = self.flat_blocks[index]
                blocks_to_delete.append(block)

        # Remove blocks from their parent containers
        for block in blocks_to_delete:
            self._remove_block_from_tree(block)

        # Clear selection and rebuild
        self.selected_indices.clear()
        self._rebuild_flat_list()
        self._refresh_display()
        self._update_global_state()

        # Set selection to the item at the position where the first deleted item was
        if self.flat_blocks:
            new_index = min(first_selected, len(self.flat_blocks) - 1)
            self.selected_indices = [new_index]
            self.last_selected_index = new_index
            self._update_selection_display()
            self.macro_listbox.see(new_index)

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
        """Insert a macro block after the selected block."""
        is_image_match_copy = self._is_image_match_block(macro_block)

        if selected_depth == 0:
            root_idx = self.macro_blocks.index(selected_block)
            self._clear_reference_positions_if_needed(macro_block, None, is_image_match_copy)
            self.macro_blocks.insert(root_idx + 1, macro_block)
        else:
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
        if self.inline_edit.is_editing():
            return

        if self.get_selected_macro_blocks():
            self.delete_selected()
        return "break"

    def _on_copy(self, event):
        """Handle Ctrl+C to copy selected items."""
        if self.inline_edit.is_editing():
            return

        selected_blocks = self.get_selected_macro_blocks()
        if selected_blocks:
            self.clipboard = [block.copy() for block in selected_blocks]
        return "break"

    def _on_cut(self, event):
        """Handle Ctrl+X to cut selected items."""
        if self.inline_edit.is_editing():
            return

        selected_blocks = self.get_selected_macro_blocks()
        if selected_blocks:
            self._save_state_for_undo()
            self.clipboard = [block.copy() for block in selected_blocks]
            self.delete_selected()
        return "break"

    def _on_paste(self, event):
        """Handle Ctrl+V to paste items from clipboard."""
        if self.inline_edit.is_editing() or not self.clipboard:
            return

        self._save_state_for_undo()
        sel = self.get_selected_indices()

        if sel:
            # Use the first selected index as the base insertion point
            selected_idx = sel[0]
            selected_block, selected_depth = self.flat_blocks[selected_idx]

            # Determine the insertion location
            if selected_block.event_type == EventType.IF:
                # Insert inside the IF block
                parent_block = selected_block
                insert_list = parent_block.macro_blocks
                insert_position = len(insert_list)  # Insert at the end of the IF block
            else:
                # Insert after the selected block
                if selected_depth == 0:
                    # Root level
                    parent_block = None
                    insert_list = self.macro_blocks
                    insert_position = self.macro_blocks.index(selected_block) + 1
                else:
                    # Find parent block
                    parent_block = self._find_parent_block(selected_idx, selected_block)
                    if parent_block and hasattr(parent_block, 'macro_blocks'):
                        insert_list = parent_block.macro_blocks
                        insert_position = parent_block.macro_blocks.index(selected_block) + 1
                    else:
                        # Fallback to root level
                        parent_block = None
                        insert_list = self.macro_blocks
                        insert_position = len(self.macro_blocks)

            for i, block in enumerate(self.clipboard):
                copied_block = block.copy()
                is_image_match_copy = self._is_image_match_block(copied_block)
                self._clear_reference_positions_if_needed(copied_block, parent_block, is_image_match_copy)
                insert_list.insert(insert_position + i, copied_block)

        else:
            for block in self.clipboard:
                copied_block = block.copy()
                is_image_match_copy = self._is_image_match_block(copied_block)
                self._clear_reference_positions_if_needed(copied_block, None, is_image_match_copy)
                self.macro_blocks.append(copied_block)
        
        self._rebuild_flat_list()
        self._refresh_display()

        # Select the newly pasted blocks
        if sel and self.clipboard:
            # Calculate where the pasted blocks should appear in the flat list
            original_selected_idx = sel[0]

            # Rebuild flat list to get updated positions
            if original_selected_idx < len(self.flat_blocks):
                # Try to find the new position of pasted blocks
                # They should be right after the original selected position
                paste_start_idx = original_selected_idx + 1
                paste_end_idx = paste_start_idx + len(self.clipboard) - 1

                # Ensure we don't go beyond the list bounds
                if paste_start_idx < len(self.flat_blocks):
                    paste_end_idx = min(paste_end_idx, len(self.flat_blocks) - 1)
                    self.selected_indices = list(range(paste_start_idx, paste_end_idx + 1))
                    self.last_selected_index = paste_start_idx
                    self._update_selection_display()
                    self.macro_listbox.see(paste_start_idx)
                    self.macro_listbox.focus_set()
        elif self.clipboard:
            # No selection, items were added to the end - select the pasted blocks
            total_blocks = len(self.flat_blocks)
            clipboard_size = len(self.clipboard)
            paste_start_idx = total_blocks - clipboard_size
            paste_end_idx = total_blocks - 1

            if paste_start_idx >= 0:
                self.selected_indices = list(range(paste_start_idx, paste_end_idx + 1))
                self.last_selected_index = paste_start_idx
                self._update_selection_display()
                self.macro_listbox.see(paste_start_idx)
                self.macro_listbox.focus_set()

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

    def _on_save(self, event):
        """Handle Ctrl+S to save file."""
        # Don't save if inline editing is active
        if self.inline_edit.is_editing():
            return

        # Call the save callback if available
        if self.save_callback:
            self.save_callback()

        return "break"

    def _on_select_all(self, event):
        """Handle Ctrl+A to select all blocks."""
        # Don't select all if inline editing is active
        if self.inline_edit.is_editing():
            return

        # Select all blocks if there are any
        if self.flat_blocks:
            self.selected_indices = list(range(len(self.flat_blocks)))
            self.last_selected_index = 0 if self.flat_blocks else None
            self._update_selection_display()
            # Scroll to first item
            if self.selected_indices:
                self.macro_listbox.see(0)

        return "break"

    def _on_up_arrow(self, event):
        """Move selection up."""
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
            self.macro_listbox.see(self.selected_indices[0])
        return "break"

    def _on_down_arrow(self, event):
        """Move selection down."""
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
            self.macro_listbox.see(self.selected_indices[0])
        return "break"

    def _on_shift_up_arrow(self, event):
        """Extend selection upward."""
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
            self.macro_listbox.see(new_active_end)

        return "break"

    def _on_shift_down_arrow(self, event):
        """Extend selection downward."""
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
            self.macro_listbox.see(new_active_end)

        return "break"


    def _clear_reference_positions_if_needed(self, block: MacroBlock, target_parent: MacroBlock = None, is_image_match_block_copy: bool = False):
        """Clear reference positions for mouse blocks when needed."""
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
                self._clear_reference_positions_if_needed(child_block, target_parent, child_is_image_match_copy)

    def _update_global_state(self):
        """Update global state with current macro information."""
        class CurrentMacro:
            def __init__(self, macro_blocks):
                self.macro_blocks = macro_blocks

        GlobalState.current_macro = CurrentMacro(self.macro_blocks)

    def _select_newly_added_block(self, new_block: MacroBlock):
        """Select the newly added block."""
        for i, (block, depth) in enumerate(self.flat_blocks):
            if block is new_block:
                self.selected_indices = [i]
                self.last_selected_index = i
                self._update_selection_display()
                self.macro_listbox.see(i)
                self.macro_listbox.focus_set()
                break