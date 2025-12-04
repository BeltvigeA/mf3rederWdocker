from __future__ import annotations

import base64
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


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
