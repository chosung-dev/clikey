# core/mouse.py
from __future__ import annotations
import autoit  # pip install pyautoit

def mouse_move_click(x: int, y: int, button: str = "left"):
    autoit.mouse_click(button, x, y, clicks=1, speed=0)

def mouse_move_only(x: int, y: int):
    autoit.mouse_move(x, y, speed=0)

def mouse_down_at_current(button: str = "left"):
    autoit.mouse_down(button)

def mouse_up_at_current(button: str = "left"):
    autoit.mouse_up(button)

def get_mouse_position() -> tuple[int, int]:
    return autoit.mouse_get_pos()
