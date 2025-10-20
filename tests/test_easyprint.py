import os
import sys
from pathlib import Path

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from parsing.extractors.base import deriveWeightGFromLength  # noqa: E402
from parsing.extractors.easyprint_gcode import EasyPrintGcodeExtractor  # noqa: E402
from parsing.file_loader import loadInput  # noqa: E402
from parsing.gcode_view import buildGcodeView  # noqa: E402
from parsing.slicer_detect import detectSlicer  # noqa: E402


FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'easyprint_sample.gcode'


def loadFixtureText() -> str:
    return FIXTURE_PATH.read_text(encoding='utf-8')


def buildEasyPrintView(gcodeText: str):
    source = loadInput(gcodeText.encode('utf-8'), 'sample.gcode')
    return buildGcodeView(source)


def test_detect_easyprint_confidence():
    gview = buildEasyPrintView(loadFixtureText())
    guess = detectSlicer(gview)
    assert guess.name == 'easyprint'
    assert guess.confidence >= 0.8
    assert guess.hints.get('prep') == 'easyprint'


def test_easyprint_extraction_core_fields():
    gview = buildEasyPrintView(loadFixtureText())
    extractor = EasyPrintGcodeExtractor()
    parsed = extractor.extract(gview)
    values = parsed.fieldValues

    assert values['printTimeSec'] == '1244'
    assert values['filamentUsedGrams'] == '10.5'
    assert values['objectsOnPlate'] == '2'
    assert values['totalLayers'] == '50'
    assert values['maxZHeight'] == '10'
    assert parsed.meta['slicerBase'] == 'prusaslicer'
    assert parsed.meta['nozzleDiameter'] == pytest.approx(0.4)

    assert len(values['filamentAnalysis']) == 1
    spool = values['filamentAnalysis'][0]
    assert spool['lengthMm'] == pytest.approx(123.45)
    assert spool['volumeCm3'] == pytest.approx(3.456)
    assert spool['weightG'] == pytest.approx(10.5)


def test_easyprint_weight_fallback_from_length():
    originalText = loadFixtureText()
    modifiedText = originalText.replace('; filament used [g] = 10.5\n', '')
    gview = buildEasyPrintView(modifiedText)
    extractor = EasyPrintGcodeExtractor()
    parsed = extractor.extract(gview)
    values = parsed.fieldValues

    expectedWeight = deriveWeightGFromLength(123.45, 1.75, 1.24)
    assert float(values['filamentUsedGrams']) == pytest.approx(expectedWeight, rel=1e-3)
    spool = values['filamentAnalysis'][0]
    assert spool['weightG'] == pytest.approx(expectedWeight, rel=1e-3)
    assert spool['lengthMm'] == pytest.approx(123.45)
