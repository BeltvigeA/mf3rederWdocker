from __future__ import annotations

import base64
import io
import math
import xml.etree.ElementTree as ET
from colorsys import rgb_to_hsv
from typing import Any, Dict, List

from fastapi import HTTPException
from PIL import Image, ImageDraw

from ..extractors.base import ParsedValues
from ..gcode_view import GCodeView


def toCamelCase(text: str) -> str:
    parts = text.split('_')
    return parts[0] + ''.join(part.capitalize() for part in parts[1:]) if parts else text


def segmentColorRegions(pickImageBytes: bytes) -> List[Dict[str, Any]]:
    pickImage = Image.open(io.BytesIO(pickImageBytes)).convert('RGBA')
    width, height = pickImage.size
    pixelAccess = pickImage.load()
    alphaMask = [[False for _ in range(width)] for _ in range(height)]
    colorGrid = [[(0, 0, 0) for _ in range(width)] for _ in range(height)]
    for pixelY in range(height):
        for pixelX in range(width):
            red, green, blue, alpha = pixelAccess[pixelX, pixelY]
            alphaMask[pixelY][pixelX] = alpha > 0
            colorGrid[pixelY][pixelX] = (red, green, blue)
    visitedMask = [[False for _ in range(width)] for _ in range(height)]
    regions: List[Dict[str, Any]] = []
    for pixelY in range(height):
        for pixelX in range(width):
            if not alphaMask[pixelY][pixelX] or visitedMask[pixelY][pixelX]:
                continue
            targetColor = colorGrid[pixelY][pixelX]
            stack = [(pixelX, pixelY)]
            visitedMask[pixelY][pixelX] = True
            sumRed = sumGreen = sumBlue = 0.0
            sumX = sumY = 0.0
            pixelCount = 0
            while stack:
                currentX, currentY = stack.pop()
                red, green, blue = colorGrid[currentY][currentX]
                sumRed += red
                sumGreen += green
                sumBlue += blue
                sumX += currentX
                sumY += currentY
                pixelCount += 1
                for offsetX, offsetY in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    neighborX = currentX + offsetX
                    neighborY = currentY + offsetY
                    if 0 <= neighborX < width and 0 <= neighborY < height and not visitedMask[neighborY][neighborX]:
                        if alphaMask[neighborY][neighborX] and colorGrid[neighborY][neighborX] == targetColor:
                            visitedMask[neighborY][neighborX] = True
                            stack.append((neighborX, neighborY))
            if pixelCount == 0:
                continue
            meanRed = sumRed / pixelCount
            meanGreen = sumGreen / pixelCount
            meanBlue = sumBlue / pixelCount
            brightness = rgb_to_hsv(
                meanRed / 255.0,
                meanGreen / 255.0,
                meanBlue / 255.0,
            )[2]
            centroidX = sumX / pixelCount
            centroidY = sumY / pixelCount
            regions.append({
                'meanColor': (meanRed, meanGreen, meanBlue),
                'brightness': brightness,
                'centroid': (centroidX, centroidY),
            })
    pickImage.close()
    orderedRegions = sorted(
        regions,
        key=lambda entry: (
            -entry['brightness'],
            -entry['meanColor'][0],
            -entry['meanColor'][1],
            -entry['meanColor'][2],
        ),
    )
    rankedRegions: List[Dict[str, Any]] = []
    for index, region in enumerate(orderedRegions, start=1):
        rankedRegions.append({
            'order': index,
            'centroid': region['centroid'],
            'meanColor': tuple(int(round(value)) for value in region['meanColor']),
            'brightness': region['brightness'],
        })
    return rankedRegions


def drawOrderLabels(topImageBytes: bytes, rankedRegions: List[Dict[str, Any]]) -> bytes:
    if not rankedRegions:
        return topImageBytes
    topImage = Image.open(io.BytesIO(topImageBytes)).convert('RGBA')
    draw = ImageDraw.Draw(topImage)
    for region in rankedRegions:
        centroidX, centroidY = region['centroid']
        textPosition = (float(centroidX), float(centroidY))
        draw.text(
            textPosition,
            str(region['order']),
            fill=(255, 255, 255, 255),
            anchor='mm',
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
    outputBuffer = io.BytesIO()
    topImage.save(outputBuffer, format='PNG')
    topImage.close()
    return outputBuffer.getvalue()


def parseObjects(sliceContent: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(sliceContent)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail='Invalid slice_info.config content') from exc
    objects: List[Dict[str, Any]] = []
    for element in root.findall('.//object'):
        converted = {toCamelCase(key): value for key, value in element.attrib.items()}
        objects.append(converted)
    def safeIdentify(item: Dict[str, Any]) -> int:
        try:
            return int(item.get('identifyId', ''))
        except (TypeError, ValueError):
            return math.inf
    objects.sort(key=safeIdentify)
    return objects


def enrichBambuAttachments(gview: GCodeView, values: ParsedValues) -> Dict[str, str]:
    attachments = gview.attachments
    plateNum = gview.plateNumber

    # Try to find images with the correct plate number
    plateImageBytes = attachments.get(f'Metadata/plate_{plateNum}.png')
    pickImageBytes = attachments.get(f'Metadata/pick_{plateNum}.png')
    topImageBytes = attachments.get(f'Metadata/top_{plateNum}.png')
    sliceConfigBytes = attachments.get('Metadata/slice_info.config')

    if plateImageBytes is None:
        raise HTTPException(status_code=404, detail=f'plate_{plateNum}.png not found')
    if pickImageBytes is None:
        raise HTTPException(status_code=404, detail=f'pick_{plateNum}.png not found')
    if topImageBytes is None:
        raise HTTPException(status_code=404, detail=f'top_{plateNum}.png not found')
    if sliceConfigBytes is None:
        raise HTTPException(status_code=404, detail='slice_info.config not found')
    rankedRegions = segmentColorRegions(pickImageBytes)
    drawnTop = drawOrderLabels(topImageBytes, rankedRegions)
    sliceContent = sliceConfigBytes.decode('utf-8', errors='ignore')
    objects = parseObjects(sliceContent)
    values.fieldValues['objects'] = objects
    orderedObjects: List[Dict[str, Any]] = []
    pairedObjects = []
    for item in objects:
        try:
            pairedObjects.append((int(item.get('identifyId', '')), item))
        except (TypeError, ValueError):
            continue
    pairedObjects.sort(key=lambda entry: entry[0])
    for region, (_, obj) in zip(rankedRegions, pairedObjects):
        orderedObjects.append({
            'order': region['order'],
            'identifyId': obj.get('identifyId'),
            'name': obj.get('name'),
            'skipped': obj.get('skipped'),
        })
    values.fieldValues['orderedObjects'] = orderedObjects
    plateImageBase64 = base64.b64encode(plateImageBytes).decode('utf-8')
    pickImageBase64 = base64.b64encode(pickImageBytes).decode('utf-8')
    topImageBase64 = base64.b64encode(drawnTop).decode('utf-8')
    return {
        'plateImage': plateImageBase64,
        'pickImage': pickImageBase64,
        'topImage': topImageBase64,
    }
