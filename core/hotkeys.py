# core/hotkeys.py
"""전역 단축키 문자열 다루기.

`keyboard` 라이브러리는 `"f8"`, `"ctrl+1"` 처럼 소문자 조합을 쓰고,
화면에는 `F8`, `Ctrl+1` 처럼 보여주는 편이 읽기 좋다. 두 표기를 여기서만
오간다.
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Tuple

# 화면 표기 <-> keyboard 표기가 다른 것들
_PRETTY = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
    "esc": "Esc", "enter": "Enter", "tab": "Tab", "space": "Space",
    "backspace": "Backspace", "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "page up": "PageUp", "page down": "PageDown",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
}
_FROM_PRETTY = {v.lower(): k for k, v in _PRETTY.items()}
_FROM_PRETTY.update({"pageup": "page up", "pagedown": "page down"})


def normalize(text: str) -> str:
    """화면 표기 -> keyboard 표기. 빈 문자열이면 단축키 없음."""
    if not text:
        return ""
    parts = []
    for chunk in str(text).replace("-", "+").split("+"):
        chunk = chunk.strip()
        if not chunk:
            continue
        low = chunk.lower()
        parts.append(_FROM_PRETTY.get(low, low))
    return "+".join(parts)


def display(text: str) -> str:
    """keyboard 표기 -> 화면 표기."""
    if not text:
        return "—"
    parts = []
    for chunk in str(text).split("+"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.append(_PRETTY.get(chunk.lower(), chunk.upper()
                                 if len(chunk) == 1 else chunk.capitalize()))
    return "+".join(parts)


# QKeySequence 가 알아듣는 이름 (화면 표기와 다른 것만)
_QT_NAMES = {
    "esc": "Esc", "enter": "Return", "page up": "PgUp", "page down": "PgDown",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "win": "Meta",
}


def qt_sequence(text: str) -> str:
    """keyboard 표기 -> QKeySequence 문자열. 못 옮기면 빈 문자열."""
    if not text:
        return ""
    parts = []
    for chunk in normalize(text).split("+"):
        if not chunk:
            continue
        if chunk in _QT_NAMES:
            parts.append(_QT_NAMES[chunk])
        elif len(chunk) == 1:
            parts.append(chunk.upper())
        else:
            parts.append(chunk.capitalize())
    return "+".join(parts)


def is_bare_modifier(text: str) -> bool:
    """수정키만 있는 조합은 단축키로 쓸 수 없다."""
    keys = [k for k in normalize(text).split("+") if k]
    return bool(keys) and all(k in ("ctrl", "alt", "shift", "win") for k in keys)


class HotkeyBinder:
    """전역 단축키 묶음을 한꺼번에 걸고 푼다.

    폴더를 옮기면 이전 폴더의 단축키는 풀고 새 폴더 것만 걸어야 하므로,
    등록해 둔 것을 기억하고 통째로 교체할 수 있게 한다.
    """

    def __init__(self):
        self._handles: List[object] = []
        self._bound: Dict[str, str] = {}      # 단축키 -> 무엇에 걸렸는지(설명)

    @property
    def bound(self) -> Dict[str, str]:
        return dict(self._bound)

    def clear(self) -> None:
        if not self._handles:
            self._bound.clear()
            return
        try:
            from core.keyboard_hotkey import _get_keyboard
            kb = _get_keyboard()
        except Exception:
            self._handles.clear()
            self._bound.clear()
            return

        for handle in self._handles:
            try:
                kb.remove_hotkey(handle)
            except Exception:
                pass
        self._handles.clear()
        self._bound.clear()

    def bind(self, entries: Iterable[Tuple[str, str, Callable[[], None]]]) -> List[str]:
        """entries: (단축키, 설명, 누를 때 할 일). 걸지 못한 단축키 목록을 반환.

        같은 단축키에 여러 개가 걸리면 **모두** 실행한다. 여러 매크로를 한 키로
        동시에 돌리고 싶은 경우가 있어 겹침을 막지 않는다.
        """
        self.clear()

        grouped: Dict[str, List[Tuple[str, Callable[[], None]]]] = {}
        for key, label, action in entries:
            key = normalize(key)
            if not key or is_bare_modifier(key):
                continue
            grouped.setdefault(key, []).append((label, action))

        try:
            from core.keyboard_hotkey import _get_keyboard
            kb = _get_keyboard()
        except Exception:
            return list(grouped)

        failed: List[str] = []
        for key, items in grouped.items():
            def run_all(items=items):
                for _, action in items:
                    try:
                        action()
                    except Exception:
                        pass

            try:
                self._handles.append(kb.add_hotkey(key, run_all, suppress=False))
                self._bound[key] = " · ".join(label for label, _ in items)
            except Exception:
                failed.append(key)

        return failed
