from __future__ import annotations

import io
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

from parsing.enrichers.bambu_3mf import enrichBambuAttachments, extractObjectsFromPlateJson
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
        if gview.containerType == '3mf' and guess.name in ('bambu', 'orca'):
            imagesPayload = enrichBambuAttachments(gview, parsedValues)

        # Extract objects from plate_X.json (for 3MF files)
        objectsPayload = {}
        if gview.containerType == '3mf':
            objectsPayload = extractObjectsFromPlateJson(gview)
            # Update parsedValues with objects data if found
            if objectsPayload.get('objects'):
                parsedValues.fieldValues['objects'] = objectsPayload['objects']
                parsedValues.fieldValues['objectsOnPlate'] = str(objectsPayload['objectsOnPlate'])

        # Normalize response
        responseValues = normalizeToBambuFields(parsedValues, guess)

        logRequestStatus('process', True, f'Successfully processed {fileName} (plate {gview.plateNumber})')

        return {
            **imagesPayload,
            'plateNumber': gview.plateNumber,  # Include in response
            'values': responseValues,
        }

    except ValueError as exc:
        error_msg = str(exc)

        # Check if it's a "No G-code found" error
        if 'No G-code found' in error_msg or 'No GCODE' in error_msg:
            logMessage(f'❌ No GCODE found in {fileName}')

            # Try to list files in archive for debugging
            files_in_archive = []
            try:
                with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
                    files_in_archive = archive.namelist()
                    logMessage(f'📂 Files in archive: {files_in_archive[:10]}')
            except Exception as zip_error:
                logMessage(f'⚠️ Could not read archive: {zip_error}')

            return JSONResponse(
                content={
                    'success': False,
                    'error': 'No GCODE file found in 3MF archive',
                    'details': 'The uploaded 3MF file does not contain a GCODE file. Please ensure your 3MF file includes sliced GCODE data (usually in Metadata/plate_X.gcode).',
                    'fileName': fileName,
                    'filesFound': files_in_archive[:20] if files_in_archive else []
                },
                status_code=400
            )

        # Other ValueError - log and return as 400
        logRequestStatus('process', False, f'ValueError: {error_msg}')
        raise HTTPException(status_code=400, detail=error_msg) from exc

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
    fileName = gcodeUpload.filename
    logRequestReceived('list-plates', fileName)

    fileBytes = await gcodeUpload.read()

    try:
        # Import plate scanner module
        from plate_scanner import scan_plates

        # Scan for plates
        result = scan_plates(fileBytes, fileName)

        logRequestStatus('list-plates', True, f'Found {result.get("totalPlates", 0)} plates in {fileName}')
        return JSONResponse(content=result)

    except ValueError as exc:
        error_msg = str(exc)

        # Check if it's a "No G-code found" error
        if 'No G-code found' in error_msg or 'No GCODE' in error_msg:
            logMessage(f'❌ No GCODE found in {fileName}')

            # List files in archive
            files_in_archive = []
            try:
                with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
                    files_in_archive = archive.namelist()
                    logMessage(f'📂 Files in archive: {files_in_archive[:10]}')
            except Exception as zip_error:
                logMessage(f'⚠️ Could not read archive: {zip_error}')

            return JSONResponse(
                content={
                    'success': False,
                    'error': 'No GCODE file found in 3MF archive',
                    'details': 'This 3MF file appears to be a 3D model file without sliced GCODE. Please slice the file in your slicer software (e.g., Bambu Studio, PrusaSlicer) before uploading.',
                    'fileName': fileName,
                    'filesFound': files_in_archive[:20] if files_in_archive else [],
                    'totalPlates': 0,
                    'plates': []
                },
                status_code=400
            )

        # Other ValueError
        logRequestStatus('list-plates', False, f'ValueError: {error_msg}')
        return JSONResponse(
            content={
                'success': False,
                'error': error_msg
            },
            status_code=400
        )

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

    fileBytes = await gcodeUpload.read()

    try:
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

    except ValueError as exc:
        error_msg = str(exc)

        # Check if it's a "No G-code found" error
        if 'No G-code found' in error_msg or 'No GCODE' in error_msg:
            logMessage(f'❌ No GCODE found in {fileName}')

            # List files in archive
            files_in_archive = []
            try:
                with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
                    files_in_archive = archive.namelist()
                    logMessage(f'📂 Files in archive: {files_in_archive[:10]}')
            except Exception as zip_error:
                logMessage(f'⚠️ Could not read archive: {zip_error}')

            return JSONResponse(
                content={
                    'success': False,
                    'error': 'No GCODE file found in 3MF archive',
                    'details': 'Cannot split file: This 3MF file does not contain any GCODE data. Please slice the file first.',
                    'fileName': fileName,
                    'filesFound': files_in_archive[:20] if files_in_archive else []
                },
                status_code=400
            )

        # Other ValueError
        logRequestStatus('split-plates', False, f'ValueError: {error_msg}')
        return JSONResponse(
            content={
                'success': False,
                'error': error_msg
            },
            status_code=400
        )

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


