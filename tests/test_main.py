from main import parseGcodeParameters

def testParseGcodeParameters():
    gcodeText = (
        "model printing time = 123\n"
        "total filament weight: 5.6\n"
        "enable_support = True\n"
        "filament_type: PLA\n"
        "layer_height = 0.2\n"
        "nozzle_diameter: 0.4\n"
        "sparse_infill_density = 20\n"
        "printer_model: MK3S"
    )
    result = parseGcodeParameters(gcodeText)
    assert result == {
        'modelPrintingTime': '123',
        'totalFilamentWeight': '5.6',
        'enableSupport': 'True',
        'filamentType': 'PLA',
        'layerHeight': '0.2',
        'nozzleDiameter': '0.4',
        'sparseInfillDensity': '20',
        'printerModel': 'MK3S'
    }
