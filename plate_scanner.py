"""
Plate Scanner Module
Scans 3MF files for all available plates and extracts metadata
"""

import zipfile
import io
import base64
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


def sanitize_plate_name(name: str) -> str:
    """
    Sanitize plate name by replacing '-' and '_' with spaces.

    Args:
        name: Original plate name

    Returns:
        Sanitized plate name with '-' and '_' replaced by spaces
    """
    if not name:
        return name
    return name.replace('-', ' ').replace('_', ' ')


def format_seconds_to_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if not seconds:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    
    parts = []
    if h > 0: parts.append(f"{h}h")
    if m > 0: parts.append(f"{m}m")
    if s > 0 or not parts: parts.append(f"{s}s")
    
    return " ".join(parts)



@dataclass
class ImageInfo:
    path: str
    exists: bool
    base64: Optional[str] = None


@dataclass
class PlateMetadata:
    jsonPath: str
    jsonExists: bool
    md5Path: str
    md5Exists: bool


@dataclass
class QuickAnalysis:
    estimatedPrintTime: Optional[str] = None
    printTimeSeconds: Optional[int] = None
    filamentWeight: Optional[str] = None
    filamentLength: Optional[str] = None
    material: Optional[str] = None
    layerCount: Optional[int] = None
    objectCount: Optional[int] = None


@dataclass
class PlateInfo:
    plateNumber: int
    gcodePath: str
    gcodeSize: int
    metadata: PlateMetadata
    hasGcode: bool
    quickAnalysis: QuickAnalysis
    albumName: Optional[str] = None
    # Images as flat base64 strings (matching /process endpoint format)
    plateImage: Optional[str] = None
    pickImage: Optional[str] = None
    topImage: Optional[str] = None
    plateNoLightImage: Optional[str] = None


def extract_plate_names_from_config(archive: zipfile.ZipFile, all_files: List[str]) -> Dict[int, str]:
    """
    Extract all plate names from model_settings.config

    Args:
        archive: Open ZipFile object
        all_files: List of all files in archive

    Returns:
        Dictionary mapping plate number to plate name
    """
    plate_names: Dict[int, str] = {}

    # Look for model_settings.config
    config_path = None
    for filepath in all_files:
        if filepath.lower() == 'metadata/model_settings.config':
            config_path = filepath
            break

    if not config_path:
        return plate_names

    try:
        config_data = archive.read(config_path).decode('utf-8')
        root = ET.fromstring(config_data)

        # Find all plate elements
        for plate in root.findall('.//plate'):
            plater_id = None
            plater_name = None

            for metadata in plate.findall('metadata'):
                key = metadata.get('key', '')
                value = metadata.get('value', '')

                if key == 'plater_id':
                    plater_id = int(value)
                elif key == 'plater_name':
                    plater_name = value

            if plater_id is not None and plater_name:
                plate_names[plater_id] = sanitize_plate_name(plater_name)

    except Exception as e:
        print(f"Error extracting plate names: {e}")

    return plate_names