@apiApp.post('/analyze-plate')
async def analyze_plate(plateImage: UploadFile = File(...)):
    """
    Analyze a 3D print build plate image for potential interference objects.
    
    Takes an image of the build plate and uses AI (Gemini Vision) to detect if there are
    any objects that could interfere with the next print.
    
    Returns:
        JSON with analysis results including:
        - hasInterference: bool
        - confidenceScore: float
        - summary: str
        - detectedObjects: list
        - recommendation: str
    """
    fileName = plateImage.filename
    logRequestReceived('analyze-plate', fileName)
    
    # Validate file type
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'application/octet-stream']
    content_type = plateImage.content_type or ''
    
    # If content type is octet-stream, try to determine from filename
    if content_type == 'application/octet-stream' and fileName:
        file_ext = fileName.lower().split('.')[-1]
        if file_ext == 'png':
            content_type = 'image/png'
        elif file_ext in ['jpg', 'jpeg']:
            content_type = 'image/jpeg'
        elif file_ext == 'webp':
            content_type = 'image/webp'
        else:
            logRequestStatus('analyze-plate', False, f'Unknown file extension: {file_ext}')
            return JSONResponse(
                content={
                    'success': False,
                    'error': f'Unknown file extension: {file_ext}. Allowed: .png, .jpg, .jpeg, .webp'
                },
                status_code=400
            )
    
    # Validate content type
    valid_image_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp']
    if content_type not in valid_image_types:
        logRequestStatus('analyze-plate', False, f'Invalid content type: {content_type}')
        return JSONResponse(
            content={
                'success': False,
                'error': f'Invalid file type: {content_type}. Allowed types: PNG, JPEG, WebP'
            },
            status_code=400
        )
    
    imageBytes = await plateImage.read()
    
    # Validate file is not empty
    if len(imageBytes) == 0:
        logRequestStatus('analyze-plate', False, 'Empty file uploaded')
        return JSONResponse(
            content={
                'success': False,
                'error': 'Empty file uploaded'
            },
            status_code=400
        )
    
    try:
        from plate_analysis import analyze_plate_image, to_dict
        
        # Map content type to format
        format_map = {
            'image/png': 'png',
            'image/jpeg': 'jpeg',
            'image/jpg': 'jpeg',
            'image/webp': 'webp'
        }
        image_format = format_map.get(content_type, 'png')
        
        result = analyze_plate_image(imageBytes, image_format)
        
        logRequestStatus('analyze-plate', True, 
                        f'Analyzed {fileName}: interference={result.hasInterference}, '
                        f'confidence={result.confidenceScore:.2f}')
        
        return JSONResponse(content={
            'success': True,
            **to_dict(result)
        })
        
    except ValueError as exc:
        logRequestStatus('analyze-plate', False, f'ValueError: {exc}')
        return JSONResponse(
            content={'success': False, 'error': str(exc)},
            status_code=400
        )
    except RuntimeError as exc:
        logRequestStatus('analyze-plate', False, f'RuntimeError: {exc}')
        return JSONResponse(
            content={'success': False, 'error': str(exc)},
            status_code=500
        )
    except Exception as exc:
        logRequestStatus('analyze-plate', False, f'Unexpected error: {exc}')
        return JSONResponse(
            content={'success': False, 'error': f'Unexpected error: {exc}'},
            status_code=500
        )


