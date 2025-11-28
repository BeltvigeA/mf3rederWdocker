"""
Plate Splitter Module
Splits 3MF files into separate files for each selected plate
"""

import zipfile
import io
import base64
import re
from typing import List, Dict, Set


def split_3mf_by_plates(original_file_bytes: bytes, selected_plates: List[int], original_filename: str) -> dict:
    """
    Main function to split 3MF file by selected plates

    Args:
        original_file_bytes: Raw bytes of original 3MF file
        selected_plates: List of plate numbers to extract
        original_filename: Original filename

    Returns:
        Dictionary with split file information
    """
    try:
        split_files = []

        # Process each selected plate
        for plate_num in selected_plates:
            split_result = create_plate_specific_3mf(
                original_file_bytes,
                plate_num,
                original_filename
            )
            split_files.append(split_result)

        return {
            'success': True,
            'originalFile': original_filename,
            'totalSplitFiles': len(split_files),
            'splitFiles': split_files
        }

    except Exception as e:
        raise Exception(f"Failed to split 3MF file: {str(e)}")


def create_plate_specific_3mf(original_bytes: bytes, plate_number: int, original_filename: str) -> dict:
    """
    Create a new 3MF file containing only data for a specific plate

    Args:
        original_bytes: Original 3MF file bytes
        plate_number: Plate number to extract
        original_filename: Original filename

    Returns:
        Dictionary with split file info
    """
    # Open original ZIP
    original_zip = zipfile.ZipFile(io.BytesIO(original_bytes))

    # Create new in-memory ZIP
    new_zip_buffer = io.BytesIO()
    new_zip = zipfile.ZipFile(new_zip_buffer, 'w', zipfile.ZIP_DEFLATED)

    # Track what files we include
    included_files = {
        'gcode': False,
        'images': [],
        'metadata': []
    }

    try:
        # Process each file in original archive
        for file_info in original_zip.filelist:
            filepath = file_info.filename

            # Determine if we should include this file
            action = classify_file(filepath, plate_number)

            if action == 'KEEP_ALWAYS':
                # Always keep structural files
                data = original_zip.read(filepath)
                new_zip.writestr(file_info, data)

            elif action == 'KEEP_PLATE_FILE':
                # Keep plate-specific file
                data = original_zip.read(filepath)
                new_zip.writestr(file_info, data)

                # Track what type of file
                if filepath.lower().endswith('.gcode'):
                    included_files['gcode'] = True
                elif any(ext in filepath.lower() for ext in ['.png', '.jpg', '.jpeg']):
                    included_files['images'].append(filepath.split('/')[-1])
                elif filepath.lower().endswith('.json') or filepath.lower().endswith('.md5'):
                    included_files['metadata'].append(filepath.split('/')[-1])

            elif action == 'DELETE_OTHER_PLATE':
                # Skip files from other plates
                continue

        # Close the ZIP
        new_zip.close()
        original_zip.close()

        # Get the bytes
        new_file_bytes = new_zip_buffer.getvalue()

        # Generate new filename
        base_name = original_filename.replace('.3mf', '').replace('.gcode.3mf', '')
        new_filename = f"{base_name}-plate{plate_number}.3mf"

        # Encode to base64
        base64_encoded = base64.b64encode(new_file_bytes).decode('utf-8')

        return {
            'plateNumber': plate_number,
            'fileName': new_filename,
            'fileSize': len(new_file_bytes),
            'base64': base64_encoded,
            'containsFiles': included_files
        }

    except Exception as e:
        new_zip.close()
        original_zip.close()
        raise Exception(f"Error creating plate {plate_number} file: {str(e)}")


def classify_file(filepath: str, target_plate: int) -> str:
    """
    Classify a file to determine if it should be kept, deleted, or always kept

    Args:
        filepath: File path in ZIP
        target_plate: Target plate number

    Returns:
        'KEEP_ALWAYS', 'KEEP_PLATE_FILE', or 'DELETE_OTHER_PLATE'
    """
    filepath_lower = filepath.lower()

    # RULE 1: Always keep structural files
    always_keep_patterns = [
        '3d/',
        '[content_types].xml',
        '_rels/',
        'metadata/model_settings.config',
        'metadata/project_settings.config',
        'metadata/slice_info.config',
        'metadata/cut_information.xml'
    ]

    for pattern in always_keep_patterns:
        if pattern in filepath_lower:
            return 'KEEP_ALWAYS'

    # RULE 2: Check if file belongs to target plate
    if is_plate_specific_file(filepath, target_plate):
        return 'KEEP_PLATE_FILE'

    # RULE 3: Check if file belongs to another plate
    if is_other_plate_file(filepath, target_plate):
        return 'DELETE_OTHER_PLATE'

    # Default: keep the file (for any unclassified files)
    return 'KEEP_ALWAYS'


def is_plate_specific_file(filepath: str, plate_number: int) -> bool:
    """
    Check if a file belongs to a specific plate

    Args:
        filepath: File path to check
        plate_number: Plate number

    Returns:
        True if file belongs to this plate
    """
    # Pattern for plate-specific files
    patterns = [
        f'plate_{plate_number}\\.',
        f'pick_{plate_number}\\.',
        f'top_{plate_number}\\.',
        f'plate_no_light_{plate_number}\\.',
        f'plate_{plate_number}_small\\.',
    ]

    filepath_lower = filepath.lower()

    for pattern in patterns:
        if re.search(pattern, filepath_lower):
            return True

    return False


def is_other_plate_file(filepath: str, target_plate: int) -> bool:
    """
    Check if a file belongs to a different plate

    Args:
        filepath: File path to check
        target_plate: Target plate number

    Returns:
        True if file belongs to another plate
    """
    # Match patterns like: plate_X., pick_X., top_X., etc.
    patterns = [
        r'plate_(\d+)\.',
        r'pick_(\d+)\.',
        r'top_(\d+)\.',
        r'plate_no_light_(\d+)\.',
        r'plate_(\d+)_small\.',
    ]

    filepath_lower = filepath.lower()

    for pattern in patterns:
        match = re.search(pattern, filepath_lower)
        if match:
            file_plate_num = int(match.group(1))
            # If it's a different plate number, mark for deletion
            if file_plate_num != target_plate:
                return True

    return False


def get_files_to_keep(all_files: List[str], plate_number: int) -> Set[str]:
    """
    Get a set of files that should be kept for a specific plate

    Args:
        all_files: List of all files in archive
        plate_number: Target plate number

    Returns:
        Set of file paths to keep
    """
    keep_files = set()

    for filepath in all_files:
        classification = classify_file(filepath, plate_number)

        if classification in ['KEEP_ALWAYS', 'KEEP_PLATE_FILE']:
            keep_files.add(filepath)

    return keep_files


def get_files_to_delete(all_files: List[str], plate_number: int) -> Set[str]:
    """
    Get a set of files that should be deleted for a specific plate

    Args:
        all_files: List of all files in archive
        plate_number: Target plate number

    Returns:
        Set of file paths to delete
    """
    delete_files = set()

    for filepath in all_files:
        classification = classify_file(filepath, plate_number)

        if classification == 'DELETE_OTHER_PLATE':
            delete_files.add(filepath)

    return delete_files
