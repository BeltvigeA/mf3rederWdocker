from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from google.cloud import logging as cloudLogging
except ImportError:  # pragma: no cover - optional dependency during local dev
    cloudLogging = None

if TYPE_CHECKING:
    from google.cloud.logging_v2.logger import Logger as CloudLogger

from parsing.enrichers.bambu_3mf import enrichBambuAttachments
from parsing.file_loader import loadInput
from parsing.gcode_view import buildGcodeView
from parsing.router import extractParsedValues
from parsing.slicer_detect import detectSlicer
from parsing.valueNormalizer import normalizeToBambuFields

def buildCloudLogger() -> Optional['CloudLogger']:
    if cloudLogging is None:
        return None
    try:
        client = cloudLogging.Client()
        return client.logger("gcode-service")
    except Exception:
        return None


def logMessage(message: str) -> None:
    if requestLogger is not None:
        requestLogger.log_text(message)
    fallbackLogger.info(message)


def logRequestReceived(endpointName: str, detail: Optional[str] = None) -> None:
    detailSuffix = f" - {detail}" if detail else ""
    logMessage(f"📥 Incoming request for {endpointName}{detailSuffix}")


def logRequestStatus(endpointName: str, isSuccess: bool, detail: Optional[str] = None) -> None:
    emoji = "✅" if isSuccess else "❌"
    detailSuffix = f" - {detail}" if detail else ""
    logMessage(f"{emoji} {endpointName}{detailSuffix}")


fallbackLogger = logging.getLogger("gcode-service")
if not fallbackLogger.handlers:
    logging.basicConfig(level=logging.INFO)

requestLogger = buildCloudLogger()

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
    logRequestReceived('testRequest')
    logRequestStatus('testRequest', True, 'Health check response delivered')
    return {'status': 'ok'}


@apiApp.post('/process')
async def processFile(gcodeUpload: UploadFile = File(...)):
    logRequestReceived('process', gcodeUpload.filename)
    try:
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
    except HTTPException as exc:
        logRequestStatus('process', False, f"HTTP {exc.status_code} - {exc.detail}")
        raise
    except Exception as exc:
        logRequestStatus('process', False, f'Unexpected error: {exc}')
        raise

    logRequestStatus('process', True, f'Successfully processed {gcodeUpload.filename}')
    return {
        **imagesPayload,
        'values': responseValues,
    }
