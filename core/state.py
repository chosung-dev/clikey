# core/state.py

def default_settings():
    return {
        "repeat": 1,
        "start_delay": 1,
        "step_delay": 0.03,
        "beep_on_finish": False
    }


def default_hotkeys():
    return {"start": "F8", "stop": "F9"}


class GlobalState:
    current_macro = None
    image_match_results = {}
    image_match_stack = []  # Stack to track parent-child relationships of image conditions
