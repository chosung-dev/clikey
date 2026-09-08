# core/persistence.py
"""앱 상태(환경설정·최근 확인 시각 등)를 사용자 홈에 저장한다."""
from __future__ import annotations
import os, json


def _app_state_path() -> str:
    base = os.path.join(os.path.expanduser("~"), ".clikey")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "app_state.json")


def load_app_state() -> dict:
    path = _app_state_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_app_state(state: dict) -> None:
    path = _app_state_path()
    try:
        # 기존 상태와 merge
        existing = load_app_state()
        existing.update(state or {})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------- 매크로 차례

ORDER_KEY = "macro_order"


def load_macro_order(folder: str) -> list:
    """폴더에 손으로 정해둔 매크로 차례. 정한 적이 없으면 빈 목록."""
    orders = load_app_state().get(ORDER_KEY)
    names = orders.get(folder) if isinstance(orders, dict) else None
    return [str(n) for n in names] if isinstance(names, list) else []


def save_macro_order(folder: str, names) -> None:
    """폴더의 매크로 차례를 이름 순서로 적어둔다.

    파일에 넣지 않고 앱 상태에 두는 것은, 차례가 매크로의 성질이 아니라 이
    컴퓨터에서 목록을 어떻게 보고 싶은지의 문제이기 때문이다.
    """
    state = load_app_state()
    orders = state.get(ORDER_KEY)
    orders = dict(orders) if isinstance(orders, dict) else {}
    orders[folder] = [str(n) for n in names]
    save_app_state({ORDER_KEY: orders})


def move_macro_order(old_folder: str, new_folder) -> None:
    """폴더가 이름을 바꾸거나 사라질 때 적어둔 차례도 따라간다.

    `new_folder` 가 None 이면 지운다.
    """
    state = load_app_state()
    orders = state.get(ORDER_KEY)
    orders = dict(orders) if isinstance(orders, dict) else {}
    names = orders.pop(old_folder, None)
    if names is None:
        return
    if new_folder:
        orders[new_folder] = names
    save_app_state({ORDER_KEY: orders})


# ---------------------------------------------------------------- 폴더 차례

FOLDER_ORDER_KEY = "folder_order"


def load_folder_order() -> list:
    """사이드바에 손으로 정해둔 폴더 차례. 정한 적이 없으면 빈 목록."""
    names = load_app_state().get(FOLDER_ORDER_KEY)
    return [str(n) for n in names] if isinstance(names, list) else []


def save_folder_order(names) -> None:
    save_app_state({FOLDER_ORDER_KEY: [str(n) for n in names]})


def rename_in_folder_order(old: str, new) -> None:
    """폴더 이름이 바뀌거나 사라지면 차례에서도 고친다.

    `new` 가 None 이면 뺀다. 안 고치면 이름만 바꿔도 차례에 없는 폴더가 되어
    맨 위로 튄다.
    """
    names = load_folder_order()
    if old not in names:
        return
    if new is None:
        names = [n for n in names if n != old]
    else:
        names = [new if n == old else n for n in names]
    save_folder_order(names)
