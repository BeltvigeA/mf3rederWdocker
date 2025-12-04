from __future__ import annotations

import json
import logging
import zipfile
from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    """Process GCODE/3MF file and extract metadata + images."""

    fileName = gcodeUpload.filename
    logRequestReceived('process', fileName)

    fileBytes = await gcodeUpload.read()

    try:
        # Load and parse file (with dynamic plate number detection)
        source = loadInput(fileBytes, fileName)
        gview = buildGcodeView(source)

        # Log plate number
        logMessage(f'🔢 Detected plate number: {gview.plateNumber}')

        # Detect slicer and extract values
        guess = detectSlicer(gview)
        parsedValues = extractParsedValues(gview, guess)

        # Extract images (using dynamic plate number)
        imagesPayload = {}
        if gview.containerType == '3mf' and guess.name == 'bambu':
            imagesPayload = enrichBambuAttachments(gview, parsedValues)

        # Normalize response
        responseValues = normalizeToBambuFields(parsedValues, guess)

        logRequestStatus('process', True, f'Successfully processed {fileName} (plate {gview.plateNumber})')

        return {
            **imagesPayload,
            'plateNumber': gview.plateNumber,  # Include in response
            'values': responseValues,
        }

    except ValueError as exc:
        logRequestStatus('process', False, f'ValueError: {exc}')
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logRequestStatus('process', False, f'HTTP 404 - {exc}')
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException as exc:
        logRequestStatus('process', False, f"HTTP {exc.status_code} - {exc.detail}")
        raise
    except Exception as exc:
        logRequestStatus('process', False, f'Unexpected error: {exc}')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@apiApp.post('/list-plates')
async def list_plates(gcodeUpload: UploadFile = File(...)):
    """
    List all plates in a 3MF file with metadata and images
    """
    logRequestReceived('list-plates', gcodeUpload.filename)
    try:
        # Read file
        fileBytes = await gcodeUpload.read()
        fileName = gcodeUpload.filename

        # Import plate scanner module
        from plate_scanner import scan_plates

        # Scan for plates
        result = scan_plates(fileBytes, fileName)

        logRequestStatus('list-plates', True, f'Found {result.get("totalPlates", 0)} plates in {fileName}')
        return JSONResponse(content=result)

    except zipfile.BadZipFile:
        logRequestStatus('list-plates', False, 'Invalid 3MF file (not a valid ZIP archive)')
        return JSONResponse(
            content={
                'success': False,
                'error': 'Invalid 3MF file (not a valid ZIP archive)'
            },
            status_code=400
        )
    except Exception as e:
        logRequestStatus('list-plates', False, f'Error: {str(e)}')
        return JSONResponse(
            content={
                'success': False,
                'error': str(e)
            },
            status_code=500
        )


@apiApp.post('/split-plates')
async def split_plates(
    gcodeUpload: UploadFile = File(...),
    selectedPlates: str = Form(...),
    originalFilename: str = Form(None)
):
    """
    Split a 3MF file into separate files for each selected plate
    """
    fileName = originalFilename or gcodeUpload.filename
    logRequestReceived('split-plates', f'{fileName} - plates: {selectedPlates}')
    try:
        # Read file
        fileBytes = await gcodeUpload.read()

        # Parse selected plates
        plates = json.loads(selectedPlates)

        if not isinstance(plates, list) or len(plates) == 0:
            logRequestStatus('split-plates', False, 'selectedPlates must be a non-empty array')
            return JSONResponse(
                content={
                    'success': False,
                    'error': 'selectedPlates must be a non-empty array'
                },
                status_code=400
            )

        # Import plate splitter
        from plate_splitter import split_3mf_by_plates

        # Split the file
        result = split_3mf_by_plates(fileBytes, plates, fileName)

        logRequestStatus('split-plates', True, f'Split {fileName} into {len(plates)} files')
        return JSONResponse(content=result)

    except json.JSONDecodeError:
        logRequestStatus('split-plates', False, 'Invalid JSON in selectedPlates parameter')
        return JSONResponse(
            content={
                'success': False,
                'error': 'Invalid JSON in selectedPlates parameter'
            },
            status_code=400
        )
    except zipfile.BadZipFile:
        logRequestStatus('split-plates', False, 'Invalid 3MF file (not a valid ZIP archive)')
        return JSONResponse(
            content={
                'success': False,
                'error': 'Invalid 3MF file (not a valid ZIP archive)'
            },
            status_code=400
        )
    except Exception as e:
        logRequestStatus('split-plates', False, f'Error: {str(e)}')
        return JSONResponse(
            content={
                'success': False,
                'error': str(e)
            },
            status_code=500
        )
