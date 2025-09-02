import tkinter as tk
from typing import Callable, Optional, Tuple, List

from ui.styled_list import StyledList
from utils.drag_drop import DragDropHandler
from utils.inline_edit import InlineEditHandler


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
        
        self.drag_drop = DragDropHandler(self.macro_listbox, mark_dirty_callback)
        self.inline_edit = InlineEditHandler(self.macro_listbox, mark_dirty_callback)
        
        self._clipboard = []
        self._clipboard_is_block = False
        
        self._setup_keyboard_bindings()

    def _setup_keyboard_bindings(self):
        root = self.parent.winfo_toplevel()
        root.bind("<Control-c>", self._on_copy)
        root.bind("<Control-x>", self._on_cut)
        root.bind("<Control-v>", self._on_paste)
        root.bind("<Delete>", self._on_delete)
        root.bind("<Escape>", lambda e: self.macro_listbox.selection_clear(0, tk.END))

    def pack(self, **kwargs):
        self.macro_listbox.pack(**kwargs)

    def insert_smart(self, line: str):
        lb = self.macro_listbox
        size = lb.size()
        sel = lb.curselection()

        if size == 0:
            lb.insert(tk.END, line)
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)
            lb.activate(0)
            lb.see(0)
            if self.mark_dirty_callback:
                self.mark_dirty_callback(True)
            return

        idx = sel[0] if sel else (size - 1)
        line_at_idx = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is not None:
            start, end = blk

            is_footer_selected = self._is_footer(line_at_idx)
            is_no_selection = not sel
            is_block_at_bottom = (end == size - 1)

            if is_block_at_bottom and (is_no_selection or is_footer_selected):
                insert_at = size
                line = self._ensure_body_indent(line, going_into_block=False)
            else:
                if self._is_body(line_at_idx):
                    insert_at = min(idx + 1, end)
                else:
                    insert_at = end
                line = self._ensure_body_indent(line, going_into_block=True)

        else:
            insert_at = (idx + 1) if sel else size
            line = self._ensure_body_indent(line, going_into_block=False)

        lb.insert(insert_at, line)
        lb.selection_clear(0, tk.END)
        lb.selection_set(insert_at)
        lb.activate(insert_at)
        lb.see(insert_at)

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

    def get_raw_items(self) -> List[str]:
        items_only_raw = []
        for i in range(self.macro_listbox.size()):
            raw, _ = self._split_raw_desc(self.macro_listbox.get(i))
            items_only_raw.append(raw)
        return items_only_raw

    def get_descriptions(self) -> List[str]:
        descs = []
        for i in range(self.macro_listbox.size()):
            _, desc = self._split_raw_desc(self.macro_listbox.get(i))
            descs.append(desc)
        return descs

    def clear(self):
        self.macro_listbox.delete(0, tk.END)

    def size(self) -> int:
        return self.macro_listbox.size()

    def load_items(self, items: List[str], descriptions: List[str]):
        self.macro_listbox.delete(0, tk.END)
        
        if len(descriptions) != len(items):
            if len(descriptions) < len(items):
                descriptions = descriptions + [""] * (len(items) - len(descriptions))
            else:
                descriptions = descriptions[:len(items)]

        for raw, d in zip(items, descriptions):
            display = self._join_raw_desc(raw, d)
            self.macro_listbox.insert(tk.END, display)

    def _on_copy(self, event=None):
        lb = self.macro_listbox
        sel = lb.curselection()
        if not sel:
            return "break"

        idx = sel[0]
        line = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is not None and (self._is_header(line) or self._is_footer(line)):
            s, e = blk
            self._clipboard = [lb.get(i) for i in range(s, e + 1)]
            self._clipboard_is_block = True
            return "break"

        self._clipboard = [line]
        self._clipboard_is_block = False
        return "break"

    def _on_cut(self, event=None):
        self._on_copy()
        self._on_delete()
        return "break"

    def _on_paste(self, event=None):
        lb = self.macro_listbox
        size = lb.size()

        if not self._clipboard:
            self.parent.winfo_toplevel().bell()
            return "break"

        sel = lb.curselection()
        cur_idx = sel[0] if sel else (size if size > 0 else 0)

        cur_block = self._find_block_bounds(cur_idx)

        if cur_block is not None:
            start, end = cur_block
            insert_at = end
            payload = self._prepare_lines_for_body(self._clipboard)
            if not payload:
                return "break"
            for i, s in enumerate(payload):
                lb.insert(insert_at + i, s)
            lb.selection_clear(0, tk.END)
            lb.selection_set(insert_at)
            lb.activate(insert_at)
            lb.see(insert_at)
        else:
            insert_at = cur_idx + 1 if (size > 0 and cur_idx < size) else size
            payload = self._prepare_lines_for_top(self._clipboard, self._clipboard_is_block)
            if not payload:
                return "break"
            for i, s in enumerate(payload):
                lb.insert(insert_at + i, s)
            lb.selection_clear(0, tk.END)
            lb.selection_set(insert_at)
            lb.activate(insert_at)
            lb.see(insert_at)

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

        return "break"

    def _on_delete(self, event=None):
        lb = self.macro_listbox
        sel = lb.curselection()
        if not sel:
            return "break"

        idx = sel[0]
        line = lb.get(idx)
        blk = self._find_block_bounds(idx)

        if blk is None:
            lb.delete(idx)
            size = lb.size()
            if idx >= size:
                idx = size - 1
            if idx >= 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
                lb.see(idx)
            if self.mark_dirty_callback:
                self.mark_dirty_callback(True)
            return "break"

        start, end = blk
        if self._is_header(line) or self._is_footer(line):
            width = end - start + 1
            for _ in range(width):
                lb.delete(start)
            size = lb.size()
            new_idx = min(start, size - 1)
            if new_idx >= 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(new_idx)
                lb.activate(new_idx)
                lb.see(new_idx)
        else:
            lb.delete(idx)
            size = lb.size()
            new_idx = idx
            if new_idx >= size:
                new_idx = size - 1
            lb.selection_clear(0, tk.END)
            if new_idx >= 0:
                lb.selection_set(new_idx)
                lb.activate(new_idx)
                lb.see(new_idx)

        if self.mark_dirty_callback:
            self.mark_dirty_callback(True)

        return "break"

    def _is_header(self, line: str) -> bool:
        return line.startswith("조건:")

    def _is_footer(self, line: str) -> bool:
        return line.startswith("조건끝")

    def _is_body(self, line: str) -> bool:
        return line.startswith("  ") and not self._is_footer(line) and not self._is_header(line)

    def _find_block_bounds(self, idx: int) -> Optional[Tuple[int, int]]:
        size = self.macro_listbox.size()
        if size == 0 or idx < 0 or idx >= size:
            return None
        line = self.macro_listbox.get(idx)
        if self._is_header(line):
            start = idx
            j = idx + 1
            while j < size and not self._is_footer(self.macro_listbox.get(j)):
                j += 1
            if j < size and self._is_footer(self.macro_listbox.get(j)):
                return (start, j)
            return None
        if self._is_body(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return self._find_block_bounds(i)
            return None
        if self._is_footer(line):
            i = idx
            while i >= 0 and not self._is_header(self.macro_listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.macro_listbox.get(i)):
                return (i, idx)
            return None
        return None

    def _prepare_lines_for_body(self, lines: List[str]) -> List[str]:
        out = []
        for s in lines:
            if self._is_header(s) or self._is_footer(s):
                continue
            if s.startswith("  "):
                out.append(s)
            else:
                out.append("  " + s)
        return out

    def _prepare_lines_for_top(self, lines: List[str], clipboard_is_block: bool) -> List[str]:
        if clipboard_is_block:
            return list(lines)
        out = []
        for s in lines:
            if self._is_header(s) or self._is_footer(s):
                out.append(s)
            elif s.startswith("  "):
                out.append(s[2:])
            else:
                out.append(s)
        return out

    def _ensure_body_indent(self, s: str, going_into_block: bool) -> str:
        if going_into_block and not s.startswith("  ") and not self._is_header(s) and not self._is_footer(s):
            return "  " + s
        return s

    def _split_raw_desc(self, s: str) -> Tuple[str, str]:
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw