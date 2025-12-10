from __future__ import annotations

from typing import Dict, Tuple

from .extractors.bambu_gcode import BambuGcodeExtractor
from .extractors.base import ParsedValues
from .extractors.heuristic import HeuristicExtractor
from .extractors.easyprint_gcode import EasyPrintGcodeExtractor
from .extractors.orca_gcode import OrcaGcodeExtractor
from .gcode_view import GCodeView
from .slicer_detect import SlicerGuess


REGISTRY: Dict[Tuple[str, str], object] = {
    ('bambu', 'gcode'): BambuGcodeExtractor(),
    ('bambu', '3mf'): BambuGcodeExtractor(),
    ('orca', 'gcode'): OrcaGcodeExtractor(),
    ('orca', '3mf'): OrcaGcodeExtractor(),
    ('easyprint', 'gcode'): EasyPrintGcodeExtractor(),
    ('easyprint', '3mf'): EasyPrintGcodeExtractor(),
}


def extractParsedValues(gview: GCodeView, guess: SlicerGuess) -> ParsedValues:
    key = (guess.name, gview.containerType)
    extractor = REGISTRY.get(key, HeuristicExtractor())
    return extractor.extract(gview)
