import tkinter as tk


class MacroHighlighter:
    def __init__(self, listbox: tk.Listbox):
        self.listbox = listbox

    def highlight_index(self, idx: int):
        try:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.activate(idx)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
        except Exception:
            pass

    def clear_highlight(self):
        try:
            self.listbox.selection_clear(0, tk.END)
        except Exception:
            pass