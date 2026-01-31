import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
import webbrowser

try:
    import ctypes
    import platform
    if platform.system() == "Windows":
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

from ui.main_window import MacroUI
from core.keyboard_hotkey import keyboard
from utils.admin_utils import request_admin_if_needed
from core.version import __version__, get_latest_version, get_release_url, is_update_available
from core.persistence import load_app_state, save_app_state

def main():
    # Windows에서 관리자 권한 확인 및 요청
    if not request_admin_if_needed():
        return

    root = tk.Tk()
    ui = MacroUI(root)

    # 버전 업데이트 체크 (별도 스레드, 하루에 한 번)
    def check_update():
        try:
            app_state = load_app_state()
            last_check = app_state.get("last_update_check", 0)
            now = time.time()

            # 24시간(86400초)이 지나지 않았으면 스킵
            if now - last_check < 86400:
                return

            latest = get_latest_version()
            if latest and is_update_available(__version__, latest):
                def show_update_dialog():
                    if messagebox.askyesno(
                        "업데이트 확인",
                        f"업데이트가 있습니다.\n다운로드 하러 가시겠습니까?\n\n현재 버전: {__version__}\n최신 버전: {latest}"
                    ):
                        webbrowser.open(get_release_url())
                root.after(0, show_update_dialog)

            # 체크 시간 저장
            app_state["last_update_check"] = now
            save_app_state(app_state)
        except Exception:
            pass

    threading.Thread(target=check_update, daemon=True).start()

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
