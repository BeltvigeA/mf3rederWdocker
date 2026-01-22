"""Extractor for Snapmaker U1 and similar toolchanger printers.

This extractor handles G-code files from toolchanger printers that use
OrcaSlicer/PrusaSlicer format but need additional parsing for multi-tool
setups with filament type, color, and usage per tool head.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import ParsedValues
from .orca_gcode import OrcaGcodeExtractor
from ..gcode_view import GCodeView


@dataclass
class ToolInfo:
    """Information about a single tool head."""
    toolIndex: int
    filamentType: Optional[str] = None
    filamentColor: Optional[str] = None
    filamentUsedGrams: Optional[float] = None
    filamentUsedMm: Optional[float] = None
    isUsed: bool = False

    def toDict(self) -> Dict[str, Any]:
        return {
            'toolIndex': self.toolIndex,
            'filamentType': self.filamentType,
            'filamentColor': self.filamentColor,
            'filamentUsedGrams': self.filamentUsedGrams,
            'filamentUsedMm': self.filamentUsedMm,
            'isUsed': self.isUsed,
        }


class SnapmakerToolchangerExtractor:
    """Extractor specifically for Snapmaker U1 and similar toolchanger printers.
    
    This extractor parses:
    - filament_type = PLA;PLA;PETG;TPU (semicolon-separated per tool)
    - filament_colour = #804000;#400080;#00FF00;#000000 (hex colors per tool)
    - filament used [g] = 0.86, 0.00, 12.14, 24.98 (usage per tool)
    - CP TOOLCHANGE blocks to detect actual tool usage
    - ; Change ToolX -> ToolY patterns
    """

    def __init__(self):
        self._baseExtractor = OrcaGcodeExtractor()

    def extract(self, gview: GCodeView) -> ParsedValues:
        """Extract values from Snapmaker toolchanger G-code."""
        # First, get base Orca values
        baseResult = self._baseExtractor.extract(gview)
        values = baseResult.fieldValues
        meta = baseResult.meta

        gcodeText = gview.text

        # === Parse tool-specific configuration ===
        toolInfos = self._parseToolInfos(gcodeText)
        
        if toolInfos:
            # Filter to only used tools
            usedTools = [t for t in toolInfos if t.isUsed]
            
            values['tools'] = [t.toDict() for t in toolInfos]
            values['usedTools'] = [t.toDict() for t in usedTools]
            values['usedToolIndices'] = [t.toolIndex for t in usedTools]
            values['toolCount'] = len(toolInfos)
            values['usedToolCount'] = len(usedTools)

            # Create a summary of filament types being used
            usedFilamentTypes = list(set(
                t.filamentType for t in usedTools 
                if t.filamentType
            ))
            values['usedFilamentTypes'] = usedFilamentTypes

            # Create a mapping of tool index to filament info
            toolFilamentMap = {}
            for t in toolInfos:
                toolFilamentMap[str(t.toolIndex)] = {
                    'type': t.filamentType,
                    'color': t.filamentColor,
                    'usedGrams': t.filamentUsedGrams,
                }
            values['toolFilamentMap'] = toolFilamentMap

            # Rebuild filamentAnalysis to include toolIndex and ensure correct mapping
            # The base Orca extractor might filter out unused filaments, losing the index alignment.
            # We rebuild it here using our parsed toolInfos which preserves indices.
            newAnalysis = []
            for t in toolInfos:
                # Include if used OR if it has a type assigned (even if usage is 0)
                if t.isUsed or t.filamentType:
                    item = {
                        'toolIndex': t.toolIndex,
                        'weightG': t.filamentUsedGrams,
                        'lengthMm': t.filamentUsedMm,
                        # Volume is not directly parsed per tool in current logic, 
                        # but we can estimate or leave it if not critical. 
                        # Or we could try to map back from base analysis if needed.
                        'volumeCm3': 0.0 # Placeholder or calculation if needed
                    }
                    
                    # Try to match volume from base analysis if available and weights match
                    # This is a heuristic matching
                    if 'filamentAnalysis' in values:
                        for baseItem in values['filamentAnalysis']:
                            # If weights are very close, assume it's the same filament
                            if baseItem.get('weightG') and abs(baseItem['weightG'] - (t.filamentUsedGrams or 0)) < 0.1:
                                item['volumeCm3'] = baseItem.get('volumeCm3', 0.0)
                                if not item['lengthMm']:
                                    item['lengthMm'] = baseItem.get('lengthMm', 0.0)
                                break
                    
                    newAnalysis.append(item)
            
            values['filamentAnalysis'] = newAnalysis

        # === Parse tool change operations ===
        # toolChanges = self._parseToolChanges(gcodeText)
        # if toolChanges:
        #     values['toolChangeOperations'] = toolChanges
        #     values['totalToolChanges'] = len(toolChanges)

        # === Detect if this is a Snapmaker printer ===
        printerModel = values.get('printer_model', '')
        if 'snapmaker' in printerModel.lower():
            meta['isSnapmaker'] = True
            meta['printerType'] = 'snapmaker_toolchanger'

        # Mark as toolchanger if we have multiple tools
        if len([t for t in toolInfos if t.isUsed]) > 1:
            meta['isToolchanger'] = True

        return ParsedValues(fieldValues=values, meta=meta)

    def _parseToolInfos(self, gcodeText: str) -> List[ToolInfo]:
        """Parse tool information from G-code config."""
        tools: List[ToolInfo] = []

        # === Parse filament types ===
        # ; filament_type = PLA;PLA;PETG;TPU
        filamentTypeMatch = re.search(
            r';\s*filament_type\s*=\s*([^\n]+)',
            gcodeText,
            re.IGNORECASE
        )
        filamentTypes: List[str] = []
        if filamentTypeMatch:
            typeStr = filamentTypeMatch.group(1).strip()
            # Handle both semicolon and comma-separated
            if ';' in typeStr:
                filamentTypes = [t.strip().strip('"') for t in typeStr.split(';')]
            else:
                filamentTypes = [t.strip().strip('"') for t in typeStr.split(',')]

        # === Parse filament colors ===
        # ; filament_colour = #804000;#400080;#00FF00;#000000
        filamentColorMatch = re.search(
            r';\s*filament_colour\s*=\s*([^\n]+)',
            gcodeText,
            re.IGNORECASE
        )
        filamentColors: List[str] = []
        if filamentColorMatch:
            colorStr = filamentColorMatch.group(1).strip()
            if ';' in colorStr:
                filamentColors = [c.strip().strip('"') for c in colorStr.split(';')]
            else:
                filamentColors = [c.strip().strip('"') for c in colorStr.split(',')]

        # === Parse filament usage in grams ===
        # ; filament used [g] = 0.86, 0.00, 12.14, 24.98
        filamentUsedGMatch = re.search(
            r';\s*filament used \[g\]\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )
        filamentUsedGrams: List[float] = []
        if filamentUsedGMatch:
            usageStr = filamentUsedGMatch.group(1).strip()
            filamentUsedGrams = [
                float(g.strip()) 
                for g in usageStr.split(',') 
                if g.strip()
            ]

        # === Parse filament usage in mm ===
        # ; filament used [mm] = 285.90, 0.00, 3973.43, 8511.37
        filamentUsedMmMatch = re.search(
            r';\s*filament used \[mm\]\s*=\s*([0-9., ]+)',
            gcodeText,
            re.IGNORECASE
        )
        filamentUsedMm: List[float] = []
        if filamentUsedMmMatch:
            usageStr = filamentUsedMmMatch.group(1).strip()
            filamentUsedMm = [
                float(m.strip()) 
                for m in usageStr.split(',') 
                if m.strip()
            ]

        # === Determine number of tools ===
        numTools = max(
            len(filamentTypes),
            len(filamentColors),
            len(filamentUsedGrams),
            len(filamentUsedMm),
            4  # Default minimum for Snapmaker U1
        )

        # Create ToolInfo for each tool
        for i in range(numTools):
            tool = ToolInfo(toolIndex=i)

            if i < len(filamentTypes):
                tool.filamentType = filamentTypes[i] if filamentTypes[i] else None

            if i < len(filamentColors):
                tool.filamentColor = filamentColors[i] if filamentColors[i] else None

            if i < len(filamentUsedGrams):
                tool.filamentUsedGrams = filamentUsedGrams[i]
                # Tool is considered "used" if it has consumed more than 0.01g
                tool.isUsed = filamentUsedGrams[i] > 0.01

            if i < len(filamentUsedMm):
                tool.filamentUsedMm = filamentUsedMm[i]
                # Also mark as used if mm usage is significant
                if filamentUsedMm[i] > 1.0:
                    tool.isUsed = True

            tools.append(tool)

        return tools

    def _parseToolChanges(self, gcodeText: str) -> List[Dict[str, Any]]:
        """Parse tool change operations from G-code.
        
        Looks for patterns like:
        ; CP TOOLCHANGE START
        ; toolchange #8
        ; material : PLA -> TPU
        ; Change Tool0 -> Tool3 (layer 11)
        """
        toolChanges: List[Dict[str, Any]] = []

        # Pattern for CP TOOLCHANGE blocks with material info
        cpToolchangePattern = re.compile(
            r';\s*CP TOOLCHANGE START\s*\n'
            r';\s*toolchange #(\d+)\s*\n'
            r';\s*material\s*:\s*(\w+)\s*->\s*(\w+)',
            re.IGNORECASE | re.MULTILINE
        )

        for match in cpToolchangePattern.finditer(gcodeText):
            toolChanges.append({
                'changeNumber': int(match.group(1)),
                'fromMaterial': match.group(2),
                'toMaterial': match.group(3),
            })

        # Also look for Change ToolX -> ToolY patterns
        # ; Change Tool3 -> Tool2 (layer 126)
        toolChangePattern = re.compile(
            r';\s*Change Tool(\d+)\s*->\s*Tool(\d+)\s*\(layer\s*(\d+)\)',
            re.IGNORECASE
        )

        for match in toolChangePattern.finditer(gcodeText):
            # Find corresponding entry or create new one
            fromTool = int(match.group(1))
            toTool = int(match.group(2))
            layer = int(match.group(3))

            # Check if we already have this from CP TOOLCHANGE
            existing = None
            for tc in toolChanges:
                if 'fromTool' not in tc and 'toTool' not in tc:
                    # If we haven't assigned tools yet, assign them
                    if tc.get('changeNumber') == len([
                        t for t in toolChanges 
                        if 'layer' in t and t['layer'] < layer
                    ]) + 1:
                        existing = tc
                        break

            if existing:
                existing['fromTool'] = fromTool
                existing['toTool'] = toTool
                existing['layer'] = layer
            else:
                toolChanges.append({
                    'fromTool': fromTool,
                    'toTool': toTool,
                    'layer': layer,
                })

        return toolChanges


def extractSnapmakerToolInfo(gcodeText: str) -> Dict[str, Any]:
    """Standalone function to extract tool information from Snapmaker G-code.
    
    This can be used directly without the full extractor infrastructure.
    
    Returns:
        Dict with keys:
        - tools: List of all tools with their info
        - usedTools: List of only the tools that are used
        - summary: Human-readable summary
    """
    from ..gcode_view import GCodeView
    
    lines = gcodeText.split('\n')
    gview = GCodeView(
        lines=lines,
        headLines=lines[:500],  # First 500 lines as header
        attachments={},
        containerType='gcode',
        fileName=None,
        plateNumber=1,
    )
    extractor = SnapmakerToolchangerExtractor()
    result = extractor.extract(gview)
    
    tools = result.fieldValues.get('tools', [])
    usedTools = result.fieldValues.get('usedTools', [])
    
    # Create human-readable summary
    summaryLines = ["Tool Head Configuration:"]
    summaryLines.append("-" * 50)
    summaryLines.append(f"{'Tool':<8} {'Type':<10} {'Color':<12} {'Used (g)':<12} {'Status'}")
    summaryLines.append("-" * 50)
    
    for tool in tools:
        status = "✓ USED" if tool['isUsed'] else "✗ Not used"
        usedG = f"{tool['filamentUsedGrams']:.2f}" if tool['filamentUsedGrams'] else "0.00"
        summaryLines.append(
            f"Tool {tool['toolIndex']:<3} {tool['filamentType'] or 'N/A':<10} "
            f"{tool['filamentColor'] or 'N/A':<12} {usedG:<12} {status}"
        )
    
    summaryLines.append("-" * 50)
    
    totalUsed = sum(t['filamentUsedGrams'] or 0 for t in usedTools)
    summaryLines.append(f"Total filament used: {totalUsed:.2f}g")
    summaryLines.append(f"Tools in use: {len(usedTools)} of {len(tools)}")
    
    return {
        'tools': tools,
        'usedTools': usedTools,
        'summary': '\n'.join(summaryLines),
        'totalFilamentUsedGrams': totalUsed,
        'toolChangeCount': result.fieldValues.get('totalToolChanges', 0),
    }
