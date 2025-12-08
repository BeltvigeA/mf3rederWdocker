from __future__ import annotations

import io
import re
import zipfile
from typing import Dict, List, Literal, NamedTuple


class GCodeSource(NamedTuple):
    lines: List[str]
    headLines: List[str]
    attachments: Dict[str, bytes]
    containerType: Literal['gcode', '3mf']
    fileName: str | None
    plateNumber: int = 1  # NEW: Default to 1 for backwards compatibility


def normalizeText(rawBytes: bytes) -> List[str]:
    text = rawBytes.decode('utf-8', errors='ignore')
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.split('\n')


def extractPlateNumber(filepath: str) -> int:
    """
    Extract plate number from filepath.

    Examples:
      - "Metadata/plate_3.gcode" -> 3
      - "plate_1.gcode" -> 1
      - "some_file.gcode" -> 1 (default)
    """
    pattern = re.compile(r'plate_(\d+)\.gcode', re.IGNORECASE)
    match = pattern.search(filepath)

    if match:
        return int(match.group(1))

    # Default to plate 1 if no match
    return 1


def loadInput(fileBytes: bytes, fileName: str | None) -> GCodeSource:
    lowerName = (fileName or '').lower()
    if lowerName.endswith('.3mf') or lowerName.endswith('.gcode.3mf'):
        return _loadFrom3mf(fileBytes, fileName)
    if lowerName.endswith('.gcode'):
        return _loadFromGcode(fileBytes, fileName)
    try:
        return _loadFrom3mf(fileBytes, fileName)
    except zipfile.BadZipFile:
        if not fileName:
            raise ValueError('Unsupported file format')
        return _loadFromGcode(fileBytes, fileName)


def _loadFrom3mf(fileBytes: bytes, fileName: str | None) -> GCodeSource:
    attachments: Dict[str, bytes] = {}
    gcodeBytes: bytes | None = None
    plateNumber = 1  # Default

    with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
        # Get all files in archive
        all_files = archive.namelist()

        # Get all GCODE files
        gcodePaths = [name for name in all_files if name.lower().endswith('.gcode')]

        # Prefer files in metadata/ folder
        preferredPaths = [path for path in gcodePaths if path.lower().startswith('metadata/')]
        targetPath = preferredPaths[0] if preferredPaths else (gcodePaths[0] if gcodePaths else None)

        if not targetPath:
            # Improved error message with file list
            sample_files = ', '.join(all_files[:5]) if all_files else 'no files'
            raise ValueError(
                f'No G-code found in archive. Found {len(all_files)} files: {sample_files}...'
            )

        # Extract plate number from GCODE filename
        plateNumber = extractPlateNumber(targetPath)

        # Read GCODE
        gcodeBytes = archive.read(targetPath)

        # Read all other files into attachments
        for name in archive.namelist():
            if name == targetPath:
                continue
            try:
                attachments[name] = archive.read(name)
            except KeyError:
                continue

    lines = normalizeText(gcodeBytes)
    headLines = lines[:500]

    return GCodeSource(
        lines=lines,
        headLines=headLines,
        attachments=attachments,
        containerType='3mf',
        fileName=fileName,
        plateNumber=plateNumber  # Pass plate number
    )


def _loadFromGcode(fileBytes: bytes, fileName: str | None) -> GCodeSource:
    lines = normalizeText(fileBytes)
    headLines = lines[:500]
    return GCodeSource(
        lines=lines,
        headLines=headLines,
        attachments={},
        containerType='gcode',
        fileName=fileName,
        plateNumber=1  # Default for pure GCODE
    )