def scan_gcode_file(fileBytes: bytes, fileName: Optional[str]) -> dict:
    """
    Scan a raw .gcode file and extract plate information.

    Args:
        fileBytes: Raw bytes of the GCODE file
        fileName: Original filename

    Returns:
        Dictionary with plate information (single plate)
    """
    from parsing.file_loader import loadInput
    from parsing.gcode_view import buildGcodeView
    from parsing.slicer_detect import detectSlicer
    from parsing.router import extractParsedValues

    try:
        # Load and parse the gcode file
        source = loadInput(fileBytes, fileName)
        gview = buildGcodeView(source)

        # Detect slicer and extract values
        guess = detectSlicer(gview)
        parsedValues = extractParsedValues(gview, guess)

        # Extract thumbnail image from gcode (embedded base64)
        plate_image = None
        if parsedValues.fieldValues.get('plateImageBase64'):
            plate_image = parsedValues.fieldValues['plateImageBase64']

        # Build quick analysis from parsed values
        quick_analysis = QuickAnalysis(
            estimatedPrintTime=format_seconds_to_duration(int(parsedValues.fieldValues.get('printTimeSec', 0))),
            printTimeSeconds=int(parsedValues.fieldValues.get('printTimeSec', 0)) if parsedValues.fieldValues.get('printTimeSec') else None,
            filamentWeight=f"{parsedValues.fieldValues.get('filamentUsedGrams', '0')}g",
            filamentLength=f"{parsedValues.fieldValues.get('filamentUsedMeters', '0')}m" if parsedValues.fieldValues.get('filamentUsedMeters') else None,
            material=parsedValues.fieldValues.get('filament_type') or parsedValues.fieldValues.get('filamentType'),
            layerCount=int(parsedValues.fieldValues.get('totalLayers', 0)) if parsedValues.fieldValues.get('totalLayers') else None,
            objectCount=int(parsedValues.fieldValues.get('objectsOnPlate', 0)) if parsedValues.fieldValues.get('objectsOnPlate') else None
        )


        # Create plate info
        plate_info = PlateInfo(
            plateNumber=1,
            gcodePath=fileName or 'uploaded.gcode',
            gcodeSize=len(fileBytes),
            metadata=PlateMetadata(
                jsonPath='',
                jsonExists=False,
                md5Path='',
                md5Exists=False
            ),
            hasGcode=True,
            quickAnalysis=quick_analysis,
            albumName=None,
            plateImage=plate_image,
            pickImage=None,
            topImage=None,
            plateNoLightImage=None
        )

        return {
            'success': True,
            'fileName': fileName,
            'totalPlates': 1,
            'fileSize': len(fileBytes),
            'plates': [asdict(plate_info)]
        }

    except Exception as e:
        raise Exception(f"Failed to scan gcode file: {str(e)}")


def scan_plates(fileBytes: bytes, fileName: Optional[str]) -> dict:
    """
    Main function to scan 3MF or GCODE file for all plates

    Args:
        fileBytes: Raw bytes of the 3MF or GCODE file
        fileName: Original filename

    Returns:
        Dictionary with plate information
    """
    # Check if this is a .gcode file (not a zip archive)
    is_gcode_file = False
    if fileName and fileName.lower().endswith('.gcode'):
        is_gcode_file = True
    else:
        # Try to detect if it's a zip file
        try:
            with zipfile.ZipFile(io.BytesIO(fileBytes)) as _:
                pass  # It's a valid zip file
        except zipfile.BadZipFile:
            # Not a zip file, assume it's a gcode file
            is_gcode_file = True

    if is_gcode_file:
        return scan_gcode_file(fileBytes, fileName)

    # Process as 3MF file
    try:
        with zipfile.ZipFile(io.BytesIO(fileBytes)) as archive:
            # Get all file names
            all_files = archive.namelist()

            # Find all GCODE files
            gcode_files = [
                name for name in all_files
                if name.lower().endswith('.gcode') and 'metadata/' in name.lower()
            ]

            # Extract plate numbers
            plates_data = []
            plate_numbers = extract_plate_numbers(gcode_files)

            # Extract plate names from model_settings.config
            plate_names = extract_plate_names_from_config(archive, all_files)

            for plate_num in sorted(plate_numbers):
                plate_info = extract_plate_info(archive, all_files, plate_num, plate_names)
                plates_data.append(plate_info)

            return {
                'success': True,
                'fileName': fileName,
                'totalPlates': len(plates_data),
                'fileSize': len(fileBytes),
                'plates': [asdict(plate) for plate in plates_data]
            }

    except Exception as e:
        raise Exception(f"Failed to scan plates: {str(e)}")


def extract_plate_numbers(gcode_files: List[str]) -> List[int]:
    """
    Extract plate numbers from GCODE filenames

    Args:
        gcode_files: List of GCODE file paths

    Returns:
        List of plate numbers
    """
    plate_numbers = []
    pattern = re.compile(r'plate_(\d+)\.gcode', re.IGNORECASE)

    for filepath in gcode_files:
        match = pattern.search(filepath)
        if match:
            plate_numbers.append(int(match.group(1)))

    return plate_numbers


