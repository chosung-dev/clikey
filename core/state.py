# core/state.py
def default_settings():
    return {
        "repeat": 1,
        "start_delay": 3,
        "step_delay": 0.001,
        "beep_on_finish": False
    }

def default_hotkeys():
    return {"start": "F8", "stop": "F9"}
