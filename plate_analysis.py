"""
Plate Analysis Module
Analyzes 3D print build plate images using Gemini Vision AI
to detect objects that could interfere with printing.
"""

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from typing import List, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

logger = logging.getLogger("plate-analysis")


@dataclass
class DetectedObject:
    """Represents a detected object on the build plate."""
    description: str
    location: Optional[str] = None  # "center", "left", "right", "front", "back"
    riskLevel: str = "unknown"  # "low", "medium", "high"


@dataclass
class PlateAnalysisResult:
    """Result of analyzing a build plate image."""
    hasInterference: bool
    confidenceScore: float  # 0.0 - 1.0
    summary: str
    detectedObjects: List[DetectedObject]
    recommendation: str


def to_dict(result: PlateAnalysisResult) -> dict:
    """Convert PlateAnalysisResult to dictionary for JSON serialization."""
    return {
        "hasInterference": result.hasInterference,
        "confidenceScore": result.confidenceScore,
        "summary": result.summary,
        "detectedObjects": [asdict(obj) for obj in result.detectedObjects],
        "recommendation": result.recommendation
    }


def analyze_plate_image(image_bytes: bytes, image_format: str = "png") -> PlateAnalysisResult:
    """
    Analyze a build plate image for potential interference objects.
    
    Args:
        image_bytes: Raw image bytes
        image_format: Image format (png, jpeg, webp)
    
    Returns:
        PlateAnalysisResult with analysis details
    
    Raises:
        ValueError: If API key is not set or Gemini SDK is not installed
        RuntimeError: If AI analysis fails
    """
    if not HAS_GENAI:
        raise ValueError("google-genai package is not installed. Run: pip install google-genai")
    
    # Get API key from environment
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    # Create Gemini client
    client = genai.Client(api_key=api_key)
    
    # Prepare the analysis prompt
    prompt = """You are an expert on 3D printing. Analyze this image of a 3D print build plate.

Task:
1. Identify if there are any 3D printed objects in the CENTER of the plate that could interfere with the next print.
2. IGNORE objects at the very edges of the plate - these are adhesion helpers or purge lines and will NOT interfere with printing.
3. Only objects in the central print area should be considered as potential interference.

IMPORTANT: Respond ONLY with valid JSON in the following format (no extra text):
{
    "hasInterference": true or false,
    "confidenceScore": number between 0.0 and 1.0,
    "summary": "Brief description of the plate and print area",
    "detectedObjects": [
        {
            "description": "Description of object",
            "location": "center or left or right or front or back",
            "riskLevel": "low or medium or high"
        }
    ],
    "recommendation": "Recommendation for the user"
}

Rules:
- Set hasInterference to FALSE if the plate only has small objects at the very edges
- Set hasInterference to TRUE only if there are objects in the center of the plate
- Adhesion helpers, purge lines, and other small edge helpers should be IGNORED
- Only consider objects in the central print area as interference"""

    try:
        # Encode image as base64 for the API
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Create image part for the API
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=f"image/{image_format}"
        )
        
        logger.info("Sending image to Gemini Vision API for analysis...")
        
        # Send to Gemini using the new SDK
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[prompt, image_part]
        )
        
        if not response.text:
            raise RuntimeError("Empty response from Gemini API")
        
        logger.info(f"Received response from Gemini: {response.text[:200]}...")
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Try to extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            response_text = json_match.group(1).strip()
        
        # Parse the JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {response_text}")
            raise RuntimeError(f"Invalid JSON response from AI: {e}")
        
        # Validate and extract fields
        detected_objects = []
        for obj in data.get("detectedObjects", []):
            detected_objects.append(DetectedObject(
                description=obj.get("description", "Ukjent objekt"),
                location=obj.get("location"),
                riskLevel=obj.get("riskLevel", "unknown")
            ))
        
        result = PlateAnalysisResult(
            hasInterference=bool(data.get("hasInterference", False)),
            confidenceScore=float(data.get("confidenceScore", 0.5)),
            summary=str(data.get("summary", "Analyse fullfort")),
            detectedObjects=detected_objects,
            recommendation=str(data.get("recommendation", "Ingen spesifikk anbefaling"))
        )
        
        logger.info(f"Analysis complete: hasInterference={result.hasInterference}, objects={len(result.detectedObjects)}")
        
        return result
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise RuntimeError(f"AI analysis failed: {e}")

