from fastapi import FastAPI, UploadFile, File, HTTPException
import io
import zipfile
import base64
import re

apiApp = FastAPI()

searchKeys = {
    'model printing time': 'modelPrintingTime',
    'total filament weight': 'totalFilamentWeight',
    'enable_support': 'enableSupport',
    'filament_type': 'filamentType',
    'layer_height': 'layerHeight',
    'nozzle_diameter': 'nozzleDiameter',
    'sparse_infill_density': 'sparseInfillDensity',
    'printer_model': 'printerModel'
}

@apiApp.post('/process')
async def processFile(gcode3mf: UploadFile = File(...)):
    if not gcode3mf.filename.endswith('.gcode.3mf'):
        raise HTTPException(status_code=400, detail='Invalid file extension')
    fileData = await gcode3mf.read()
    zipBuffer = io.BytesIO(fileData)
    try:
        with zipfile.ZipFile(zipBuffer) as archive:
            try:
                with archive.open('metadata/plate_1.png') as imageFile:
                    plateImageBytes = imageFile.read()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='plate_1 not found') from exc
            try:
                with archive.open('gcode_1') as gcodeFile:
                    gcodeContent = gcodeFile.read().decode('utf-8', errors='ignore')
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='gcode_1 not found') from exc
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail='Corrupted archive') from exc
    resultValues = {}
    for originalKey, camelKey in searchKeys.items():
        pattern = re.compile(rf"{re.escape(originalKey)}\s*=\s*(.*)", re.IGNORECASE)
        match = pattern.search(gcodeContent)
        if match:
            resultValues[camelKey] = match.group(1).strip()
    plateImageBase64 = base64.b64encode(plateImageBytes).decode('utf-8')
    return {'plateImage': plateImageBase64, 'values': resultValues}
