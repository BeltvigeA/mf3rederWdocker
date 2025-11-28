"""
Plate Scanner Module
Scans 3MF files for all available plates and extracts metadata
"""

import zipfile
import io
import base64
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


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
    images: Dict[str, ImageInfo]
    metadata: PlateMetadata
    hasGcode: bool
    quickAnalysis: QuickAnalysis


def scan_plates(fileBytes: bytes, fileName: Optional[str]) -> dict:
    """
    Main function to scan 3MF file for all plates

    Args:
        fileBytes: Raw bytes of the 3MF file
        fileName: Original filename

    Returns:
        Dictionary with plate information
    """
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

            for plate_num in sorted(plate_numbers):
                plate_info = extract_plate_info(archive, all_files, plate_num)
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


def extract_plate_info(archive: zipfile.ZipFile, all_files: List[str], plate_num: int) -> PlateInfo:
    """
    Extract complete information for a specific plate

    Args:
        archive: Open ZipFile object
        all_files: List of all files in archive
        plate_num: Plate number to extract

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

    # Extract images
    images = {
        'plate': extract_image_info(archive, all_files, plate_num, 'plate', '.png'),
        'plateSmall': extract_image_info(archive, all_files, plate_num, 'plate', '_small.png'),
        'pick': extract_image_info(archive, all_files, plate_num, 'pick', '.png'),
        'top': extract_image_info(archive, all_files, plate_num, 'top', '.png'),
        'plateNoLight': extract_image_info(archive, all_files, plate_num, 'plate_no_light', '.png')
    }

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

    return PlateInfo(
        plateNumber=plate_num,
        gcodePath=gcode_path or f'Metadata/plate_{plate_num}.gcode',
        gcodeSize=gcode_size,
        images=images,
        metadata=metadata,
        hasGcode=gcode_exists,
        quickAnalysis=quick_analysis
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
    Quick analysis of GCODE file for basic metadata

    Args:
        gcode_bytes: Raw GCODE file bytes

    Returns:
        QuickAnalysis object with extracted data
    """
    try:
        # Decode GCODE
        gcode_text = gcode_bytes.decode('utf-8', errors='ignore')
        lines = gcode_text.split('\n')[:500]  # Only check first 500 lines

        analysis = QuickAnalysis()

        for line in lines:
            line = line.strip()

            # Print time
            if 'estimated printing time' in line.lower():
                match = re.search(r'(\d+)h\s*(\d+)m\s*(\d+)s', line, re.IGNORECASE)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = int(match.group(3))
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    analysis.printTimeSeconds = total_seconds
                    analysis.estimatedPrintTime = f"{hours}h {minutes}m {seconds}s"

            # Filament weight
            if 'total filament weight' in line.lower():
                match = re.search(r'(\d+\.?\d*)\s*g', line, re.IGNORECASE)
                if match:
                    analysis.filamentWeight = f"{match.group(1)}g"

            # Filament length
            if 'total filament used' in line.lower():
                match = re.search(r'(\d+\.?\d*)\s*mm', line, re.IGNORECASE)
                if match:
                    analysis.filamentLength = f"{match.group(1)}mm"

            # Material type
            if 'filament_type' in line.lower() or 'material' in line.lower():
                for material in ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'PC', 'PA', 'PVA']:
                    if material in line.upper():
                        analysis.material = material
                        break

            # Layer count
            if 'total_layer_count' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    analysis.layerCount = int(match.group(1))

            # Object count
            if 'object' in line.lower() and 'count' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    analysis.objectCount = int(match.group(1))

        return analysis

    except Exception as e:
        print(f"Quick analysis error: {e}")
        return QuickAnalysis()
