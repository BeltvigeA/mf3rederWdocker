import base64
import zipfile
from fastapi.testclient import TestClient
from app.main import app


def createSampleFile(tmpPath):
    archivePath = tmpPath / "sample.gcode.zip"
    with zipfile.ZipFile(archivePath, "w") as archive:
        archive.writestr("metadata/plate_1.png", b"fake-image")
        gcodeContent = (
            "model printing time: 100\n"
            "total filament weight: 5g\n"
            "enable_support: true\n"
            "filament_type: PLA\n"
            "layer_height: 0.2\n"
            "nozzle_diameter: 0.4\n"
            "sparse_infill_density: 15\n"
            "printer_model: TestPrinter\n"
        )
        archive.writestr("gcode_1.gcode", gcodeContent)
    finalPath = tmpPath / "sample.gcode.3mf"
    archivePath.rename(finalPath)
    return finalPath


def test_processFile(tmp_path):
    tmpPath = tmp_path
    client = TestClient(app)
    samplePath = createSampleFile(tmpPath)
    with open(samplePath, "rb") as fileObject:
        response = client.post("/process", files={"uploadedFile": (samplePath.name, fileObject)})
    assert response.status_code == 200
    payload = response.json()
    assert "image" in payload
    assert base64.b64decode(payload["image"]) == b"fake-image"
    assert payload["data"]["modelPrintingTime"] == "100"
    assert payload["data"]["printerModel"] == "TestPrinter"
