from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal

from .file_loader import GCodeSource


@dataclass
class GCodeView:
    lines: List[str]
    headLines: List[str]
    attachments: Dict[str, bytes]
    containerType: Literal['gcode', '3mf']
    fileName: str | None
    plateNumber: int = 1  # NEW: Add plate number

    @property
    def text(self) -> str:
        return '\n'.join(self.lines)

    def iterLines(self):
        for line in self.lines:
            yield line


def buildGcodeView(source: GCodeSource) -> GCodeView:
    return GCodeView(
        lines=list(source.lines),
        headLines=list(source.headLines),
        attachments=dict(source.attachments),
        containerType=source.containerType,
        fileName=source.fileName,
        plateNumber=source.plateNumber,  # Pass through plate number
    )
