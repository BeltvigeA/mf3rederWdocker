from __future__ import annotations

from typing import Any, Dict, List

from .extractors.base import ParsedValues
from .slicer_detect import SlicerGuess


def _formatNumber(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            if value.is_integer():
                return f"{value:.1f}"
            formatted = f"{value:.6f}".rstrip('0').rstrip('.')
            return formatted if formatted else '0'
        return str(value)
    return str(value)


def normalizeToBambuFields(parsedValues: ParsedValues, slicerGuess: SlicerGuess) -> Dict[str, Any]:
    normalizedValues: Dict[str, Any] = dict(parsedValues.fieldValues)

    def setIfMissing(key: str, value: Any) -> None:
        if key not in normalizedValues and value is not None:
            normalizedValues[key] = value

    printTimeValue = parsedValues.fieldValues.get('printTimeSec')
    totalSeconds: int | None = None
    if isinstance(printTimeValue, str) and printTimeValue.strip():
        try:
            totalSeconds = int(float(printTimeValue))
        except (TypeError, ValueError):
            totalSeconds = None
    elif isinstance(printTimeValue, (int, float)):
        totalSeconds = int(printTimeValue)
    if totalSeconds is not None:
        hours = totalSeconds // 3600
        minutes = (totalSeconds % 3600) // 60
        seconds = totalSeconds % 60
        setIfMissing('model printing time', f'{hours}h {minutes}m {seconds}s')

    filamentWeights = parsedValues.fieldValues.get('filamentWeights')
    weightEntries: List[str] = []
    if isinstance(filamentWeights, list):
        for item in filamentWeights:
            if item is not None and item > 0.01:  # Filter out unused filaments (< 0.01g)
                weightEntries.append(_formatNumber(item))
    filamentUsed = parsedValues.fieldValues.get('filamentUsedGrams')
    if not weightEntries and filamentUsed is not None:
        weightEntries.append(_formatNumber(filamentUsed))
    if weightEntries:
        setIfMissing('total filament weight [g]', ','.join(weightEntries))

    filamentAnalysis = parsedValues.fieldValues.get('filamentAnalysis')
    lengthEntries: List[str] = []
    volumeEntries: List[str] = []
    if isinstance(filamentAnalysis, list):
        for spool in filamentAnalysis:
            if isinstance(spool, dict):
                # Only include filaments with weight > 0.01g
                weightValue = spool.get('weightG')
                if weightValue is None or weightValue <= 0.01:
                    continue

                lengthValue = spool.get('lengthMm')
                if lengthValue is not None:
                    lengthEntries.append(_formatNumber(lengthValue))
                volumeValue = spool.get('volumeCm3')
                if volumeValue is not None:
                    volumeEntries.append(_formatNumber(volumeValue))
    if lengthEntries:
        setIfMissing('total filament length [mm]', ','.join(lengthEntries))
    if volumeEntries:
        setIfMissing('total filament volume [cm^3]', ','.join(volumeEntries))

    metaKeyMap = {
        'printerModel': 'printer_model',
        'nozzleDiameter': 'nozzle_diameter',
        'layerHeight': 'layer_height',
        'filamentDiameter': 'filament_diameter',
        'filamentDensity': 'filament_density',
        'filamentType': 'filament_type',
        'filamentColour': 'filament_colour',
    }
    for metaKey, targetKey in metaKeyMap.items():
        if metaKey in parsedValues.meta:
            metaValue = parsedValues.meta.get(metaKey)
            if metaValue is not None:
                setIfMissing(targetKey, _formatNumber(metaValue))

    setIfMissing('slicerType', 'Unknown')
    setIfMissing('estimatedPowerConsumptionWh', '0')
    setIfMissing('buildPlateTemperature', '0')
    setIfMissing('hotendTemperature', '0')
    setIfMissing('objects', [])
    setIfMissing('orderedObjects', [])

    return normalizedValues
