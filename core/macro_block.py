from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
import json
import time
import hashlib

from core.event_types import EventType


@dataclass
class MacroBlock:
    event_type: EventType
    event_data: Optional[str] = None
    action: Optional[Union[str, float, bool]] = None
    position: Optional[str] = None
    description: str = ""
    macro_blocks: List[MacroBlock] = field(default_factory=list)
    key: str = field(default_factory=lambda: MacroBlock._generate_key())

    @staticmethod
    def _generate_key() -> str:
        """Generate a unique key using timestamp and random hash."""
        timestamp = str(time.time())
        data = f"{timestamp}_{time.time_ns()}"
        return hashlib.md5(data.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        """Convert MacroBlock to dictionary for JSON serialization."""
        result = {
            "event_type": self.event_type.value,
            "event_data": self.event_data,
            "action": self.action,
            "position": self.position,
            "description": self.description,
            "key": self.key
        }

        if self.macro_blocks:
            result["macro_blocks"] = [block.to_dict() for block in self.macro_blocks]

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MacroBlock:
        """Create MacroBlock from dictionary (JSON deserialization)."""
        event_type = EventType(data["event_type"])

        macro_blocks = []
        if "macro_blocks" in data and data["macro_blocks"]:
            macro_blocks = [cls.from_dict(block_data) for block_data in data["macro_blocks"]]

        # Use existing key if available, otherwise generate new one
        key = data.get("key", cls._generate_key())

        return cls(
            event_type=event_type,
            event_data=data.get("event_data"),
            action=data.get("action"),
            position=data.get("position"),
            description=data.get("description", ""),
            macro_blocks=macro_blocks,
            key=key
        )

    def to_json(self) -> str:
        """Convert MacroBlock to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> MacroBlock:
        """Create MacroBlock from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def get_display_text(self) -> str:
        """Get display text for UI list."""
        if self.event_type == EventType.KEYBOARD:
            return f"키보드: {self.event_data} ({self.action})"
        elif self.event_type == EventType.MOUSE:
            return f"마우스: {self.event_data} {self.action} @{self.position}"
        elif self.event_type == EventType.DELAY:
            return f"대기: {self.action}초"
        elif self.event_type == EventType.IF:
            return f"조건: {self.event_data} @{self.position}"
        elif self.event_type == EventType.EXIT:
            return f"종료: {self.action}"
        else:
            return f"{self.event_type.value}: {self.event_data}"

    def parse_position(self) -> Optional[tuple[int, int]]:
        """Parse position string to (x, y) tuple."""
        if not self.position:
            return None
        try:
            x, y = self.position.split(",")
            return (int(x.strip()), int(y.strip()))
        except (ValueError, AttributeError):
            return None