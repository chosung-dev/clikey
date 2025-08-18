# app.py
import sys
import threading
import tkinter as tk

# Windows DPI awareness (optional)
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

from ui.macro_ui import MacroUI
from core.keyboard_hotkey import KEYBOARD_AVAILABLE, keyboard  # re-exported

def main():
    root = tk.Tk()
    ui = MacroUI(root)

    def cleanup_hotkeys():
        if not KEYBOARD_AVAILABLE or keyboard is None:
            return
        for k in ("start", "stop"):
            h = ui.hotkey_handles.get(k)
            if h is not None:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
                ui.hotkey_handles[k] = None

    def on_close():
        try:
            if getattr(ui, "running", False):
                ui.stop_execution()
            t = getattr(ui, "worker_thread", None)
            if isinstance(t, threading.Thread) and t.is_alive():
                t.join(timeout=1.5)
        except Exception:
            pass
        finally:
            cleanup_hotkeys()
            try:
                root.destroy()
            except Exception:
                sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    finally:
        cleanup_hotkeys()

if __name__ == "__main__":
    main()
