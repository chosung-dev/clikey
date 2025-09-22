# core/mouse.py
from __future__ import annotations
import platform

try:
    import autoit  # pip install pyautoit
    AUTOIT_AVAILABLE = True
except ImportError:
    AUTOIT_AVAILABLE = False
    autoit = None

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

def mouse_move_click(x: int, y: int, button: str = "left"):
    button = "left" if button not in ("left", "right", "middle") else button

    # Try PyAutoGUI first (cross-platform)
    if PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.click(x, y, button=button)
            return
        except Exception:
            pass

    # Fallback to AutoIt (Windows only)
    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_click(button, x, y, clicks=1, speed=0)
            return
        except Exception:
            pass

    print(f"Mouse click at ({x}, {y}) with {button} button - no mouse library available")

def mouse_move_only(x: int, y: int):
    # Try PyAutoGUI first (cross-platform)
    if PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.moveTo(x, y)
            return
        except Exception:
            pass

    # Fallback to AutoIt (Windows only)
    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_move(x, y, speed=0)
            return
        except Exception:
            pass

    print(f"Mouse move to ({x}, {y}) - no mouse library available")

def mouse_down_at_current(button: str = "left"):
    button = "left" if button not in ("left", "right", "middle") else button

    # Try PyAutoGUI first (cross-platform)
    if PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.mouseDown(button=button)
            return
        except Exception:
            pass

    # Fallback to AutoIt (Windows only)
    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_down(button)
            return
        except Exception:
            pass

    print(f"Mouse down {button} button - no mouse library available")

def mouse_up_at_current(button: str = "left"):
    button = "left" if button not in ("left", "right", "middle") else button

    # Try PyAutoGUI first (cross-platform)
    if PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.mouseUp(button=button)
            return
        except Exception:
            pass

    # Fallback to AutoIt (Windows only)
    if AUTOIT_AVAILABLE:
        try:
            autoit.mouse_up(button)
            return
        except Exception:
            pass

    print(f"Mouse up {button} button - no mouse library available")

def get_mouse_position() -> tuple[int, int]:
    """Get current mouse position."""
    # Try PyAutoGUI first (cross-platform)
    if PYAUTOGUI_AVAILABLE:
        try:
            return pyautogui.position()
        except Exception:
            pass

    # Fallback to AutoIt (Windows only)
    if AUTOIT_AVAILABLE:
        try:
            return autoit.mouse_get_pos()
        except Exception:
            pass

    print("Get mouse position - no mouse library available")
    return (0, 0)
