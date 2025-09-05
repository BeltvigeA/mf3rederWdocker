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
            'metadata/plate_1.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8/x8AAwMCAO/a/94AAAAASUVORK5CYII='
            ),
        )
        archive.writestr(
            'gcode_1',
            '; model printing time = 10\n'
            '; total filament weight = 5\n'
            '; enable_support = True\n'
            '; filament_type = PLA\n'
            '; layer_height = 0.2\n'
            '; nozzle_diameter = 0.4\n'
            '; sparse_infill_density = 20\n'
            '; printer_model = TestPrinter\n',
        )
    memoryZip.seek(0)
    return memoryZip.getvalue()


def test_process_file():
    sampleData = buildSample3mf()
    files = {
        'gcode3mf': ('test.gcode.3mf', sampleData, 'application/octet-stream')
    }
    response = client.post('/process', files=files)
    assert response.status_code == 200
    result = response.json()
    assert 'plateImage' in result
    assert result['values']['model printing time'] == '10'


def test_testRequest():
    response = client.get('/testRequest')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
