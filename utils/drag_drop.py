import tkinter as tk
from typing import Callable, Optional, Tuple, List


class DragDropHandler:
    def __init__(self, listbox, mark_dirty_callback: Optional[Callable[[bool], None]] = None):
        self.listbox = listbox
        self.mark_dirty_callback = mark_dirty_callback
        
        self._drag_start_index = None
        self._drag_preview_index = None
        self._drag_moved = False
        self._drop_preview_insert_at = None
        
        # Insert indicator
        self._insert_bar = tk.Frame(listbox.master, height=2, bd=0, highlightthickness=0)
        self._insert_bar.place_forget()
        self._insert_line_visible = False
        
        self._setup_bindings()

    def _setup_bindings(self):
        self.listbox.bind("<Button-1>", self._on_drag_start, add="+")
        self.listbox.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.listbox.bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        
        self.listbox.bind(
            "<Configure>",
            lambda e: (
                self._show_insert_indicator(self._drag_preview_index)
                if self._insert_line_visible and self._drag_preview_index is not None
                else None
            ),
        )

    def _on_drag_start(self, event):
        lb = self.listbox
        size = lb.size()

        if size == 0:
            try:
                lb.selection_clear(0, tk.END)
            except Exception:
                pass
            self._drag_start_index = None
            self._hide_insert_indicator()
            return "break"

        bbox_last = lb.bbox(size - 1)
        if bbox_last:
            _, y, _, h = bbox_last
            y_bottom = y + h
            if event.y > y_bottom:
                try:
                    lb.selection_clear(0, tk.END)
                except Exception:
                    pass
                self._drag_start_index = None
                self._hide_insert_indicator()
                return "break"

        self._drag_start_index = self._nearest_index(event)
        self._drag_preview_index = None
        self._drag_moved = False
        try:
            lb.selection_clear(0, tk.END)
            lb.selection_set(self._drag_start_index)
            lb.activate(self._drag_start_index)
        except Exception:
            pass
        return "break"

    def _on_drag_motion(self, event):
        if self._drag_start_index is None:
            self._hide_insert_indicator()
            return "break"

        lb = self.listbox
        size = lb.size()
        idx, at_end = self._nearest_index_allow_end(event)

        if not self._drag_moved:
            if at_end or idx != self._drag_start_index:
                self._drag_moved = True

        src = self._drag_start_index
        src_line = lb.get(src)
        src_blk = self._find_block_bounds(src)
        tgt_blk = None if at_end else self._find_block_bounds(idx)

        if at_end:
            preview_insert_at = size
        elif tgt_blk is not None:
            t_start, t_end = tgt_blk
            if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk:
                body_start, body_end = t_start + 1, t_end - 1
                if body_start > body_end:
                    self._hide_insert_indicator()
                    return "break"
                preview_insert_at = max(body_start, min(idx, body_end + 1))
            else:
                preview_insert_at = t_end
        else:
            preview_insert_at = idx

        self._drop_preview_insert_at = preview_insert_at
        self._show_insert_indicator(preview_insert_at)

        try:
            if size > 0:
                lb.see(size - 1 if at_end else idx)
        except Exception:
            pass

        return "break"

    def _on_drag_release(self, event):
        try:
            if self._drag_start_index is None:
                return
            if not self._drag_moved:
                return

            lb = self.listbox
            size = lb.size()
            src = self._drag_start_index
            src_line = lb.get(src)
            src_blk = self._find_block_bounds(src)

            if src_blk is not None and (self._is_header(src_line) or self._is_footer(src_line)):
                s, e = src_blk
                payload = [lb.get(i) for i in range(s, e + 1)]
                payload_is_block = True
                del_start, del_end = s, e
            else:
                payload = [src_line]
                payload_is_block = False
                del_start, del_end = src, src

            width = del_end - del_start + 1

            idx, at_end = self._nearest_index_allow_end(event)
            tgt_blk = None if at_end else self._find_block_bounds(idx)

            if tgt_blk is not None:
                t_start, t_end = tgt_blk

                if payload_is_block and src_blk == tgt_blk:
                    return

                if src_blk is not None and self._is_body(src_line) and tgt_blk == src_blk and not payload_is_block:
                    body_start, body_end = t_start + 1, t_end - 1
                    if body_start > body_end:
                        return
                    insert_at = max(body_start, min(idx, body_end + 1))
                    lb.delete(src)
                    if src < insert_at:
                        insert_at -= 1
                    lb.insert(insert_at, payload[0])
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(insert_at)
                    lb.activate(insert_at)
                    lb.see(insert_at)
                    if self.mark_dirty_callback:
                        self.mark_dirty_callback(True)
                    return

                insert_at = t_end
                if del_start < insert_at:
                    insert_at -= width
                final_lines = self._prepare_lines_for_body(payload)

            else:
                insert_at = self._drop_preview_insert_at if self._drop_preview_insert_at is not None else (
                    size if at_end else idx)
                if insert_at < 0:
                    insert_at = 0
                if insert_at > size:
                    insert_at = size

                if del_start < insert_at:
                    insert_at -= width

                final_lines = self._prepare_lines_for_top(payload, payload_is_block)

            for _ in range(width):
                lb.delete(del_start)

            for i, s in enumerate(final_lines):
                lb.insert(insert_at + i, s)

            lb.selection_clear(0, tk.END)
            lb.selection_set(max(0, min(lb.size() - 1, insert_at)))
            lb.activate(max(0, min(lb.size() - 1, insert_at)))
            lb.see(insert_at)

            if self.mark_dirty_callback:
                self.mark_dirty_callback(True)

        finally:
            self._hide_insert_indicator()
            self._drag_start_index = None
            self._drag_preview_index = None
            self._drop_preview_insert_at = None
            self._drag_moved = False

        return "break"

    def _nearest_index(self, event) -> int:
        idx = self.listbox.nearest(event.y)
        size = self.listbox.size()
        if idx < 0:
            idx = 0
        if idx >= size:
            idx = size - 1 if size > 0 else 0
        return idx

    def _nearest_index_allow_end(self, event) -> Tuple[int, bool]:
        lb = self.listbox
        size = lb.size()
        if size == 0:
            return 0, True
        idx = lb.nearest(event.y)
        try:
            bbox_last = lb.bbox(size - 1)
            if bbox_last:
                _, y, _, h = bbox_last
                if event.y > y + h:
                    return size, True
        except Exception:
            pass
        return idx, False

    def _is_header(self, line: str) -> bool:
        return line.startswith("조건:")

    def _is_footer(self, line: str) -> bool:
        return line.startswith("조건끝")

    def _is_body(self, line: str) -> bool:
        return line.startswith("  ") and not self._is_footer(line) and not self._is_header(line)

    def _find_block_bounds(self, idx: int) -> Optional[Tuple[int, int]]:
        size = self.listbox.size()
        if size == 0 or idx < 0 or idx >= size:
            return None
        line = self.listbox.get(idx)
        if self._is_header(line):
            start = idx
            j = idx + 1
            while j < size and not self._is_footer(self.listbox.get(j)):
                j += 1
            if j < size and self._is_footer(self.listbox.get(j)):
                return (start, j)
            return None
        if self._is_body(line):
            i = idx
            while i >= 0 and not self._is_header(self.listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.listbox.get(i)):
                return self._find_block_bounds(i)
            return None
        if self._is_footer(line):
            i = idx
            while i >= 0 and not self._is_header(self.listbox.get(i)):
                i -= 1
            if i >= 0 and self._is_header(self.listbox.get(i)):
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

    def _hide_insert_indicator(self):
        if self._insert_line_visible:
            try:
                self._insert_bar.place_forget()
            except Exception:
                pass
            self._insert_line_visible = False

    def _show_insert_indicator(self, insert_at: int):
        lb = self.listbox
        size = lb.size()
        if size == 0:
            self._hide_insert_indicator()
            return

        line_index = insert_at - 1
        base_top = False
        if line_index < 0:
            line_index = 0
            base_top = True

        try:
            lb.see(line_index)
            bbox = lb.bbox(line_index)
            if not bbox:
                self._hide_insert_indicator()
                return
            x, y, w, h = bbox
            y_line = y if base_top else (y + h - 1)

            try:
                self._insert_bar.configure(bg="#2a7fff")
            except Exception:
                pass

            self._insert_bar.place(in_=lb, x=0, y=y_line, relwidth=1, height=2)
            self._insert_line_visible = True
        except Exception:
            self._hide_insert_indicator()