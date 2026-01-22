from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .base import ParsedValues
from ..gcode_view import GCodeView


SEARCH_KEYS = [
    'model printing time',
    'total filament weight [g]',
    'total filament length [mm]',
    'total filament volume [cm^3]',
    'enable_support',
    'filament_type',
    'layer_height',
    'nozzle_diameter',
    'sparse_infill_density',
    'printer_model',
]


class BambuGcodeExtractor:
    def extract(self, gview: GCodeView) -> ParsedValues:
        gcodeText = gview.text
        values: Dict[str, Any] = {}
        for key in SEARCH_KEYS:
            pattern = re.compile(rf"{re.escape(key)}\s*=\s*(.*)", re.IGNORECASE)
            match = pattern.search(gcodeText)
            if match:
                values[key] = match.group(1).strip()
        objectsMatch = re.search(r'model label id:\s*([0-9,]+)', gcodeText, re.IGNORECASE)
        if objectsMatch:
            ids = [segment for segment in objectsMatch.group(1).split(',') if segment.strip()]
            values['objectsOnPlate'] = str(len(ids))
        # Try to parse print time - handles formats like "2h 30m 45s", "2m 24s", or "45s"
        printTimeSec = 0
        timeMatch = re.search(r'model printing time:\s*((?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?)', gcodeText, re.IGNORECASE)
        if timeMatch:
            hours = int(timeMatch.group(2)) if timeMatch.group(2) else 0
            minutes = int(timeMatch.group(3)) if timeMatch.group(3) else 0
            seconds = int(timeMatch.group(4)) if timeMatch.group(4) else 0
            printTimeSec = hours * 3600 + minutes * 60 + seconds

        # Fallback to total estimated time if print time is 0 or not found
        if printTimeSec == 0:
            totalTimeMatch = re.search(r'total estimated time:\s*((?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?)', gcodeText, re.IGNORECASE)
            if totalTimeMatch:
                hours = int(totalTimeMatch.group(2)) if totalTimeMatch.group(2) else 0
                minutes = int(totalTimeMatch.group(3)) if totalTimeMatch.group(3) else 0
                seconds = int(totalTimeMatch.group(4)) if totalTimeMatch.group(4) else 0
                printTimeSec = hours * 3600 + minutes * 60 + seconds

        if printTimeSec > 0:
            values['printTimeSec'] = str(printTimeSec)
        weightMatch = re.search(r'total filament weight \[g\]\s*[=:]\s*([0-9., ]+)', gcodeText, re.IGNORECASE)
        lengthMatch = re.search(r'total filament length \[mm\]\s*[=:]\s*([0-9., ]+)', gcodeText, re.IGNORECASE)
        volumeMatch = re.search(r'total filament volume \[cm\^3\]\s*[=:]\s*([0-9., ]+)', gcodeText, re.IGNORECASE)

        weights = []
        if weightMatch:
            # Parse all weights, but filter out unused filaments (< 0.01g)
            all_weights = [float(piece.strip()) for piece in weightMatch.group(1).split(',') if piece.strip()]
            weights = [w for w in all_weights if w > 0.01]
            values['filamentWeights'] = weights
            values['filamentUsedGrams'] = str(sum(weights)) if weights else '0'
        # Parse filament types and colors (comma-separated in Bambu, semi-colon in some configs)
        filamentTypeMatch = re.search(r';\s*filament_type\s*=\s*(.*)', gcodeText, re.IGNORECASE)
        filamentColorMatch = re.search(r';\s*(?:filament_colour|extruder_colour)\s*=\s*(.*)', gcodeText, re.IGNORECASE)

        filamentTypes: List[str] = []
        if filamentTypeMatch:
            rawTypes = filamentTypeMatch.group(1).strip()
            if ';' in rawTypes:
                filamentTypes = [t.strip().strip('"') for t in rawTypes.split(';')]
            else:
                filamentTypes = [t.strip().strip('"') for t in rawTypes.split(',')]

        filamentColors: List[str] = []
        if filamentColorMatch:
            rawColors = filamentColorMatch.group(1).strip()
            if ';' in rawColors:
                filamentColors = [c.strip().strip('"') for c in rawColors.split(';')]
            else:
                filamentColors = [c.strip().strip('"') for c in rawColors.split(',')]


        analysis: List[Dict[str, Any]] = []
        if weightMatch:
            # Parse ALL values to get correct indices
            all_weights = [float(piece.strip()) for piece in weightMatch.group(1).split(',') if piece.strip()]
            all_lengths = [float(piece.strip()) for piece in lengthMatch.group(1).split(',') if piece.strip()] if lengthMatch else []
            all_volumes = [float(piece.strip()) for piece in volumeMatch.group(1).split(',') if piece.strip()] if volumeMatch else []

            # Only include filaments with weight > 0.01g
            for index, weight in enumerate(all_weights):
                if weight > 0.01:
                    item = {
                        'amsIndex': index,
                        'toolIndex': index,
                        'lengthMm': all_lengths[index] if index < len(all_lengths) else None,
                        'volumeCm3': all_volumes[index] if index < len(all_volumes) else None,
                        'weightG': weight,
                        'filamentType': filamentTypes[index] if index < len(filamentTypes) else None,
                        'filamentColor': filamentColors[index] if index < len(filamentColors) else None,
                    }
                    analysis.append(item)

        values['filamentAnalysis'] = analysis

        # Add tools/usedTools for parity
        values['tools'] = analysis
        values['usedTools'] = [a for a in analysis if a.get('weightG', 0) > 0.01]
        values['usedToolIndices'] = [a['toolIndex'] for a in values['usedTools']]


        changes = re.findall(r'M620\s+S\d+A', gcodeText)
        values['filamentChanges'] = str(len(changes))
        purgeLength = 0.0
        for section in re.findall(r';\s*FLUSH_START\s*(.*?)\s*;\s*FLUSH_END', gcodeText, re.DOTALL | re.IGNORECASE):
            for amount in re.findall(r'G1\s+E([-+]?[0-9]*\.?[0-9]+)', section):
                purgeLength += abs(float(amount))
        diameterMatch = re.search(r'filament_diameter:\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
        densityMatch = re.search(r'filament_density:\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
        if purgeLength and diameterMatch and densityMatch:
            diameter = float(diameterMatch.group(1).split(',')[0])
            density = float(densityMatch.group(1).split(',')[0])
            volumeMm3 = purgeLength * math.pi * (diameter / 2) ** 2
            volumeCm3 = volumeMm3 / 1000
            purgeGrams = volumeCm3 * density
            values['filamentPurgeGrams'] = f"{purgeGrams:.2f}"
        else:
            values['filamentPurgeGrams'] = '0'
        layerMatch = re.search(r'total layer number:\s*(\d+)', gcodeText, re.IGNORECASE)
        if layerMatch:
            values['totalLayers'] = layerMatch.group(1)
        heightMatch = re.search(r'max_z_height:\s*([0-9.]+)', gcodeText, re.IGNORECASE)
        if heightMatch:
            values['maxZHeight'] = heightMatch.group(1)
        values.setdefault('slicerType', 'Unknown')
        values.setdefault('estimatedPowerConsumptionWh', '0')
        values.setdefault('buildPlateTemperature', '0')
        values.setdefault('hotendTemperature', '0')
        values.setdefault('objects', [])
        values.setdefault('orderedObjects', [])
        return ParsedValues(fieldValues=values, meta={'slicer': 'bambu'})
