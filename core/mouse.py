# core/mouse.py
from __future__ import annotations
import math
import time
import autoit


def _ease_in_out(t: float) -> float:
    # smoothstep: 시작/끝은 느리고 중간은 빠르게 (사람 손 느낌)
    return t * t * (3 - 2 * t)


def smooth_move(x: int, y: int, duration: float = 0.15):
    start_x, start_y = autoit.mouse_get_pos()
    dx = x - start_x
    dy = y - start_y
    distance = math.hypot(dx, dy)

    if distance < 1 or duration <= 0:
        autoit.mouse_move(x, y, speed=0)
        return

    # 거리에 비례해 단계 수 결정 (2~100)
    steps = max(2, min(int(distance / 5), 100))
    interval = duration / steps

    for i in range(1, steps + 1):
        t = _ease_in_out(i / steps)
        cx = round(start_x + dx * t)
        cy = round(start_y + dy * t)
        autoit.mouse_move(cx, cy, speed=0)
        time.sleep(interval)

    # 마지막은 정확한 목표 좌표로 보정
    autoit.mouse_move(x, y, speed=0)


def mouse_move_click(x: int, y: int, button: str = "left", duration: float = 0.15):
    smooth_move(x, y, duration)
    autoit.mouse_click(button, x, y, clicks=1, speed=0)


def mouse_move_only(x: int, y: int, duration: float = 0.15):
    smooth_move(x, y, duration)


def mouse_down_at_current(button: str = "left"):
    autoit.mouse_down(button)


def mouse_up_at_current(button: str = "left"):
    autoit.mouse_up(button)


def get_mouse_position() -> tuple[int, int]:
    return autoit.mouse_get_pos()
