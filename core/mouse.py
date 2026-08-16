# core/mouse.py
from __future__ import annotations
import math
import time
import autoit


def _ease_in_out(t: float) -> float:
    # smoothstep: 시작/끝은 느리고 중간은 빠르게 (사람 손 느낌)
    return t * t * (3 - 2 * t)


def _settle_at(x: int, y: int, timeout: float = 0.1):
    """커서가 목표 좌표에 실제로 도달할 때까지 대기 (OS 입력 큐 반영 보장)."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        cx, cy = autoit.mouse_get_pos()
        if abs(cx - x) <= 1 and abs(cy - y) <= 1:
            return
        time.sleep(0.002)


def smooth_move(x: int, y: int, duration: float = 0.0):
    start_x, start_y = autoit.mouse_get_pos()
    dx = x - start_x
    dy = y - start_y
    distance = math.hypot(dx, dy)

    if distance < 1 or duration <= 0:
        autoit.mouse_move(x, y, speed=0)
        _settle_at(x, y)
        return

    # 벽시계 기준으로 duration을 실제로 보장 (Windows sleep 해상도 편차 방지)
    start_t = time.perf_counter()
    while True:
        t = (time.perf_counter() - start_t) / duration
        if t >= 1.0:
            break
        e = _ease_in_out(t)
        cx = round(start_x + dx * e)
        cy = round(start_y + dy * e)
        autoit.mouse_move(cx, cy, speed=0)
        time.sleep(0.001)

    # 마지막은 정확한 목표 좌표로 보정하고, 실제 도달까지 정착 대기
    autoit.mouse_move(x, y, speed=0)
    _settle_at(x, y)


def mouse_move_click(x: int, y: int, button: str = "left", duration: float = 0.0):
    smooth_move(x, y, duration)
    autoit.mouse_click(button, x, y, clicks=1, speed=0)


def mouse_move_only(x: int, y: int, duration: float = 0.0):
    smooth_move(x, y, duration)


def mouse_down_at_current(button: str = "left"):
    autoit.mouse_down(button)


def mouse_up_at_current(button: str = "left"):
    autoit.mouse_up(button)


def get_mouse_position() -> tuple[int, int]:
    return autoit.mouse_get_pos()
