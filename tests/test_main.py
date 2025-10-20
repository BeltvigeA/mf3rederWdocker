import asyncio
import base64
import io
import os
import sys
import zipfile

import pytest
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip('PIL')

from PIL import Image, ImageDraw

from main import apiApp, processFile, testRequest as fetchTestRequest


def encodeImage(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def buildSample3mf():
    memoryZip = io.BytesIO()
    imageSize = (90, 30)
    plateImage = Image.new('RGBA', imageSize, (220, 220, 220, 255))
    topImage = Image.new('RGBA', imageSize, (245, 245, 245, 255))
    pickImage = Image.new('RGBA', imageSize, (0, 0, 0, 0))
    pickDraw = ImageDraw.Draw(pickImage)
    pickDraw.rectangle((5, 5, 30, 25), fill=(255, 70, 70, 255))
    pickDraw.rectangle((35, 5, 60, 25), fill=(140, 140, 140, 255))
    pickDraw.rectangle((65, 5, 85, 25), fill=(10, 10, 10, 255))
    plateImageBytes = encodeImage(plateImage)
    pickImageBytes = encodeImage(pickImage)
    topImageBytes = encodeImage(topImage)
    gcodeText = (
        '; model printing time: 0h 0m 10s; total estimated time: 0h 0m 10s\n'
        '; total filament length [mm] : 10.0,20.0\n'
        '; total filament volume [cm^3] : 1.0,2.0\n'
        '; total filament weight [g] : 1.5,2.5\n'
        '; filament_density: 1.24\n'
        '; filament_diameter: 1.75\n'
        '; model label id: 1,2,3\n'
        'M620 S0A\n'
        'M620 S1A\n'
        '; FLUSH_START\nG1 E10\n; FLUSH_END\n'
        '; total layer number: 5\n'
        '; max_z_height: 10.5\n'
        '; enable_support = True\n'
        '; filament_type = PLA\n'
        '; layer_height = 0.2\n'
        '; nozzle_diameter = 0.4\n'
        '; sparse_infill_density = 20\n'
        '; printer_model = TestPrinter\n'
    )
    with zipfile.ZipFile(memoryZip, 'w') as archive:
        archive.writestr('Metadata/plate_1.png', plateImageBytes)
        archive.writestr('Metadata/pick_1.png', pickImageBytes)
        archive.writestr('Metadata/top_1.png', topImageBytes)
        archive.writestr('Metadata/plate_1.gcode', gcodeText)
        archive.writestr(
            'Metadata/slice_info.config',
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<config><plate>'
            '<object identify_id="101" name="balloonRed" skipped="false" />'
            '<object identify_id="205" name="balloonGray" skipped="false" />'
            '<object identify_id="307" name="balloonBlack" skipped="true" />'
            '</plate></config>',
        )
    memoryZip.seek(0)
    return memoryZip.getvalue(), topImageBytes, gcodeText.encode('utf-8')


def callProcessFile(filename: str, data: bytes):
    uploadFile = UploadFile(file=io.BytesIO(data), filename=filename)
    return asyncio.run(processFile(uploadFile))


def testProcessFileGcode3mf():
    sampleData, originalTopImageBytes, _ = buildSample3mf()
    result = callProcessFile('test.3mf', sampleData)
    assert 'plateImage' in result
    assert 'pickImage' in result
    assert 'topImage' in result
    modifiedTopImageBytes = base64.b64decode(result['topImage'])
    assert modifiedTopImageBytes != originalTopImageBytes
    values = result['values']
    assert values['printTimeSec'] == '10'
    assert values['objectsOnPlate'] == '3'
    assert values['filamentUsedGrams'] == '4.0'
    assert values['filamentWeights'] == [1.5, 2.5]
    assert values['filamentAnalysis'][0]['lengthMm'] == 10.0
    assert values['filamentChanges'] == '2'
    assert values['filamentPurgeGrams'] != '0'
    assert values['totalLayers'] == '5'
    assert values['maxZHeight'] == '10.5'
    assert values['objects'] == [
        {'identifyId': '101', 'name': 'balloonRed', 'skipped': 'false'},
        {'identifyId': '205', 'name': 'balloonGray', 'skipped': 'false'},
        {'identifyId': '307', 'name': 'balloonBlack', 'skipped': 'true'},
    ]
    assert values['orderedObjects'] == [
        {'order': 1, 'identifyId': '101', 'name': 'balloonRed', 'skipped': 'false'},
        {'order': 2, 'identifyId': '205', 'name': 'balloonGray', 'skipped': 'false'},
        {'order': 3, 'identifyId': '307', 'name': 'balloonBlack', 'skipped': 'true'},
    ]


def testProcessFileGcode():
    _, _, gcodeBytes = buildSample3mf()
    result = callProcessFile('test.gcode', gcodeBytes)
    assert 'plateImage' not in result
    assert 'pickImage' not in result
    assert 'topImage' not in result
    values = result['values']
    assert values['printTimeSec'] == '10'
    assert values['objectsOnPlate'] == '3'
    assert values['filamentUsedGrams'] == '4.0'
    assert values['filamentWeights'] == [1.5, 2.5]
    assert values['filamentAnalysis'][0]['lengthMm'] == 10.0
    assert values['orderedObjects'] == []


def testTestRequest():
    response = asyncio.run(fetchTestRequest())
    assert response == {'status': 'ok'}


def testCorsHeaders():
    middlewareClasses = [middleware.cls for middleware in apiApp.user_middleware]
    assert CORSMiddleware in middlewareClasses
