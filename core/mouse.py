# core/mouse.py
from __future__ import annotations
import autoit  # pip install pyautoit

def mouse_move_click(x: int, y: int, button: str = "left"):
    b = "left" if button not in ("left", "right", "middle") else button
    autoit.mouse_click(b, x, y, clicks=1, speed=0)

def mouse_move_only(x: int, y: int):
    autoit.mouse_move(x, y, speed=0)

def mouse_down_at_current(button: str = "left"):
    b = "left" if button not in ("left", "right", "middle") else button
    autoit.mouse_down(b)

def mouse_up_at_current(button: str = "left"):
    b = "left" if button not in ("left", "right", "middle") else button
    autoit.mouse_up(b)
