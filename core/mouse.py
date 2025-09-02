# core/mouse.py
from __future__ import annotations
from typing import Optional, Tuple

import tkinter as tk

try:
    import pyautogui
except Exception:
    pyautogui = None  # type: ignore

# AutoIt (Windows 전용)
try:
    import autoit  # pip install pyautoit
    AUTOIT_AVAILABLE = True
except Exception:
    AUTOIT_AVAILABLE = False

def mouse_move_click(root: tk.Tk, x: int, y: int, button: str = "left"):
    """Move to (x,y) and click with given button. Prefer AutoIt, fallback to pyautogui."""
    b = "left" if button not in ("left", "right", "middle") else button

    # 좌표 안전성
    try:
        if pyautogui is not None:
            scr_w, scr_h = pyautogui.size()
            if not (0 <= x < scr_w and 0 <= y < scr_h):
                root.after(0, lambda: tk.messagebox.showwarning(
                    "좌표 오류", f"화면 범위를 벗어난 좌표입니다: ({x}, {y})"))
                return
    except Exception:
        pass

    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_move(x, y, speed=0)
            autoit.mouse_click(b, x, y, clicks=1, speed=0)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showwarning(
                "AutoIt 오류", f"AutoIt 마우스 동작 중 오류가 발생하여 pyautogui로 폴백합니다.\n\n{e}"))

    if pyautogui is not None:
        try:
            pyautogui.moveTo(x, y)
            pyautogui.click(x=x, y=y, button=b)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showerror("마우스 오류", f"마우스 동작 실패:\n{e}"))
    else:
        root.after(0, lambda: tk.messagebox.showerror("마우스 오류", "pyautogui를 사용할 수 없습니다."))

def mouse_move_only(root: tk.Tk, x: int, y: int):
    """Move mouse to (x,y) without clicking."""
    # 좌표 안전성 검사
    try:
        if pyautogui is not None:
            scr_w, scr_h = pyautogui.size()
            if not (0 <= x < scr_w and 0 <= y < scr_h):
                root.after(0, lambda: tk.messagebox.showwarning(
                    "좌표 오류", f"화면 범위를 벗어난 좌표입니다: ({x}, {y})"))
                return
    except Exception:
        pass

    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_move(x, y, speed=0)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showwarning(
                "AutoIt 오류", f"AutoIt 마우스 이동 중 오류가 발생하여 pyautogui로 폴백합니다.\n\n{e}"))

    if pyautogui is not None:
        try:
            pyautogui.moveTo(x, y)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showerror("마우스 오류", f"마우스 이동 실패:\n{e}"))
    else:
        root.after(0, lambda: tk.messagebox.showerror("마우스 오류", "pyautogui를 사용할 수 없습니다."))

def mouse_down_at_current(root: tk.Tk, button: str = "left"):
    """Press down mouse button at current position."""
    b = "left" if button not in ("left", "right", "middle") else button

    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_down(b)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showwarning(
                "AutoIt 오류", f"AutoIt 마우스 누르기 중 오류가 발생하여 pyautogui로 폴백합니다.\n\n{e}"))

    if pyautogui is not None:
        try:
            pyautogui.mouseDown(button=b)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showerror("마우스 오류", f"마우스 누르기 실패:\n{e}"))
    else:
        root.after(0, lambda: tk.messagebox.showerror("마우스 오류", "pyautogui를 사용할 수 없습니다."))

def mouse_up_at_current(root: tk.Tk, button: str = "left"):
    """Release mouse button at current position."""
    b = "left" if button not in ("left", "right", "middle") else button

    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_up(b)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showwarning(
                "AutoIt 오류", f"AutoIt 마우스 떼기 중 오류가 발생하여 pyautogui로 폴백합니다.\n\n{e}"))

    if pyautogui is not None:
        try:
            pyautogui.mouseUp(button=b)
            return
        except Exception as e:
            root.after(0, lambda: tk.messagebox.showerror("마우스 오류", f"마우스 떼기 실패:\n{e}"))
    else:
        root.after(0, lambda: tk.messagebox.showerror("마우스 오류", "pyautogui를 사용할 수 없습니다."))
