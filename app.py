# app.py
import sys
import threading
import tkinter as tk

# Windows에서 DPI 블러 방지(선택)
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

from macro_ui import MacroUI, KEYBOARD_AVAILABLE

# keyboard가 있다면 가져오기 (핫키 해제용, 없어도 동작)
if KEYBOARD_AVAILABLE:
    try:
        import keyboard  # type: ignore
    except Exception:
        keyboard = None
else:
    keyboard = None


def main():
    root = tk.Tk()
    ui = MacroUI(root)

    def cleanup_hotkeys():
        """등록된 전역 단축키 정리(있으면)."""
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
        """창 닫기 시 안전 종료."""
        try:
            # 실행 중이면 중지 신호
            if getattr(ui, "running", False):
                ui.stop_execution()
            # 워커 스레드가 있다면 잠시 대기
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
                # 강제 종료 백업
                sys.exit(0)

    # X 버튼/Alt+F4
    root.protocol("WM_DELETE_WINDOW", on_close)

    # ESC로도 창 닫기 원하면 주석 해제
    # root.bind("<Escape>", lambda e: on_close())

    try:
        root.mainloop()
    finally:
        # mainloop가 예외 등으로 빠질 때도 정리
        cleanup_hotkeys()


if __name__ == "__main__":
    main()
