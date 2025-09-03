from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile
import zipfile
import base64
from typing import Dict

app = FastAPI()

searchKeys = [
    'model printing time',
    'total filament weight',
    'enable_support',
    'filament_type',
    'layer_height',
    'nozzle_diameter',
    'sparse_infill_density',
    'printer_model'
]


@app.post("/upload")
async def uploadFile(gcodeFile: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmpFile:
        tmpFile.write(await gcodeFile.read())
        tempZipPath = tmpFile.name

    plateImageBase64 = None
    gcodeInfo: Dict[str, str] = {}

    with zipfile.ZipFile(tempZipPath, 'r') as zipRef:
        for member in zipRef.namelist():
            lowerName = member.lower()
            if lowerName.endswith('metadata/plate_1.png') or lowerName.endswith('metadata/plate_1.jpg'):
                plateImageBase64 = base64.b64encode(zipRef.read(member)).decode('utf-8')
            if lowerName.endswith('gcode_1') or lowerName.endswith('gcode/gcode_1.gcode'):
                lines = zipRef.read(member).decode('utf-8', errors='ignore').splitlines()
                for line in lines:
                    for key in searchKeys:
                        if key in line:
                            parts = line.split('=')
                            if len(parts) > 1:
                                gcodeInfo[key] = parts[1].strip()

    return JSONResponse({
        'plateImage': plateImageBase64,
        'gcodeInfo': gcodeInfo
    })
