import sys
import os

# Add parent directory to sys.path to import parsing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parsing.extractors.bambu_gcode import BambuGcodeExtractor
from parsing.extractors.orca_gcode import OrcaGcodeExtractor
from parsing.gcode_view import GCodeView

def test_bambu_extraction():
    print("Testing BambuGcodeExtractor...")
    gcode = """
; HEADER_BLOCK_START
; filament_type = PLA,PETG,PLA
; filament_colour = #FF0000,#00FF00,#0000FF
; total filament weight [g] : 10.5, 20.2, 5.1
; total filament length [mm] : 1000, 2000, 500
; total filament volume [cm^3] : 10, 20, 5
; HEADER_BLOCK_END
"""
    gview = GCodeView(lines=gcode.split('\n'), headLines=gcode.split('\n'), attachments={}, containerType='gcode', fileName='test.gcode', plateNumber=1)
    extractor = BambuGcodeExtractor()
    result = extractor.extract(gview)
    
    analysis = result.fieldValues.get('filamentAnalysis', [])
    print(f"Filament Analysis: {analysis}")
    
    assert len(analysis) == 3
    assert analysis[0]['amsIndex'] == 0
    assert analysis[0]['toolIndex'] == 0
    assert analysis[1]['amsIndex'] == 1
    assert analysis[1]['toolIndex'] == 1
    assert analysis[2]['amsIndex'] == 2
    assert analysis[2]['toolIndex'] == 2
    print("Bambu test passed!")

def test_orca_bambu_mode():
    print("\\nTesting OrcaGcodeExtractor (Bambu/AMS mode)...")
    gcode = """
; printer_model = Bambu Lab X1 Carbon
; filament_type = PLA;TPU
; filament_colour = #FFFFFF;#000000
; filament used [g] = 15.0, 2.5
; filament used [mm] = 1500, 250
; filament used [cm3] = 15, 2.5
"""
    gview = GCodeView(lines=gcode.split('\n'), headLines=gcode.split('\n'), attachments={}, containerType='gcode', fileName='test.gcode', plateNumber=1)
    extractor = OrcaGcodeExtractor()
    result = extractor.extract(gview)
    
    analysis = result.fieldValues.get('filamentAnalysis', [])
    print(f"Filament Analysis: {analysis}")
    
    assert len(analysis) == 2
    assert analysis[0]['amsIndex'] == 0
    assert analysis[0]['toolIndex'] == 0
    assert analysis[1]['amsIndex'] == 1
    assert analysis[1]['toolIndex'] == 1
    print("Orca Bambu mode passed!")

def test_orca_toolchanger_mode():
    print("\\nTesting OrcaGcodeExtractor (Toolchanger mode)...")
    gcode = """
; printer_model = Generic Toolchanger
; filament_type = PLA;PETG
; filament_colour = #FF0000;#00FF00
; filament used [g] = 10.0, 20.0
; filament used [mm] = 1000, 2000
; filament used [cm3] = 10, 20
"""
    gview = GCodeView(lines=gcode.split('\n'), headLines=gcode.split('\n'), attachments={}, containerType='gcode', fileName='test.gcode', plateNumber=1)
    extractor = OrcaGcodeExtractor()
    result = extractor.extract(gview)
    
    analysis = result.fieldValues.get('filamentAnalysis', [])
    print(f"Filament Analysis: {analysis}")
    
    assert len(analysis) == 2
    assert analysis[0]['toolIndex'] == 0
    assert analysis[0]['amsIndex'] == 0
    assert analysis[1]['toolIndex'] == 1
    assert analysis[1]['amsIndex'] == 1
    print("Orca Toolchanger mode passed!")

if __name__ == "__main__":
    try:
        test_bambu_extraction()
        test_orca_bambu_mode()
        test_orca_toolchanger_mode()
        print("\\nAll tests passed successfully!")
    except Exception as e:
        print(f"\\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
