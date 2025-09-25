from enum import Enum


class EventType(Enum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    DELAY = "delay"
    IF = "if"
    EXIT = "exit"


class ConditionType(Enum):
    RGB_MATCH = "rgb_match"
    IMAGE_MATCH = "image_match"