from enum import Enum


class EventType(Enum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    DELAY = "delay"
    IF = "if"
    EXIT = "exit"