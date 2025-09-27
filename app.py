import sys
import threading
import tkinter as tk

try:
    import ctypes
    import platform
    if platform.system() == "Windows":
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

from ui.main_window import MacroUI
from core.keyboard_hotkey import keyboard

def main():
    root = tk.Tk()
    ui = MacroUI(root)

    def cleanup_hotkeys():
        if keyboard is None:
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
            try:
                if hasattr(ui, "_confirm_save_if_dirty"):
                    if not ui._confirm_save_if_dirty():
                        return
            except Exception:
                pass

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
