# core/state.py

def default_settings():
    return {
        "repeat": 1,
        "step_delay": 0.03,
        "mouse_move_duration": 0.0
    }


def default_hotkeys():
    return {"start": "f8", "stop": "f9"}


class GlobalState:
    current_macro = None
    image_match_results = {}
    image_match_stack = []  # Stack to track parent-child relationships of image conditions
