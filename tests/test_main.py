from fastapi.testclient import TestClient
import io
import zipfile
import base64

from main import apiApp

client = TestClient(apiApp)


def buildSample3mf():
    memoryZip = io.BytesIO()
    with zipfile.ZipFile(memoryZip, 'w') as archive:
        archive.writestr(
            'Metadata/plate_1.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8/x8AAwMCAO/a/94AAAAASUVORK5CYII='
            ),
        )
        archive.writestr(
            'Metadata/pick_1.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8/x8AAwMCAO/a/94AAAAASUVORK5CYII='
            ),
        )
        archive.writestr(
            'Metadata/top_1.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8/x8AAwMCAO/a/94AAAAASUVORK5CYII='
            ),
        )
        archive.writestr(
            'Metadata/plate_1.gcode',
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
            '; printer_model = TestPrinter\n',
        )
        archive.writestr(
            'Metadata/slice_info.config',
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<config><plate>'
            '<object identify_id="1" name="test1" skipped="false" />'
            '<object identify_id="2" name="test2" skipped="true" />'
            '</plate></config>',
        )
    memoryZip.seek(0)
    return memoryZip.getvalue()


def testProcessFileGcode3mf():
    sampleData = buildSample3mf()
    files = {'gcode3mf': ('test.gcode.3mf', sampleData, 'application/octet-stream')}
    response = client.post('/process', files=files)
    assert response.status_code == 200
    result = response.json()
    assert 'plateImage' in result
    assert 'pickImage' in result
    assert 'topImage' in result
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
        {'identifyId': '1', 'name': 'test1', 'skipped': 'false'},
        {'identifyId': '2', 'name': 'test2', 'skipped': 'true'},
    ]


def testProcessFile3mf():
    sampleData = buildSample3mf()
    files = {'gcode3mf': ('test.3mf', sampleData, 'application/octet-stream')}
    response = client.post('/process', files=files)
    assert response.status_code == 200
    result = response.json()
    assert 'pickImage' in result
    assert 'topImage' in result
    assert result['values']['printer_model'] == 'TestPrinter'


def testTestRequest():
    response = client.get('/testRequest')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def testCorsHeaders():
    response = client.options(
        '/testRequest',
        headers={
            'origin': 'http://example.com',
            'access-control-request-method': 'GET',
        },
    )
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == '*'
