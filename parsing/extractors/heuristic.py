from __future__ import annotations

import re
from typing import Any, Dict

from .base import ParsedValues
from ..gcode_view import GCodeView


class HeuristicExtractor:
    def extract(self, gview: GCodeView) -> ParsedValues:
        gcodeText = gview.text
        values: Dict[str, Any] = {
            'filamentAnalysis': [],
            'orderedObjects': [],
            'slicerType': 'Unknown',
            'estimatedPowerConsumptionWh': '0',
            'buildPlateTemperature': '0',
            'hotendTemperature': '0',
        }
        timeMatch = re.search(r'(?:model printing time|total estimated time)\s*[:=]\s*(\d+)h\s*(\d+)m\s*(\d+)s', gcodeText, re.IGNORECASE)
        if timeMatch:
            hours, minutes, seconds = map(int, timeMatch.groups())
            values['printTimeSec'] = str(hours * 3600 + minutes * 60 + seconds)
        objectsMatch = re.search(r'model label id:\s*([0-9,]+)', gcodeText, re.IGNORECASE)
        if objectsMatch:
            ids = [segment for segment in objectsMatch.group(1).split(',') if segment.strip()]
            values['objectsOnPlate'] = str(len(ids))
        return ParsedValues(fieldValues=values, meta={'slicer': 'unknown'})
