import tkinter as tk
from typing import Callable, Optional, Tuple


class InlineEditHandler:
    def __init__(self, listbox, mark_dirty_callback: Optional[Callable[[bool], None]] = None, 
                 update_block_callback: Optional[Callable[[int, str], None]] = None):
        self.listbox = listbox
        self.mark_dirty_callback = mark_dirty_callback
        self.update_block_callback = update_block_callback
        
        self._inline_edit_entry = None
        self._inline_edit_idx = None
        self._inline_edit_raw = None
        
        self._setup_bindings()

    def _setup_bindings(self):
        self.listbox.bind("<Double-Button-1>", self._begin_desc_inline_edit, add="+")

    def _begin_desc_inline_edit(self, event):
        if self._inline_edit_entry is not None:
            return "break"

        lb = self.listbox
        idx = lb.nearest(event.y)
        size = lb.size()
        if size == 0 or idx < 0 or idx >= size:
            return "break"
        bbox = lb.bbox(idx)
        if not bbox:
            return "break"
        bbox_last = lb.bbox(size - 1)
        if bbox_last:
            _, y, _, h = bbox_last
            if event.y > y + h:
                return "break"
        x, y, w, h = bbox

        line = lb.get(idx)
        raw, cur_desc = self._split_raw_desc(line)

        self._inline_edit_idx = idx
        self._inline_edit_raw = raw

        ent = tk.Entry(lb)
        ent.insert(0, cur_desc)
        ent.place(x=0, y=max(0, y - 2), width=max(w + 16, lb.winfo_width() - 8), height=h + 6)
        ent.focus_set()
        self._inline_edit_entry = ent

        ent.bind("<Return>", self._inline_edit_commit)
        ent.bind("<Escape>", lambda e: (self._inline_edit_cleanup(), "break"))
        ent.bind("<FocusOut>", self._inline_edit_commit)

        return "break"

    def _inline_edit_cleanup(self):
        ent = self._inline_edit_entry
        if ent is not None:
            try:
                ent.place_forget()
                ent.destroy()
            except Exception:
                pass
        self._inline_edit_entry = None
        self._inline_edit_idx = None
        self._inline_edit_raw = None

    def _inline_edit_commit(self, *_):
        if self._inline_edit_entry is None or self._inline_edit_idx is None:
            return
        lb = self.listbox
        idx = self._inline_edit_idx
        raw = self._inline_edit_raw
        new_desc = self._inline_edit_entry.get().strip()
        try:
            lb.delete(idx)
            lb.insert(idx, self._join_raw_desc(raw, new_desc))
            
            # Update the actual MacroBlock object
            if self.update_block_callback:
                self.update_block_callback(idx, new_desc)
            
            if self.mark_dirty_callback:
                self.mark_dirty_callback(True)
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.activate(idx)
            lb.see(idx)
        finally:
            self._inline_edit_cleanup()
        return "break"

    def commit_if_editing(self):
        if self._inline_edit_entry is not None:
            self._inline_edit_commit()

    def is_editing(self) -> bool:
        return self._inline_edit_entry is not None

    def _split_raw_desc(self, s: str) -> Tuple[str, str]:
        if " - " in s:
            raw, desc = s.rsplit(" - ", 1)
            return raw.rstrip("\n"), desc.strip()
        return s.rstrip("\n"), ""

    def _join_raw_desc(self, raw: str, desc: str) -> str:
        raw = (raw or "").rstrip("\n")
        desc = (desc or "").strip()
        return f"{raw} - {desc}" if desc else raw