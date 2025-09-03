from fastapi import FastAPI, UploadFile, File, HTTPException
import zipfile
import tempfile
import os
from typing import Dict
import base64
import re
import requests

app = FastAPI()

parameterMap = {
    "modelPrintingTime": "model printing time",
    "totalFilamentWeight": "total filament weight",
    "enableSupport": "enable_support",
    "filamentType": "filament_type",
    "layerHeight": "layer_height",
    "nozzleDiameter": "nozzle_diameter",
    "sparseInfillDensity": "sparse_infill_density",
    "printerModel": "printer_model"
}


def parseGcodeParameters(gcodeText: str) -> Dict[str, str]:
    results = {}
    for camelKey, pattern in parameterMap.items():
        match = re.search(rf"{re.escape(pattern)}\s*[:=]\s*(.+)", gcodeText, re.IGNORECASE)
        if match:
            results[camelKey] = match.group(1).strip()
    return results


@app.post("/process")
async def processFile(file: UploadFile = File(...)):
    if not file.filename.endswith(".gcode.3mf"):
        raise HTTPException(status_code=400, detail="Invalid file extension")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".3mf") as temp3mf:
        contents = await file.read()
        temp3mf.write(contents)

    tempZipPath = temp3mf.name.replace(".3mf", ".zip")
    os.rename(temp3mf.name, tempZipPath)

    results = {}
    plateImageBase64 = None

    try:
        with zipfile.ZipFile(tempZipPath) as zipRef:
            plateNames = [name for name in zipRef.namelist() if "metadata/plate_1" in name]
            if plateNames:
                with zipRef.open(plateNames[0]) as plateFile:
                    plateImageBase64 = base64.b64encode(plateFile.read()).decode("utf-8")

            gcodeNames = [name for name in zipRef.namelist() if "gcode_1" in name]
            if gcodeNames:
                with zipRef.open(gcodeNames[0]) as gcodeFile:
                    gcodeText = gcodeFile.read().decode("utf-8", errors="ignore")
                    results = parseGcodeParameters(gcodeText)
    finally:
        os.remove(tempZipPath)

    base44Status = None
    try:
        base44Response = requests.get("https://base44.com", timeout=5)
        base44Status = base44Response.status_code
    except Exception:
        base44Status = None

    return {
        "plate1Image": plateImageBase64,
        "parameters": results,
        "base44Status": base44Status
    }
