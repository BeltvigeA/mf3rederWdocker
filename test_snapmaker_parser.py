"""Test script for Snapmaker toolchanger G-code parser.

This script demonstrates parsing tool head information from
Snapmaker U1 G-code files.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parsing.extractors.snapmaker_toolchanger import extractSnapmakerToolInfo


def main():
    """Parse the example G-code file and display results."""
    gcode_path = Path(__file__).parent / "ToolchangerExsempel.gcode"
    
    if not gcode_path.exists():
        print(f"Error: G-code file not found at {gcode_path}")
        return 1
    
    print(f"Reading G-code file: {gcode_path}")
    print("=" * 60)
    
    with open(gcode_path, 'r', encoding='utf-8') as f:
        gcode_text = f.read()
    
    # Extract tool information
    result = extractSnapmakerToolInfo(gcode_text)
    
    # Print the summary
    print(result['summary'])
    print()
    
    # Print detailed used tools information
    print("\n📊 Detailed Used Tools:")
    print("=" * 60)
    for tool in result['usedTools']:
        print(f"\n  🔧 Tool {tool['toolIndex']}:")
        print(f"     Filament Type:  {tool['filamentType']}")
        print(f"     Filament Color: {tool['filamentColor']}")
        print(f"     Used (grams):   {tool['filamentUsedGrams']:.2f}g")
        if tool.get('filamentUsedMm'):
            print(f"     Used (mm):      {tool['filamentUsedMm']:.2f}mm")
    
    print("\n" + "=" * 60)
    print(f"📈 Total filament used: {result['totalFilamentUsedGrams']:.2f}g")
    print(f"🔄 Total tool changes:  {result['toolChangeCount']}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
