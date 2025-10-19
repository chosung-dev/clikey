from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
import json
import uuid

from core.event_types import EventType, ConditionType


@dataclass
class MacroBlock:
    event_type: EventType
    event_data: Optional[str] = None
    action: Optional[Union[str, float, bool]] = None
    position: Optional[str] = None
    description: str = ""
    macro_blocks: List[MacroBlock] = field(default_factory=list)
    key: str = field(default_factory=lambda: MacroBlock._generate_key())
    condition_type: Optional[ConditionType] = None

    @staticmethod
    def _generate_key() -> str:
        return str(uuid.uuid4())[:12]

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "event_type": self.event_type.value,
            "event_data": self.event_data,
            "action": self.action,
            "position": self.position,
            "description": self.description,
            "key": self.key
        }

        if self.condition_type:
            result["condition_type"] = self.condition_type.value

        if self.macro_blocks:
            result["macro_blocks"] = [block.to_dict() for block in self.macro_blocks]

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MacroBlock:
        event_type = EventType(data["event_type"])
        condition_type = ConditionType(data["condition_type"]) if data.get("condition_type") else None
        macro_blocks = [cls.from_dict(block_data) for block_data in data.get("macro_blocks", [])]
        key = data.get("key", cls._generate_key())

        return cls(
            event_type=event_type,
            event_data=data.get("event_data"),
            action=data.get("action"),
            position=data.get("position"),
            description=data.get("description", ""),
            macro_blocks=macro_blocks,
            key=key,
            condition_type=condition_type
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> MacroBlock:
        return cls.from_dict(json.loads(json_str))

    def get_display_text(self) -> str:
        if self.event_type == EventType.KEYBOARD:
            action_text = {"press": "누르기", "down": "누르고있기", "up": "떼기"}.get(self.action, self.action)
            return f"⌨️ 키보드 {self.event_data} ({action_text})"
        elif self.event_type == EventType.MOUSE:
            position_display = self.position
            if self.position and self.position.strip() == "@parent":
                position_display = "상위좌표"
            return f"🖱️ 마우스 {self.event_data} {self.action} @{position_display}"
        elif self.event_type == EventType.DELAY:
            return f"⏱️ 대기 {self.action}초"
        elif self.event_type == EventType.IF:
            if self.condition_type == ConditionType.RGB_MATCH:
                position_display = self.position
                if self.position and self.position.strip() == "@parent":
                    position_display = "상위좌표"
                return f"[조건] 색상 매치 {position_display}"
            elif self.condition_type == ConditionType.IMAGE_MATCH:
                return f"[조건] 이미지 매치 @{self.event_data}"
            elif self.condition_type == ConditionType.COORDINATE_CONDITION:
                return f"[조건] 좌표 조건 @{self.position}"
            else:
                return f"[조건] {self.event_data} @{self.position}"
        elif self.event_type == EventType.EXIT:
            return f"⏹️ 매크로 중지"
        else:
            return f"❓ {self.event_type.value}: {self.event_data}"

    def parse_position(self) -> Optional[tuple[int, int]]:
        if not self.position:
            return None
        try:
            x, y = self.position.split(",")
            return (int(x.strip()), int(y.strip()))
        except (ValueError, AttributeError):
            return None

    def has_reference_position(self) -> bool:
        if not self.position:
            return False
        return (self.position.strip() == "@parent" or
                ("." in self.position and any(coord in self.position for coord in [".x", ".y"])))

    def clear_reference_position(self):
        if self.has_reference_position():
            self.position = "0,0"

    def copy(self) -> 'MacroBlock':
        copied_nested_blocks = [block.copy() for block in self.macro_blocks]
        return MacroBlock(
            event_type=self.event_type,
            event_data=self.event_data,
            action=self.action,
            position=self.position,
            description=self.description,
            macro_blocks=copied_nested_blocks,
            key=MacroBlock._generate_key(),
            condition_type=self.condition_type
        )