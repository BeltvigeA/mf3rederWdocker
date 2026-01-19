from __future__ import annotations

import base64
import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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


def extractPlateName(gview) -> Optional[str]:
    """
    Extract the plate name (plater_name) from model_settings.config in 3MF attachments.

    The plate name is stored in the XML structure:
    <plate>
      <metadata key="plater_id" value="1"/>
      <metadata key="plater_name" value="Album Name Here"/>
      ...
    </plate>

    Returns:
        The plate name string if found, otherwise None
    """
    plateNum = getattr(gview, 'plateNumber', 1)

    # Look for model_settings.config in attachments
    configPatterns = [
        'Metadata/model_settings.config',
        'model_settings.config',
    ]

    configData = None
    for pattern in configPatterns:
        # Try exact match
        if pattern in gview.attachments:
            try:
                configData = gview.attachments[pattern].decode('utf-8')
                logger.info(f'✅ Found model_settings.config: {pattern}')
                break
            except UnicodeDecodeError as e:
                logger.warning(f'⚠️ Failed to decode {pattern}: {e}')

        # Try case-insensitive search
        patternLower = pattern.lower()
        for attachmentPath, data in gview.attachments.items():
            if attachmentPath.lower() == patternLower:
                try:
                    configData = data.decode('utf-8')
                    logger.info(f'✅ Found model_settings.config: {attachmentPath} (case-insensitive)')
                    break
                except UnicodeDecodeError as e:
                    logger.warning(f'⚠️ Failed to decode {attachmentPath}: {e}')

        if configData:
            break

    if not configData:
        logger.warning('❌ model_settings.config not found in attachments')
        return None

    try:
        # Parse XML
        root = ET.fromstring(configData)

        # Find all plate elements
        for plate in root.findall('.//plate'):
            # Get the plater_id for this plate
            platerId = None
            platerName = None

            for metadata in plate.findall('metadata'):
                key = metadata.get('key', '')
                value = metadata.get('value', '')

                if key == 'plater_id':
                    platerId = int(value)
                elif key == 'plater_name':
                    platerName = value

            # Check if this is the plate we're looking for
            if platerId == plateNum and platerName:
                sanitizedName = sanitize_plate_name(platerName)
                logger.info(f'🏷️ Found plate name for plate {plateNum}: "{platerName}" -> "{sanitizedName}"')
                return sanitizedName

        logger.warning(f'❌ No plate name found for plate {plateNum} in model_settings.config')
        return None

    except ET.ParseError as e:
        logger.warning(f'⚠️ Failed to parse model_settings.config XML: {e}')
        return None
    except Exception as e:
        logger.warning(f'⚠️ Error extracting plate name: {e}')
        return None


def enrichBambuAttachments(gview, parsedValues: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract and encode Bambu Studio images from 3MF attachments.
    Uses dynamic plate number from gview.
    """
    result = {}

    # Get plate number from gview
    plateNum = getattr(gview, 'plateNumber', 1)

    logger.info(f'🔍 Looking for images for plate {plateNum}')

    # Define image patterns with plate number
    imagePatterns = {
        'plateImage': [
            f'Metadata/plate_{plateNum}.png',
            f'plate_{plateNum}.png',
        ],
        'pickImage': [
            f'Metadata/pick_{plateNum}.png',
            f'pick_{plateNum}.png',
        ],
        'topImage': [
            f'Metadata/top_{plateNum}.png',
            f'top_{plateNum}.png',
        ],
        'plateNoLightImage': [
            f'Metadata/plate_no_light_{plateNum}.png',
            f'plate_no_light_{plateNum}.png',
        ]
    }

    # Search for each image type
    for imageKey, patterns in imagePatterns.items():
        found = False

        for pattern in patterns:
            # Try exact match first
            if pattern in gview.attachments:
                try:
                    imageData = gview.attachments[pattern]
                    result[imageKey] = base64.b64encode(imageData).decode('utf-8')
                    logger.info(f'✅ Found {imageKey}: {pattern}')
                    found = True
                    break
                except Exception as e:
                    logger.warning(f'⚠️ Failed to encode {pattern}: {e}')

            # Try case-insensitive search
            if not found:
                patternLower = pattern.lower()
                for attachmentPath, imageData in gview.attachments.items():
                    if attachmentPath.lower() == patternLower:
                        try:
                            result[imageKey] = base64.b64encode(imageData).decode('utf-8')
                            logger.info(f'✅ Found {imageKey}: {attachmentPath} (case-insensitive)')
                            found = True
                            break
                        except Exception as e:
                            logger.warning(f'⚠️ Failed to encode {attachmentPath}: {e}')

        if not found:
            logger.warning(f'❌ Image not found for {imageKey} (plate {plateNum})')

    return result


def extractObjectsFromPlateJson(gview) -> Dict[str, Any]:
    """
    Extract object information from plate_X.json in 3MF attachments.

    Returns a dict with:
    - objects: List of object dicts with name, id, bbox, etc.
    - objectsOnPlate: Count of objects (excluding wipe_tower)
    """
    result: Dict[str, Any] = {
        'objects': [],
        'objectsOnPlate': 0,
    }

    plateNum = getattr(gview, 'plateNumber', 1)

    # Look for plate_X.json
    jsonPatterns = [
        f'Metadata/plate_{plateNum}.json',
        f'plate_{plateNum}.json',
    ]

    plateJsonData = None
    for pattern in jsonPatterns:
        # Try exact match
        if pattern in gview.attachments:
            try:
                plateJsonData = json.loads(gview.attachments[pattern].decode('utf-8'))
                logger.info(f'✅ Found plate JSON: {pattern}')
                break
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f'⚠️ Failed to parse {pattern}: {e}')

        # Try case-insensitive search
        patternLower = pattern.lower()
        for attachmentPath, data in gview.attachments.items():
            if attachmentPath.lower() == patternLower:
                try:
                    plateJsonData = json.loads(data.decode('utf-8'))
                    logger.info(f'✅ Found plate JSON: {attachmentPath} (case-insensitive)')
                    break
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(f'⚠️ Failed to parse {attachmentPath}: {e}')

        if plateJsonData:
            break

    if not plateJsonData:
        logger.warning(f'❌ plate_{plateNum}.json not found in attachments')
        return result

    # Extract bbox_objects
    bboxObjects = plateJsonData.get('bbox_objects', [])

    objects: List[Dict[str, Any]] = []
    modelObjectCount = 0

    for obj in bboxObjects:
        objName = obj.get('name', '')
        objId = obj.get('id')

        # Skip wipe_tower from count (but include in list)
        isWipeTower = objName.lower() == 'wipe_tower'

        objectInfo: Dict[str, Any] = {
            'name': objName,
            'id': objId,
        }

        # Add optional fields if present
        if 'bbox' in obj:
            objectInfo['bbox'] = obj['bbox']
        if 'layer_height' in obj:
            objectInfo['layerHeight'] = obj['layer_height']
        if 'area' in obj:
            objectInfo['area'] = obj['area']

        objects.append(objectInfo)

        if not isWipeTower:
            modelObjectCount += 1

    result['objects'] = objects
    result['objectsOnPlate'] = modelObjectCount

    logger.info(f'📦 Extracted {len(objects)} objects ({modelObjectCount} models + wipe tower)')

    return result
