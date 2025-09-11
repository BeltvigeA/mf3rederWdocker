from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import io
import zipfile
import base64
import re
import math
import xml.etree.ElementTree as ET

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
    'total filament weight [g]',
    'total filament length [mm]',
    'total filament volume [cm^3]',
    'enable_support',
    'filament_type',
    'layer_height',
    'nozzle_diameter',
    'sparse_infill_density',
    'printer_model'
]


def toCamelCase(text: str) -> str:
    parts = text.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])

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
                with archive.open('Metadata/pick_1.png') as pickFile:
                    pickImageBytes = pickFile.read()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='pick_1.png not found') from exc
            try:
                with archive.open('Metadata/top_1.png') as topFile:
                    topImageBytes = topFile.read()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='top_1.png not found') from exc
            try:
                with archive.open('Metadata/plate_1.gcode') as gcodeFile:
                    gcodeContent = gcodeFile.read().decode('utf-8', errors='ignore')
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='plate_1.gcode not found') from exc
            try:
                with archive.open('Metadata/slice_info.config') as sliceFile:
                    sliceContent = sliceFile.read().decode('utf-8', errors='ignore')
            except KeyError as exc:
                raise HTTPException(status_code=404, detail='slice_info.config not found') from exc
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail='Corrupted archive') from exc
    resultValues = {}
    for key in searchKeys:
        pattern = re.compile(rf"{re.escape(key)}\s*=\s*(.*)", re.IGNORECASE)
        match = pattern.search(gcodeContent)
        if match:
            resultValues[key] = match.group(1).strip()

    objectsMatch = re.search(r'model label id:\s*([0-9,]+)', gcodeContent, re.IGNORECASE)
    if objectsMatch:
        ids = [s for s in objectsMatch.group(1).split(',') if s.strip()]
        resultValues['objectsOnPlate'] = str(len(ids))

    timeMatch = re.search(r'model printing time:\s*(\d+)h\s*(\d+)m\s*(\d+)s', gcodeContent, re.IGNORECASE)
    if timeMatch:
        hours, minutes, seconds = map(int, timeMatch.groups())
        resultValues['printTimeSec'] = str(hours * 3600 + minutes * 60 + seconds)

    weightMatch = re.search(r'total filament weight \[g\]\s*:\s*([0-9.,]+)', gcodeContent, re.IGNORECASE)
    lengthMatch = re.search(r'total filament length \[mm\]\s*:\s*([0-9.,]+)', gcodeContent, re.IGNORECASE)
    volumeMatch = re.search(r'total filament volume \[cm\^3\]\s*:\s*([0-9.,]+)', gcodeContent, re.IGNORECASE)
    weights = []
    if weightMatch:
        weights = [float(w) for w in weightMatch.group(1).split(',') if w]
        resultValues['filamentWeights'] = weights
        resultValues['filamentUsedGrams'] = str(sum(weights))
    analysis = []
    if weights:
        lengths = [float(l) for l in lengthMatch.group(1).split(',')] if lengthMatch else []
        volumes = [float(v) for v in volumeMatch.group(1).split(',')] if volumeMatch else []
        for i, w in enumerate(weights):
            item = {'lengthMm': lengths[i] if i < len(lengths) else None,
                    'volumeCm3': volumes[i] if i < len(volumes) else None,
                    'weightG': w}
            analysis.append(item)
    resultValues['filamentAnalysis'] = analysis

    changes = re.findall(r'M620\s+S\d+A', gcodeContent)
    resultValues['filamentChanges'] = str(len(changes))

    purgeLen = 0.0
    for section in re.findall(r';\s*FLUSH_START\s*(.*?)\s*;\s*FLUSH_END', gcodeContent, re.DOTALL | re.IGNORECASE):
        for val in re.findall(r'G1\s+E([-+]?[0-9]*\.?[0-9]+)', section):
            purgeLen += abs(float(val))
    diameterMatch = re.search(r'filament_diameter:\s*([0-9.,]+)', gcodeContent, re.IGNORECASE)
    densityMatch = re.search(r'filament_density:\s*([0-9.,]+)', gcodeContent, re.IGNORECASE)
    if purgeLen and diameterMatch and densityMatch:
        diameter = float(diameterMatch.group(1).split(',')[0])
        density = float(densityMatch.group(1).split(',')[0])
        volumeMm3 = purgeLen * math.pi * (diameter / 2) ** 2
        volumeCm3 = volumeMm3 / 1000
        purgeGrams = volumeCm3 * density
        resultValues['filamentPurgeGrams'] = f"{purgeGrams:.2f}"
    else:
        resultValues['filamentPurgeGrams'] = '0'

    layerMatch = re.search(r'total layer number:\s*(\d+)', gcodeContent, re.IGNORECASE)
    if layerMatch:
        resultValues['totalLayers'] = layerMatch.group(1)

    heightMatch = re.search(r'max_z_height:\s*([0-9.]+)', gcodeContent, re.IGNORECASE)
    if heightMatch:
        resultValues['maxZHeight'] = heightMatch.group(1)

    objects = []
    try:
        root = ET.fromstring(sliceContent)
        for element in root.findall('.//object'):
            obj = {toCamelCase(k): v for k, v in element.attrib.items()}
            objects.append(obj)
    except ET.ParseError:
        objects = []
    resultValues['objects'] = objects

    resultValues.setdefault('slicerType', 'Unknown')
    resultValues.setdefault('estimatedPowerConsumptionWh', '0')
    resultValues.setdefault('buildPlateTemperature', '0')
    resultValues.setdefault('hotendTemperature', '0')

    plateImageBase64 = base64.b64encode(plateImageBytes).decode('utf-8')
    pickImageBase64 = base64.b64encode(pickImageBytes).decode('utf-8')
    topImageBase64 = base64.b64encode(topImageBytes).decode('utf-8')
    return {
        'plateImage': plateImageBase64,
        'pickImage': pickImageBase64,
        'topImage': topImageBase64,
        'values': resultValues,
    }
