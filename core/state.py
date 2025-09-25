# core/state.py
def default_settings():
    return {
        "repeat": 1,
        "start_delay": 1,
        "step_delay": 0.001,
        "beep_on_finish": False
    }

def default_hotkeys():
    return {"start": "F8", "stop": "F9"}


class GlobalState:
    """전역 상태 관리 클래스"""
    current_macro = None
    image_match_results = {}
