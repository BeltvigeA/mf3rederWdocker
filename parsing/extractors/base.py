from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from ..gcode_view import GCodeView


@dataclass
class ParsedValues:
    fieldValues: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def setDefault(self, key: str, value: Any) -> None:
        self.fieldValues.setdefault(key, value)


class IExtractor(Protocol):
    def extract(self, gview: GCodeView) -> ParsedValues: ...
