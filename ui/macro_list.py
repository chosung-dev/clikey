import tkinter as tk
from typing import Callable, Optional, Tuple, List

from ui.styled_list import StyledList
from utils.inline_edit import InlineEditHandler
from core.macro_block import MacroBlock
from core.event_types import EventType


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

        # Bind click events for selection
        self.macro_listbox.bind('<Button-1>', self._on_click)

    def pack(self, **kwargs):
        self.macro_listbox.pack(**kwargs)

    def insert_macro_block(self, macro_block: MacroBlock):
        """Insert a MacroBlock into the list."""
        sel = self.get_selected_indices()

        if sel:
            selected_idx = sel[0]
            selected_block, selected_depth = self.flat_blocks[selected_idx]
            if selected_block.event_type == EventType.IF:
                selected_block.macro_blocks.append(macro_block)
            else:
                self._insert_after_selected_block(macro_block, selected_idx, selected_block, selected_depth)
        else:
            # No selection, add to end
            self.macro_blocks.append(macro_block)

        self._rebuild_flat_list()
        self._refresh_display()

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
        if selected_depth == 0:
            # Selected block is at root level
            root_idx = self.macro_blocks.index(selected_block)
            self.macro_blocks.insert(root_idx + 1, macro_block)
        else:
            # Selected block is nested, find its parent and insert after the selected block
            parent_block = self._find_parent_block(selected_idx, selected_block)
            if parent_block and hasattr(parent_block, 'macro_blocks'):
                # Find the index of selected_block in parent's macro_blocks
                if selected_block in parent_block.macro_blocks:
                    child_idx = parent_block.macro_blocks.index(selected_block)
                    parent_block.macro_blocks.insert(child_idx + 1, macro_block)
                else:
                    # Fallback: add to end of parent's macro_blocks
                    parent_block.macro_blocks.append(macro_block)
            else:
                # Fallback: add to root level
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