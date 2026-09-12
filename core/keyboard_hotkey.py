# core/keyboard_hotkey.py
"""keyboard 라이브러리를 늦게 불러오기 위한 자리.

임포트만으로 전역 후킹이 딸려와 시작이 느려진다. 실제로 키를 다룰 때에만
불러온다.

키 이름을 옮기는 일은 core/hotkeys.py 하나가 맡는다.
"""
from __future__ import annotations

# Lazy import for faster startup
keyboard = None

def _get_keyboard():
    global keyboard
    if keyboard is None:
        import keyboard as kb
        keyboard = kb
    return keyboard
