from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .base import ParsedValues
from ..gcode_view import GCodeView


class OrcaGcodeExtractor:
    """Extractor for Orca Slicer GCODE files.

    Orca Slicer is a fork of Bambu Studio with some format differences.
    This extractor handles Orca-specific header format while also checking
    for Bambu-compatible fields.
    """

    def extract(self, gview: GCodeView) -> ParsedValues:
        gcodeText = gview.text
        values: Dict[str, Any] = {}

        # === Parse Orca-specific header format ===
        # ; model printing time: 5h 54m 40s; total estimated time: 6h 0m 41s
        timeMatch = re.search(
            r';\s*model printing time:\s*(\d+)h\s*(\d+)m\s*(\d+)s',
            gcodeText,
            re.IGNORECASE
        )
        if timeMatch:
            hours, minutes, seconds = map(int, timeMatch.groups())
            values['printTimeSec'] = str(hours * 3600 + minutes * 60 + seconds)

        # ; total layer number: 140
        layerMatch = re.search(r';\s*total layer number:\s*(\d+)', gcodeText, re.IGNORECASE)
        if layerMatch:
            values['totalLayers'] = layerMatch.group(1)

        # ; model label id: 840
        objectsMatch = re.search(r';\s*model label id:\s*([0-9,]+)', gcodeText, re.IGNORECASE)
        if objectsMatch:
            ids = [segment for segment in objectsMatch.group(1).split(',') if segment.strip()]
            values['objectsOnPlate'] = str(len(ids))

        # ; max_z_height: 28.00
        heightMatch = re.search(r';\s*max_z_height:\s*([0-9.]+)', gcodeText, re.IGNORECASE)
        if heightMatch:
            values['maxZHeight'] = heightMatch.group(1)

        # === Try Bambu-compatible fields (since Orca is a fork) ===
        # Check for filament weight in Bambu format
        weightMatch = re.search(
            r';\s*total filament weight \[g\]\s*[=:]\s*([0-9.,]+)',
            gcodeText,
            re.IGNORECASE
        )
        lengthMatch = re.search(
            r';\s*total filament length \[mm\]\s*[=:]\s*([0-9.,]+)',
            gcodeText,
            re.IGNORECASE
        )
        volumeMatch = re.search(
            r';\s*total filament volume \[cm\^3\]\s*[=:]\s*([0-9.,]+)',
            gcodeText,
            re.IGNORECASE
        )

        weights = []
        if weightMatch:
            weights = [float(piece) for piece in weightMatch.group(1).split(',') if piece]
            values['filamentWeights'] = weights
            values['filamentUsedGrams'] = str(sum(weights))

        # Build filament analysis
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
        elif lengthMatch:
            # If no weight but we have length, try to calculate weight
            lengths = [float(piece) for piece in lengthMatch.group(1).split(',') if piece]
            volumes = [float(piece) for piece in volumeMatch.group(1).split(',')] if volumeMatch else []

            # Extract density and diameter from config block
            densityMatch = re.search(r';\s*filament_density[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
            diameterMatch = re.search(r';\s*filament_diameter[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)

            if densityMatch and diameterMatch:
                densities = [float(d) for d in densityMatch.group(1).split(',') if d]
                diameters = [float(d) for d in diameterMatch.group(1).split(',') if d]

                for index, length in enumerate(lengths):
                    density = densities[index] if index < len(densities) else densities[0] if densities else 1.24
                    diameter = diameters[index] if index < len(diameters) else diameters[0] if diameters else 1.75

                    # Calculate weight: weight = length * cross_section_area * density
                    # cross_section_area = π * (diameter/2)^2
                    volumeMm3 = length * math.pi * (diameter / 2) ** 2
                    volumeCm3 = volumeMm3 / 1000
                    weight = volumeCm3 * density

                    weights.append(weight)
                    item = {
                        'lengthMm': length,
                        'volumeCm3': volumes[index] if index < len(volumes) else volumeCm3,
                        'weightG': weight,
                    }
                    analysis.append(item)

                if weights:
                    values['filamentWeights'] = weights
                    values['filamentUsedGrams'] = f"{sum(weights):.2f}"

        values['filamentAnalysis'] = analysis

        # === Parse config block values ===
        # Look for config values that might be useful
        configPatterns = {
            'enable_support': r';\s*enable_support\s*=\s*(\d+)',
            'filament_type': r';\s*filament_type\s*=\s*([^\n;]+)',
            'layer_height': r';\s*layer_height\s*=\s*([0-9.]+)',
            'nozzle_diameter': r';\s*nozzle_diameter\s*=\s*([0-9.]+)',
            'sparse_infill_density': r';\s*sparse_infill_density\s*=\s*([0-9.]+%?)',
            'printer_model': r';\s*printer_model\s*=\s*([^\n;]+)',
        }

        for key, pattern in configPatterns.items():
            match = re.search(pattern, gcodeText, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                values[key] = value

        # === Count filament changes (M620 commands) ===
        changes = re.findall(r'M620\s+S\d+A', gcodeText)
        values['filamentChanges'] = str(len(changes))

        # === Calculate purge/waste filament ===
        purgeLength = 0.0
        for section in re.findall(
            r';\s*FLUSH_START\s*(.*?)\s*;\s*FLUSH_END',
            gcodeText,
            re.DOTALL | re.IGNORECASE
        ):
            for amount in re.findall(r'G1\s+E([-+]?[0-9]*\.?[0-9]+)', section):
                purgeLength += abs(float(amount))

        if purgeLength:
            diameterMatch = re.search(r';\s*filament_diameter[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
            densityMatch = re.search(r';\s*filament_density[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)

            if diameterMatch and densityMatch:
                diameter = float(diameterMatch.group(1).split(',')[0])
                density = float(densityMatch.group(1).split(',')[0])
                volumeMm3 = purgeLength * math.pi * (diameter / 2) ** 2
                volumeCm3 = volumeMm3 / 1000
                purgeGrams = volumeCm3 * density
                values['filamentPurgeGrams'] = f"{purgeGrams:.2f}"

        if 'filamentPurgeGrams' not in values:
            values['filamentPurgeGrams'] = '0'

        # === Set default values ===
        values.setdefault('slicerType', 'OrcaSlicer')
        values.setdefault('estimatedPowerConsumptionWh', '0')
        values.setdefault('buildPlateTemperature', '0')
        values.setdefault('hotendTemperature', '0')
        values.setdefault('objects', [])
        values.setdefault('orderedObjects', [])

        return ParsedValues(fieldValues=values, meta={'slicer': 'orca'})
