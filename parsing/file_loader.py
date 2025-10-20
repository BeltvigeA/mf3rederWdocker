from __future__ import annotations

import io
import zipfile
from typing import Dict, List, Literal, NamedTuple


class GCodeSource(NamedTuple):
    lines: List[str]
    headLines: List[str]
    attachments: Dict[str, bytes]
    containerType: Literal['gcode', '3mf']
    fileName: str | None


def normalizeText(rawBytes: bytes) -> List[str]:
    text = rawBytes.decode('utf-8', errors='ignore')
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.split('\n')


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
    with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
        gcodePaths = [name for name in archive.namelist() if name.lower().endswith('.gcode')]
        preferredPaths = [path for path in gcodePaths if path.lower().startswith('metadata/')]
        targetPath = preferredPaths[0] if preferredPaths else (gcodePaths[0] if gcodePaths else None)
        if not targetPath:
            raise ValueError('No G-code found in archive')
        gcodeBytes = archive.read(targetPath)
        for name in archive.namelist():
            if name == targetPath:
                continue
            try:
                attachments[name] = archive.read(name)
            except KeyError:
                continue
    lines = normalizeText(gcodeBytes)
    headLines = lines[:500]
    return GCodeSource(lines=lines, headLines=headLines, attachments=attachments, containerType='3mf', fileName=fileName)


def _loadFromGcode(fileBytes: bytes, fileName: str | None) -> GCodeSource:
    lines = normalizeText(fileBytes)
    headLines = lines[:500]
    return GCodeSource(lines=lines, headLines=headLines, attachments={}, containerType='gcode', fileName=fileName)
