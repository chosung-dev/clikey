import tkinter as tk

class StyledList(tk.Text):
    """Text 기반으로 Listbox 유사 API를 제공하는 어댑터."""

    def __init__(self, master, split_cb, join_cb, desc_color="#1a7f37", **kwargs):
        kwargs.setdefault("wrap", "none")
        kwargs.setdefault("undo", False)
        kwargs.setdefault("cursor", "arrow")
        kwargs.setdefault("height", 1)
        super().__init__(master, **kwargs)

        self._split_cb = split_cb
        self._join_cb = join_cb
        self._desc_color = desc_color
        self._lines: list[tuple[str, str]] = []
        self._cur_index: int | None = None

        self.tag_configure("desc", foreground=self._desc_color)
        self.tag_configure("selrow", background="lightblue", foreground="black")
        self.configure(state="disabled")

    # ---------- 내부 렌더 ----------
    def _render_all(self):
        self.configure(state="normal")
        tk.Text.delete(self, "1.0", "end")
        for raw, desc in self._lines:
            tk.Text.insert(self, "end", raw)
            if desc:
                tk.Text.insert(self, "end", " - ")
                tk.Text.insert(self, "end", desc, ("desc",))
            tk.Text.insert(self, "end", "\n")
        self.configure(state="disabled")

        if self._cur_index is not None and 0 <= self._cur_index < len(self._lines):
            self._apply_selection(self._cur_index)

    def _apply_selection(self, idx: int | None):
        self.tag_remove("selrow", "1.0", "end")
        if idx is None or idx < 0 or idx >= len(self._lines):
            self._cur_index = None
            return
        self._cur_index = idx
        ln = idx + 1
        self.tag_add("selrow", f"{ln}.0", f"{ln}.0 lineend")

    # ---------- Listbox 호환 ----------
    def size(self):
        return len(self._lines)

    def get(self, idx: int) -> str:
        raw, desc = self._lines[idx]
        return self._join_cb(raw, desc)

    def insert(self, index, s: str):
        if index in (tk.END, "end"):
            index = len(self._lines)
        index = max(0, min(int(index), len(self._lines)))

        raw, desc = self._split_cb(s)
        self._lines.insert(index, (raw, desc))
        self._render_all()

    def delete(self, start, end=None):
        def _to_int(val):
            if val in (tk.END, "end"):
                return len(self._lines) - 1
            if isinstance(val, str):
                if "." in val:
                    try:
                        return max(0, min(int(val.split(".", 1)[0]) - 1, len(self._lines) - 1))
                    except Exception:
                        return 0
                try:
                    return int(val)
                except Exception:
                    return 0
            return int(val)

        if end is None:
            idx = _to_int(start)
            if 0 <= idx < len(self._lines):
                del self._lines[idx]
        else:
            s = _to_int(start)
            e = _to_int(end)
            if (start in (0, "0", "1.0")) and (end in (tk.END, "end")):
                self._lines.clear()
            else:
                if s <= e and len(self._lines) > 0:
                    del self._lines[s:e + 1]

        self._render_all()

    def selection_clear(self, *_):
        self._apply_selection(None)

    def selection_set(self, idx: int):
        self._apply_selection(int(idx))

    def activate(self, idx: int):
        self._apply_selection(int(idx))

    def curselection(self):
        return () if self._cur_index is None else (self._cur_index,)

    def see(self, idx: int):
        ln = int(idx) + 1
        tk.Text.see(self, f"{ln}.0")

    def bbox(self, idx: int):
        ln = int(idx) + 1
        info = self.dlineinfo(f"{ln}.0")
        if not info:
            return None
        x, y, w, h, _ = info
        return (x, y, w, h)

    def nearest(self, y: int):
        idx = self.index(f"@0,{int(y)}")
        line = int(str(idx).split(".")[0]) - 1
        if line < 0 or line >= len(self._lines):
            line = -1
        return line

    def cget(self, key):
        return super().cget(key)

