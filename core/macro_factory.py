# core/macro_factory.py
from core.macro_block import MacroBlock
from core.event_types import EventType, ConditionType


class MacroFactory:
    """Factory class for creating common macro blocks."""

    @staticmethod
    def create_keyboard_block(key: str, description: str = "") -> MacroBlock:
        """Create a keyboard macro block."""
        return MacroBlock(
            event_type=EventType.KEYBOARD,
            event_data=key,
            action="press",
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
    def create_exit_block(should_exit: bool = True, description: str = "") -> MacroBlock:
        """Create an exit macro block."""
        return MacroBlock(
            event_type=EventType.EXIT,
            action=should_exit,
            description=description
        )

    @staticmethod
    def create_image_match_block(template_path: str, description: str = "") -> MacroBlock:
        """Create an image match conditional block using IF event type."""
        import os
        filename = os.path.basename(template_path)
        name_without_ext = os.path.splitext(filename)[0]

        return MacroBlock(
            event_type=EventType.IF,
            event_data=name_without_ext,
            action=template_path,
            condition_type=ConditionType.IMAGE_MATCH,
            description=description,
            macro_blocks=[]  # 일치할 경우 실행할 블록들을 위한 컨테이너
        )

    @staticmethod
    def create_rgb_match_block(x: int, y: int, expected_rgb: str, description: str = "") -> MacroBlock:
        """Create an RGB match conditional block using IF event type."""
        return MacroBlock(
            event_type=EventType.IF,
            event_data="rgb_check",
            action=expected_rgb,
            position=f"{x},{y}",
            condition_type=ConditionType.RGB_MATCH,
            description=description,
            macro_blocks=[]  # 일치할 경우 실행할 블록들을 위한 컨테이너
        )