def extract_plate_info(archive: zipfile.ZipFile, all_files: List[str], plate_num: int, plate_names: Optional[Dict[int, str]] = None) -> PlateInfo:
    """
    Extract complete information for a specific plate

    Args:
        archive: Open ZipFile object
        all_files: List of all files in archive
        plate_num: Plate number to extract
        plate_names: Optional dictionary mapping plate numbers to plate names

    Returns:
        PlateInfo object with all plate data
    """
    # Find GCODE file
    gcode_path = find_file_for_plate(all_files, plate_num, '.gcode', 'plate')
    gcode_size = 0
    gcode_exists = False

    if gcode_path:
        gcode_exists = True
        gcode_size = archive.getinfo(gcode_path).file_size

    # Extract images as flat base64 strings (matching /process endpoint format)
    plate_img_info = extract_image_info(archive, all_files, plate_num, 'plate', '.png')
    pick_img_info = extract_image_info(archive, all_files, plate_num, 'pick', '.png')
    top_img_info = extract_image_info(archive, all_files, plate_num, 'top', '.png')
    plate_no_light_img_info = extract_image_info(archive, all_files, plate_num, 'plate_no_light', '.png')

    # Convert to flat base64 strings (None if not found)
    plate_image = plate_img_info.base64 if plate_img_info.exists else None
    pick_image = pick_img_info.base64 if pick_img_info.exists else None
    top_image = top_img_info.base64 if top_img_info.exists else None
    plate_no_light_image = plate_no_light_img_info.base64 if plate_no_light_img_info.exists else None

    # Extract metadata paths
    json_path = find_file_for_plate(all_files, plate_num, '.json', 'plate')
    md5_path = find_file_for_plate(all_files, plate_num, '.md5', 'plate')

    metadata = PlateMetadata(
        jsonPath=json_path or f'Metadata/plate_{plate_num}.json',
        jsonExists=json_path is not None,
        md5Path=md5_path or f'Metadata/plate_{plate_num}.gcode.md5',
        md5Exists=md5_path is not None
    )

    # Quick GCODE analysis
    quick_analysis = QuickAnalysis()
    if gcode_exists and gcode_path:
        try:
            gcode_content = archive.read(gcode_path)
            quick_analysis = analyze_gcode_quick(gcode_content)
        except:
            pass  # If analysis fails, return empty QuickAnalysis

    # Get plate name (albumName)
    album_name = plate_names.get(plate_num) if plate_names else None

    return PlateInfo(
        plateNumber=plate_num,
        gcodePath=gcode_path or f'Metadata/plate_{plate_num}.gcode',
        gcodeSize=gcode_size,
        metadata=metadata,
        hasGcode=gcode_exists,
        quickAnalysis=quick_analysis,
        albumName=album_name,
        plateImage=plate_image,
        pickImage=pick_image,
        topImage=top_image,
        plateNoLightImage=plate_no_light_image
    )


def find_file_for_plate(all_files: List[str], plate_num: int, extension: str, prefix: str) -> Optional[str]:
    """
    Find a specific file for a plate number

    Args:
        all_files: List of all files
        plate_num: Plate number
        extension: File extension (e.g., '.gcode')
        prefix: File prefix (e.g., 'plate')

    Returns:
        File path or None
    """
    pattern = re.compile(f'{prefix}_{plate_num}{re.escape(extension)}$', re.IGNORECASE)

    for filepath in all_files:
        if pattern.search(filepath):
            return filepath

    return None


def extract_image_info(archive: zipfile.ZipFile, all_files: List[str],
                      plate_num: int, prefix: str, suffix: str) -> ImageInfo:
    """
    Extract image information and convert to base64

    Args:
        archive: Open ZipFile object
        all_files: List of all files
        plate_num: Plate number
        prefix: Image prefix (e.g., 'plate', 'pick')
        suffix: Image suffix (e.g., '.png', '_small.png')

    Returns:
        ImageInfo object
    """
    # Build expected path
    if suffix == '_small.png':
        expected_path = f'Metadata/{prefix}_{plate_num}_small.png'
    else:
        expected_path = f'Metadata/{prefix}_{plate_num}{suffix}'

    # Try to find the file
    image_path = None
    for filepath in all_files:
        if filepath.lower() == expected_path.lower():
            image_path = filepath
            break

    if not image_path:
        return ImageInfo(path=expected_path, exists=False, base64=None)

    # Read and encode image
    try:
        image_bytes = archive.read(image_path)
        base64_encoded = base64.b64encode(image_bytes).decode('utf-8')

        return ImageInfo(
            path=image_path,
            exists=True,
            base64=base64_encoded
        )
    except:
        return ImageInfo(path=image_path, exists=False, base64=None)


