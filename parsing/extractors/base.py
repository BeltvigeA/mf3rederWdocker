from __future__ import annotations

import math
import re
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


def toFloat(value: str | None) -> float | None:
    if value is None:
        return None
    cleanedValue = value.strip().replace(',', '.')
    if not cleanedValue:
        return None
    try:
        return float(cleanedValue)
    except ValueError:
        return None


def parseDurationToSeconds(text: str | None) -> int | None:
    if not text:
        return None
    cleanedText = text.strip()
    if not cleanedText:
        return None
    lowerText = cleanedText.lower()
    matches = re.findall(r"(\d+)\s*([hms])", lowerText)
    if matches:
        totalSeconds = 0
        for amountText, unit in matches:
            amount = int(amountText)
            if unit == 'h':
                totalSeconds += amount * 3600
            elif unit == 'm':
                totalSeconds += amount * 60
            elif unit == 's':
                totalSeconds += amount
        return totalSeconds
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", cleanedText):
        hoursText, minutesText, secondsText = cleanedText.split(':')
        return int(hoursText) * 3600 + int(minutesText) * 60 + int(secondsText)
    if re.fullmatch(r"\d{1,2}:\d{2}", cleanedText):
        minutesText, secondsText = cleanedText.split(':')
        return int(minutesText) * 60 + int(secondsText)
    return None


def deriveWeightGFromLength(lengthMm: float | None, diameterMm: float | None, densityGPerCm3: float | None) -> float | None:
    if lengthMm is None or diameterMm is None or densityGPerCm3 is None:
        return None
    diameterCm = diameterMm / 10.0
    radiusCm = diameterCm / 2.0
    lengthCm = lengthMm / 10.0
    volumeCm3 = math.pi * radiusCm * radiusCm * lengthCm
    return volumeCm3 * densityGPerCm3
