from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from parsing.enrichers.bambu_3mf import enrichBambuAttachments
from parsing.file_loader import loadInput
from parsing.gcode_view import buildGcodeView
from parsing.router import extractParsedValues
from parsing.slicer_detect import detectSlicer
from parsing.valueNormalizer import normalizeToBambuFields

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


@apiApp.post('/process')
async def processFile(gcodeUpload: UploadFile = File(...)):
    fileBytes = await gcodeUpload.read()
    try:
        source = loadInput(fileBytes, gcodeUpload.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    gview = buildGcodeView(source)
    guess = detectSlicer(gview)
    parsedValues = extractParsedValues(gview, guess)
    imagesPayload = {}
    if gview.containerType == '3mf' and guess.name == 'bambu':
        imagesPayload = enrichBambuAttachments(gview, parsedValues)
    responseValues = normalizeToBambuFields(parsedValues, guess)
    return {
        **imagesPayload,
        'values': responseValues,
    }