def analyze_gcode_quick(gcode_bytes: bytes) -> QuickAnalysis:
    """
    Quick analysis of GCODE file for basic metadata.
    Designed to work with Bambu Lab, OrcaSlicer, PrusaSlicer and standard headers.
    """
    try:
        # Decode GCODE
        gcode_text = gcode_bytes.decode('utf-8', errors='ignore')
        # Check first 2000 lines for reliability (3MF headers can be long)
        header_text = '\n'.join(gcode_text.split('\n')[:2000])

        analysis = QuickAnalysis()

        # 1. Print Time
        # Bambu/Orca: ; model printing time: 1h 2m 3s; total estimated time: 1h 5m 6s
        # Prusa: ; estimated printing time (normal mode) = 1h 2m 3s
        time_match = re.search(r'(?:printing time|estimated printing time).*?[:=]\s*((?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s))', header_text, re.IGNORECASE)
        if time_match:
            hours = int(time_match.group(2)) if time_match.group(2) else 0
            minutes = int(time_match.group(3)) if time_match.group(3) else 0
            seconds = int(time_match.group(4)) if time_match.group(4) else 0
            analysis.printTimeSeconds = hours * 3600 + minutes * 60 + seconds
            analysis.estimatedPrintTime = time_match.group(1).strip()

        # 2. Filament Weight [g]
        # Bambu: ; total filament weight [g] : 95.10,353.22
        # Prusa: ; filament used [g] = 152.74, 12.59
        weight_match = re.search(r'filament used \[g\]\s*[=:]\s*([0-9., ]+)', header_text, re.IGNORECASE)
        if not weight_match:
            weight_match = re.search(r'total filament weight \[g\]\s*[=:]\s*([0-9., ]+)', header_text, re.IGNORECASE)
        
        if weight_match:
            try:
                weights = [float(w.strip()) for w in weight_match.group(1).split(',') if w.strip()]
                total_weight = sum(weights)
                analysis.filamentWeight = f"{total_weight:.2f}g"
            except:
                pass

        # 3. Filament Length [mm]
        # Bambu: ; total filament length [mm] : 31379.69,116547.43
        # Prusa: ; filament used [mm] = 51212.00, 4221.24
        length_match = re.search(r'filament used \[mm\]\s*[=:]\s*([0-9., ]+)', header_text, re.IGNORECASE)
        if not length_match:
            length_match = re.search(r'total filament length \[mm\]\s*[=:]\s*([0-9., ]+)', header_text, re.IGNORECASE)
        
        if length_match:
            try:
                lengths = [float(l.strip()) for l in length_match.group(1).split(',') if l.strip()]
                total_length = sum(lengths)
                # Convert to meters if very long for readability
                if total_length > 1000:
                    analysis.filamentLength = f"{total_length/1000:.2f}m"
                else:
                    analysis.filamentLength = f"{total_length:.2f}mm"
            except:
                pass

        # 4. Material Type
        # Bambu: ; filament_type = PLA;PLA;PLA;PLA
        material_match = re.search(r'filament_type\s*[=:]\s*([^\n;]+)', header_text, re.IGNORECASE)
        if material_match:
            types = [t.strip().strip('"') for t in material_match.group(1).replace(';', ',').split(',') if t.strip()]
            if types:
                # Use unique types
                unique_types = sorted(list(set(types)))
                analysis.material = "/".join(unique_types) if len(unique_types) > 1 else unique_types[0]

        # 5. Layer Count
        # ; total layer number: 140 or ; total layers count = 127
        layer_match = re.search(r'(?:total layer number|total layers count)\s*[=:]\s*(\d+)', header_text, re.IGNORECASE)
        if layer_match:
            analysis.layerCount = int(layer_match.group(1))

        # 6. Object Count
        # Bambu: ; model label id: 482,493...
        objects_match = re.search(r'model label id:\s*([0-9,]+)', header_text, re.IGNORECASE)
        if objects_match:
            ids = [segment for segment in objects_match.group(1).split(',') if segment.strip()]
            analysis.objectCount = len(ids)

        return analysis


    except Exception as e:
        print(f"Quick analysis error: {e}")
        return QuickAnalysis()
