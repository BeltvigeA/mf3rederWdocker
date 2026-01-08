"""
Print Completion Analysis Module
Analyzes images of 3D prints using Gemini Vision AI
to determine if the print job is complete.
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

logger = logging.getLogger("print-completion")


@dataclass
class PrintIssue:
    """Represents a potential issue detected with the print."""
    description: str
    severity: str = "unknown"  # "minor", "moderate", "severe"
    location: Optional[str] = None


@dataclass
class PrintCompletionResult:
    """Result of analyzing a print completion image."""
    isComplete: bool
    confidenceScore: float  # 0.0 - 1.0
    printStatus: str  # "complete", "in_progress", "failed", "unknown"
    summary: str
    detectedIssues: List[PrintIssue]
    recommendation: str
    estimatedProgress: Optional[int] = None  # 0-100 percentage if in progress


def to_dict(result: PrintCompletionResult) -> dict:
    """Convert PrintCompletionResult to dictionary for JSON serialization."""
    return {
        "isComplete": result.isComplete,
        "confidenceScore": result.confidenceScore,
        "printStatus": result.printStatus,
        "summary": result.summary,
        "detectedIssues": [asdict(issue) for issue in result.detectedIssues],
        "recommendation": result.recommendation,
        "estimatedProgress": result.estimatedProgress
    }


def analyze_print_completion(image_bytes: bytes, image_format: str = "png") -> PrintCompletionResult:
    """
    Analyze an image to determine if a 3D print job is complete.

    Args:
        image_bytes: Raw image bytes
        image_format: Image format (png, jpeg, webp)

    Returns:
        PrintCompletionResult with analysis details

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
    prompt = """You are an expert on 3D printing quality control. Analyze this image of a 3D print.

Task:
1. Determine if the 3D print appears to be COMPLETE or still IN PROGRESS or FAILED.
2. Look for signs of a finished print:
   - Clean, complete layers all the way to the top
   - No active printing happening (no visible filament being extruded)
   - Object appears to match expected finished shape
3. Look for signs of an incomplete or failed print:
   - Spaghetti (tangled filament mess)
   - Layer shifting or warping
   - Detached from bed
   - Missing sections
   - Still actively printing (extruder moving, fresh filament visible)

IMPORTANT: Respond ONLY with valid JSON in the following format (no extra text):
{
    "isComplete": true or false,
    "confidenceScore": number between 0.0 and 1.0,
    "printStatus": "complete" or "in_progress" or "failed" or "unknown",
    "summary": "Brief description of the print status and what you observe",
    "estimatedProgress": number 0-100 if in_progress else null,
    "detectedIssues": [
        {
            "description": "Description of any issue found",
            "severity": "minor" or "moderate" or "severe",
            "location": "where on the print the issue is located"
        }
    ],
    "recommendation": "What action should be taken (e.g., 'Print complete - safe to remove', 'Print in progress - wait for completion', 'Print failed - abort and restart')"
}

Rules:
- Set isComplete to TRUE only if the print appears fully finished with no active printing
- Set isComplete to FALSE if printing is still happening or if the print failed
- printStatus should be "complete" for finished prints, "in_progress" for ongoing, "failed" for problematic prints
- Be conservative - if unsure, lean towards "in_progress" or lower confidence
- Look for visual cues like the print head position, fresh filament, layer count, etc."""

    try:
        # Create image part for the API
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=f"image/{image_format}"
        )

        logger.info("Sending image to Gemini Vision API for print completion analysis...")

        # Send to Gemini
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
        detected_issues = []
        for issue in data.get("detectedIssues", []):
            detected_issues.append(PrintIssue(
                description=issue.get("description", "Unknown issue"),
                severity=issue.get("severity", "unknown"),
                location=issue.get("location")
            ))

        result = PrintCompletionResult(
            isComplete=bool(data.get("isComplete", False)),
            confidenceScore=float(data.get("confidenceScore", 0.5)),
            printStatus=str(data.get("printStatus", "unknown")),
            summary=str(data.get("summary", "Analysis complete")),
            detectedIssues=detected_issues,
            recommendation=str(data.get("recommendation", "No specific recommendation")),
            estimatedProgress=data.get("estimatedProgress")
        )

        logger.info(f"Print completion analysis complete: isComplete={result.isComplete}, status={result.printStatus}")

        return result

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise RuntimeError(f"AI analysis failed: {e}")