@apiApp.post('/check-print-completion')
async def check_print_completion(printImage: UploadFile = File(...)):
    """
    Analyze an image to determine if a 3D print job is complete.

    Takes an image of a 3D print (from a camera or photo) and uses AI (Gemini Vision)
    to analyze whether the print appears complete, in progress, or failed.

    Returns:
        JSON with analysis results including:
        - isComplete: bool
        - confidenceScore: float
        - printStatus: str ("complete", "in_progress", "failed", "unknown")
        - summary: str
        - detectedIssues: list
        - recommendation: str
        - estimatedProgress: int (0-100) if in progress
    """
    fileName = printImage.filename
    logRequestReceived('check-print-completion', fileName)

    # Validate file type
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'application/octet-stream']
    content_type = printImage.content_type or ''

    # If content type is octet-stream, try to determine from filename
    if content_type == 'application/octet-stream' and fileName:
        file_ext = fileName.lower().split('.')[-1]
        if file_ext == 'png':
            content_type = 'image/png'
        elif file_ext in ['jpg', 'jpeg']:
            content_type = 'image/jpeg'
        elif file_ext == 'webp':
            content_type = 'image/webp'
        else:
            logRequestStatus('check-print-completion', False, f'Unknown file extension: {file_ext}')
            return JSONResponse(
                content={
                    'success': False,
                    'error': f'Unknown file extension: {file_ext}. Allowed: .png, .jpg, .jpeg, .webp'
                },
                status_code=400
            )

    # Validate content type
    valid_image_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp']
    if content_type not in valid_image_types:
        logRequestStatus('check-print-completion', False, f'Invalid content type: {content_type}')
        return JSONResponse(
            content={
                'success': False,
                'error': f'Invalid file type: {content_type}. Allowed types: PNG, JPEG, WebP'
            },
            status_code=400
        )

    imageBytes = await printImage.read()

    # Validate file is not empty
    if len(imageBytes) == 0:
        logRequestStatus('check-print-completion', False, 'Empty file uploaded')
        return JSONResponse(
            content={
                'success': False,
                'error': 'Empty file uploaded'
            },
            status_code=400
        )

    try:
        from print_completion_analysis import analyze_print_completion, to_dict

        # Map content type to format
        format_map = {
            'image/png': 'png',
            'image/jpeg': 'jpeg',
            'image/jpg': 'jpeg',
            'image/webp': 'webp'
        }
        image_format = format_map.get(content_type, 'png')

        result = analyze_print_completion(imageBytes, image_format)

        logRequestStatus('check-print-completion', True,
                        f'Analyzed {fileName}: complete={result.isComplete}, '
                        f'status={result.printStatus}, confidence={result.confidenceScore:.2f}')

        return JSONResponse(content={
            'success': True,
            **to_dict(result)
        })

    except ValueError as exc:
        logRequestStatus('check-print-completion', False, f'ValueError: {exc}')
        return JSONResponse(
            content={'success': False, 'error': str(exc)},
            status_code=400
        )
    except RuntimeError as exc:
        logRequestStatus('check-print-completion', False, f'RuntimeError: {exc}')
        return JSONResponse(
            content={'success': False, 'error': str(exc)},
            status_code=500
        )
    except Exception as exc:
        logRequestStatus('check-print-completion', False, f'Unexpected error: {exc}')
        return JSONResponse(
            content={'success': False, 'error': f'Unexpected error: {exc}'},
            status_code=500
        )

