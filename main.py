from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import io
import zipfile
import base64
import re

apiApp = FastAPI()

apiApp.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@apiApp.get('/testRequest')
async def testRequest():
    return {'status': 'ok'}

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

@apiApp.post('/process')
async def processFile(gcode3mf: UploadFile = File(...)):
    if not gcode3mf.filename.endswith('.3mf'):
        raise HTTPException(status_code=400, detail='Invalid file extension')
    fileData = await gcode3mf.read()
    zipBuffer = io.BytesIO(fileData)
    try:
        with zipfile.ZipFile(zipBuffer) as archive:
            try:
                with archive.open('Metadata/plate_1.png') as imageFile:
                    plateImageBytes = imageFile.read()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='plate_1.png not found') from exc
            try:
                with archive.open('Metadata/plate_1.gcode') as gcodeFile:
                    gcodeContent = gcodeFile.read().decode('utf-8', errors='ignore')
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='plate_1.gcode not found') from exc
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail='Corrupted archive') from exc
    resultValues = {}
    for key in searchKeys:
        pattern = re.compile(rf"{re.escape(key)}\s*=\s*(.*)", re.IGNORECASE)
        match = pattern.search(gcodeContent)
        if match:
            resultValues[key] = match.group(1).strip()
    plateImageBase64 = base64.b64encode(plateImageBytes).decode('utf-8')
    return {'plateImage': plateImageBase64, 'values': resultValues}
