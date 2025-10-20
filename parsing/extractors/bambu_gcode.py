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
        timeMatch = re.search(r'model printing time:\s*(\d+)h\s*(\d+)m\s*(\d+)s', gcodeText, re.IGNORECASE)
        if timeMatch:
            hours, minutes, seconds = map(int, timeMatch.groups())
            values['printTimeSec'] = str(hours * 3600 + minutes * 60 + seconds)
        weightMatch = re.search(r'total filament weight \[g\]\s*:\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
        lengthMatch = re.search(r'total filament length \[mm\]\s*:\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
        volumeMatch = re.search(r'total filament volume \[cm\^3\]\s*:\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
        weights = []
        if weightMatch:
            weights = [float(piece) for piece in weightMatch.group(1).split(',') if piece]
            values['filamentWeights'] = weights
            values['filamentUsedGrams'] = str(sum(weights))
        analysis: List[Dict[str, Any]] = []
        if weights:
            lengths = [float(piece) for piece in lengthMatch.group(1).split(',')] if lengthMatch else []
            volumes = [float(piece) for piece in volumeMatch.group(1).split(',')] if volumeMatch else []
            for index, weight in enumerate(weights):
                item = {
                    'lengthMm': lengths[index] if index < len(lengths) else None,
                    'volumeCm3': volumes[index] if index < len(volumes) else None,
                    'weightG': weight,
                }
                analysis.append(item)
        values['filamentAnalysis'] = analysis
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
