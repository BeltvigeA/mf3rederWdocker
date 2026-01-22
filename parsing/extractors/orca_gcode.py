from __future__ import annotations

import base64
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .base import ParsedValues, parseDurationToSeconds
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

        # Parse filament types and colors (semi-colon separated)
        filamentTypeMatch = re.search(r';\s*filament_type\s*=\s*(.*)', gcodeText, re.IGNORECASE)
        filamentColorMatch = re.search(r';\s*(?:filament_colour|extruder_colour)\s*=\s*(.*)', gcodeText, re.IGNORECASE)

        filamentTypes: List[str] = []
        if filamentTypeMatch:
            filamentTypes = [t.strip().strip('"') for t in filamentTypeMatch.group(1).split(';') if t.strip()]

        filamentColors: List[str] = []
        if filamentColorMatch:
            filamentColors = [c.strip().strip('"') for c in filamentColorMatch.group(1).split(';') if c.strip()]


        # Fallback: PrusaSlicer/Klipper style format
        # ; estimated printing time (normal mode) = 43m 45s
        if 'printTimeSec' not in values:
            estTimeMatch = re.search(
                r';\s*estimated printing time.*?=\s*([\dhms ]+)',
                gcodeText,
                re.IGNORECASE
            )
            if estTimeMatch:
                parsedSeconds = parseDurationToSeconds(estTimeMatch.group(1))
                if parsedSeconds is not None:
                    values['printTimeSec'] = str(parsedSeconds)

        # ; total layer number: 140
        layerMatch = re.search(r';\s*total layer number:\s*(\d+)', gcodeText, re.IGNORECASE)
        if layerMatch:
            values['totalLayers'] = layerMatch.group(1)

        # Fallback: ; total layers count = 127
        if 'totalLayers' not in values:
            layerMatch2 = re.search(r';\s*total layers count\s*=\s*(\d+)', gcodeText, re.IGNORECASE)
            if layerMatch2:
                values['totalLayers'] = layerMatch2.group(1)

        # ; model label id: 840
        objectsMatch = re.search(r';\s*model label id:\s*([0-9,]+)', gcodeText, re.IGNORECASE)
        if objectsMatch:
            ids = [segment for segment in objectsMatch.group(1).split(',') if segment.strip()]
            values['objectsOnPlate'] = str(len(ids))

        # ; max_z_height: 28.00
        heightMatch = re.search(r';\s*max_z_height:\s*([0-9.]+)', gcodeText, re.IGNORECASE)
        if heightMatch:
            values['maxZHeight'] = heightMatch.group(1)

        # === Try PrusaSlicer-style format first (Orca uses this at the end of file) ===
        # ; filament used [mm] = 51212.00, 4221.24
        # ; filament used [cm3] = 123.18, 10.15
        # ; filament used [g] = 152.74, 12.59
        weightMatch = re.search(
            r';\s*filament used \[g\]\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )
        lengthMatch = re.search(
            r';\s*filament used \[mm\]\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )
        volumeMatch = re.search(
            r';\s*filament used \[cm3\]\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )

        # If not found, try Bambu-compatible format
        if not weightMatch:
            weightMatch = re.search(
                r';\s*total filament weight \[g\]\s*[=:]\s*([0-9.,]+)',
                gcodeText,
                re.IGNORECASE
            )
        if not lengthMatch:
            lengthMatch = re.search(
                r';\s*total filament length \[mm\]\s*[=:]\s*([0-9.,]+)',
                gcodeText,
                re.IGNORECASE
            )
        if not volumeMatch:
            volumeMatch = re.search(
                r';\s*total filament volume \[cm\^3\]\s*[=:]\s*([0-9.,]+)',
                gcodeText,
                re.IGNORECASE
            )

        # Pre-parse printer model for amsIndex/toolIndex selection
        printerModelMatch = re.search(r';\s*printer_model\s*=\s*([^\n;]+)', gcodeText, re.IGNORECASE)
        if printerModelMatch:
            values['printer_model'] = printerModelMatch.group(1).strip()


        weights = []
        if weightMatch:
            # Parse all weights, but filter out unused filaments (< 0.01g)
            all_weights = [float(piece.strip()) for piece in weightMatch.group(1).split(',') if piece.strip()]
            weights = [w for w in all_weights if w > 0.01]
            values['filamentWeights'] = weights
            values['filamentUsedGrams'] = str(sum(weights)) if weights else '0'

        # Build filament analysis
        analysis: List[Dict[str, Any]] = []
        if weightMatch:
            # Parse ALL values to get correct indices
            all_weights = [float(piece.strip()) for piece in weightMatch.group(1).split(',') if piece.strip()]
            all_lengths = [float(piece.strip()) for piece in lengthMatch.group(1).split(',') if piece.strip()] if lengthMatch else []
            all_volumes = [float(piece.strip()) for piece in volumeMatch.group(1).split(',') if piece.strip()] if volumeMatch else []

            isBambu = 'bambu' in values.get('printer_model', '').lower()
            
            # Only include filaments with weight > 0.01g
            for index, weight in enumerate(all_weights):
                if weight > 0.01:
                    item = {
                        'lengthMm': all_lengths[index] if index < len(all_lengths) else None,
                        'volumeCm3': all_volumes[index] if index < len(all_volumes) else None,
                        'weightG': weight,
                        'filamentType': filamentTypes[index] if index < len(filamentTypes) else None,
                        'filamentColor': filamentColors[index] if index < len(filamentColors) else None,
                        'amsIndex': index,
                        'toolIndex': index,
                    }
                    analysis.append(item)



        elif lengthMatch:
            # If no weight but we have length, try to calculate weight
            all_lengths = [float(piece.strip()) for piece in lengthMatch.group(1).split(',') if piece.strip()]
            all_volumes = [float(piece.strip()) for piece in volumeMatch.group(1).split(',') if piece.strip()] if volumeMatch else []

            # Extract density and diameter from config block
            densityMatch = re.search(r';\s*filament_density[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)
            diameterMatch = re.search(r';\s*filament_diameter[=:]\s*([0-9.,]+)', gcodeText, re.IGNORECASE)

            if densityMatch and diameterMatch:
                densities = [float(d.strip()) for d in densityMatch.group(1).split(',') if d.strip()]
                diameters = [float(d.strip()) for d in diameterMatch.group(1).split(',') if d.strip()]

                for index, length in enumerate(all_lengths):
                    # Skip if length is negligible (< 10mm)
                    if length < 10:
                        continue

                    density = densities[index] if index < len(densities) else densities[0] if densities else 1.24
                    diameter = diameters[index] if index < len(diameters) else diameters[0] if diameters else 1.75

                    # Calculate weight: weight = length * cross_section_area * density
                    # cross_section_area = π * (diameter/2)^2
                    volumeMm3 = length * math.pi * (diameter / 2) ** 2
                    volumeCm3 = volumeMm3 / 1000
                    weight = volumeCm3 * density

                    if weight > 0.01:
                        weights.append(weight)
                        item = {
                            'lengthMm': length,
                            'volumeCm3': all_volumes[index] if index < len(all_volumes) else volumeCm3,
                            'weightG': weight,
                            'filamentType': filamentTypes[index] if index < len(filamentTypes) else None,
                            'filamentColor': filamentColors[index] if index < len(filamentColors) else None,
                            'amsIndex': index,
                            'toolIndex': index,
                        }
                        analysis.append(item)




                if weights:
                    values['filamentWeights'] = weights
                    values['filamentUsedGrams'] = f"{sum(weights):.2f}"

            # Add tools/usedTools for parity
            values['tools'] = analysis
            values['usedTools'] = [a for a in analysis if a.get('weightG', 0) > 0.01]
            values['usedToolIndices'] = [a['toolIndex'] for a in values['usedTools']]

        values['filamentAnalysis'] = analysis


        # === Parse filament cost ===
        # ; filament cost = 3.05, 0.25
        costMatch = re.search(
            r';\s*filament cost\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )
        if costMatch:
            costs = [float(piece.strip()) for piece in costMatch.group(1).split(',') if piece.strip()]
            if costs:
                values['filamentCost'] = f"{sum(costs):.2f}"
                values['filamentCosts'] = costs

        # === Parse config block values ===
        # Look for config values that might be useful
        configPatterns = {
            'enable_support': r';\s*enable_support\s*=\s*(\d+)',
            'filament_type': r';\s*filament_type\s*=\s*([^\n]+)',
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

        # === Extract thumbnails from G-code comments ===
        # Format: ; thumbnail begin WxH SIZE
        #         ; base64data...
        #         ; thumbnail end
        thumbnails = _extractThumbnailsFromGcode(gcodeText)
        if thumbnails:
            values['thumbnails'] = thumbnails
            # Use the largest thumbnail as the main plate image
            largestThumb = max(thumbnails, key=lambda t: t.get('width', 0) * t.get('height', 0))
            values['plateImageBase64'] = largestThumb.get('data', '')

        # === Toolchanger / Multi-extruder support ===
        # Detect gcode_flavor (Klipper, Marlin, etc.)
        gcodeFlavorMatch = re.search(r';\s*gcode_flavor\s*=\s*(\w+)', gcodeText, re.IGNORECASE)
        if gcodeFlavorMatch:
            values['gcode_flavor'] = gcodeFlavorMatch.group(1).strip()

        # Count extruders used (from filament arrays or T commands)
        extruderColorsMatch = re.search(r';\s*extruder_colour\s*=\s*([^\n]+)', gcodeText, re.IGNORECASE)
        if extruderColorsMatch:
            colors = [c.strip() for c in extruderColorsMatch.group(1).split(';') if c.strip()]
            values['extruderCount'] = str(len(colors))
            values['extruderColors'] = colors

        # Count tool changes for toolchangers (Tx commands where x is 0-9)
        toolChangePattern = re.compile(r'^T(\d+)\s*$', re.MULTILINE)
        toolChanges = toolChangePattern.findall(gcodeText)
        if toolChanges:
            # Count unique tools used
            uniqueTools = set(toolChanges)
            values['toolsUsed'] = sorted([int(t) for t in uniqueTools])
            # Count total tool change operations (excluding initial tool selection)
            toolChangeCount = len(toolChanges) - 1 if len(toolChanges) > 1 else 0
            if toolChangeCount > 0:
                values['toolChanges'] = str(toolChangeCount)

        # Extract bed temperature
        bedTempMatch = re.search(r';\s*(?:hot_plate_temp|bed_temperature)\s*=\s*(\d+)', gcodeText, re.IGNORECASE)
        if bedTempMatch:
            values['buildPlateTemperature'] = bedTempMatch.group(1)

        # Extract nozzle temperature
        nozzleTempMatch = re.search(r';\s*nozzle_temperature\s*=\s*(\d+)', gcodeText, re.IGNORECASE)
        if nozzleTempMatch:
            values['hotendTemperature'] = nozzleTempMatch.group(1)

        # === Set default values ===
        values.setdefault('slicerType', 'OrcaSlicer')
        values.setdefault('estimatedPowerConsumptionWh', '0')
        values.setdefault('buildPlateTemperature', '0')
        values.setdefault('hotendTemperature', '0')
        values.setdefault('objects', [])
        values.setdefault('orderedObjects', [])

        meta: Dict[str, Any] = {'slicer': 'orca'}
        if values.get('gcode_flavor', '').lower() == 'klipper':
            meta['isKlipper'] = True
        if values.get('toolsUsed'):
            meta['isToolchanger'] = len(values['toolsUsed']) > 1

        return ParsedValues(fieldValues=values, meta=meta)


def _extractThumbnailsFromGcode(gcodeText: str) -> List[Dict[str, Any]]:
    """Extract thumbnails embedded in G-code comments.

    Supports both OrcaSlicer/PrusaSlicer format:
    ; thumbnail begin WxH SIZE
    ; base64data...
    ; thumbnail end

    And THUMBNAIL_BLOCK format:
    ; THUMBNAIL_BLOCK_START
    ; thumbnail begin WxH SIZE
    ; base64data...
    ; thumbnail end
    ; THUMBNAIL_BLOCK_END
    """
    thumbnails: List[Dict[str, Any]] = []

    # Pattern to match thumbnail blocks
    # Matches: ; thumbnail begin 300x300 7516
    thumbnailPattern = re.compile(
        r';\s*thumbnail begin\s+(\d+)x(\d+)\s+(\d+)\s*\n(.*?)\n;\s*thumbnail end',
        re.DOTALL | re.IGNORECASE
    )

    for match in thumbnailPattern.finditer(gcodeText):
        width = int(match.group(1))
        height = int(match.group(2))
        expectedSize = int(match.group(3))
        rawData = match.group(4)

        # Clean up the base64 data - remove comment prefixes and whitespace
        lines = rawData.split('\n')
        base64Lines = []
        for line in lines:
            # Remove leading semicolon and whitespace
            cleanLine = line.lstrip('; \t')
            if cleanLine:
                base64Lines.append(cleanLine)

        base64Data = ''.join(base64Lines)

        # Validate base64 data
        try:
            # Try to decode to verify it's valid base64
            decoded = base64.b64decode(base64Data)
            # Check if it looks like a PNG (starts with PNG magic bytes)
            isPng = decoded[:8] == b'\x89PNG\r\n\x1a\n'
            thumbnails.append({
                'width': width,
                'height': height,
                'size': len(decoded),
                'format': 'png' if isPng else 'unknown',
                'data': base64Data,
            })
        except Exception:
            # If decoding fails, still include it but mark as potentially invalid
            thumbnails.append({
                'width': width,
                'height': height,
                'expectedSize': expectedSize,
                'format': 'unknown',
                'data': base64Data,
                'valid': False,
            })

    return thumbnails
