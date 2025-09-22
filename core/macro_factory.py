# core/macro_factory.py
from core.macro_block import MacroBlock
from core.event_types import EventType


class MacroFactory:
    """Factory class for creating common macro blocks."""

    @staticmethod
    def create_keyboard_block(key: str, action: str = "press", description: str = "") -> MacroBlock:
        """Create a keyboard macro block."""
        return MacroBlock(
            event_type=EventType.KEYBOARD,
            event_data=key,
            action=action,
            description=description
        )

    @staticmethod
    def create_mouse_block(button: str, action: str, x: int, y: int, description: str = "") -> MacroBlock:
        """Create a mouse macro block."""
        return MacroBlock(
            event_type=EventType.MOUSE,
            event_data=button,
            action=action,
            position=f"{x},{y}",
            description=description
        )

    @staticmethod
    def create_delay_block(seconds: float, description: str = "") -> MacroBlock:
        """Create a delay macro block."""
        return MacroBlock(
            event_type=EventType.DELAY,
            action=seconds,
            description=description
        )

    @staticmethod
    def create_if_block(condition_type: str, x: int, y: int, expected_value: str = "",
                       description: str = "") -> MacroBlock:
        """Create an IF conditional macro block."""
        return MacroBlock(
            event_type=EventType.IF,
            event_data=condition_type,
            action=expected_value,
            position=f"{x},{y}",
            description=description,
            macro_blocks=[]
        )

    @staticmethod
    def create_exit_block(should_exit: bool = True, description: str = "") -> MacroBlock:
        """Create an exit macro block."""
        return MacroBlock(
            event_type=EventType.EXIT,
            action=should_exit,
            description=description
        )