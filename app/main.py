from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import tempfile
import zipfile
import os
import base64
import re
import uvicorn

app = FastAPI()

searchMap = {
    "model printing time": "modelPrintingTime",
    "total filament weight": "totalFilamentWeight",
    "enable_support": "enableSupport",
    "filament_type": "filamentType",
    "layer_height": "layerHeight",
    "nozzle_diameter": "nozzleDiameter",
    "sparse_infill_density": "sparseInfillDensity",
    "printer_model": "printerModel",
}


def extractValues(text):
    values = {}
    lines = text.splitlines()
    for originalKey, camelKey in searchMap.items():
        pattern = re.compile(re.escape(originalKey), re.IGNORECASE)
        for line in lines:
            if pattern.search(line):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    values[camelKey] = parts[1].strip()
                else:
                    values[camelKey] = line.strip()
                break
    return values


@app.post("/process")
async def processFile(uploadedFile: UploadFile = File(...)):
    with tempfile.TemporaryDirectory() as tempDir:
        inputPath = os.path.join(tempDir, uploadedFile.filename)
        with open(inputPath, "wb") as buffer:
            buffer.write(await uploadedFile.read())
        zipPath = inputPath.replace(".3mf", ".zip")
        os.rename(inputPath, zipPath)
        with zipfile.ZipFile(zipPath, "r") as archive:
            plateName = next(
                (name for name in archive.namelist() if name.startswith("metadata/") and "plate_1" in name),
                None,
            )
            imageData = None
            if plateName:
                imageData = archive.read(plateName)
            gcodeName = next((name for name in archive.namelist() if "gcode_1" in name), None)
            gcodeText = ""
            if gcodeName:
                gcodeText = archive.read(gcodeName).decode("utf-8", errors="ignore")
    base64Image = base64.b64encode(imageData).decode("utf-8") if imageData else None
    values = extractValues(gcodeText)
    return JSONResponse({"image": base64Image, "data": values})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
