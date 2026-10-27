import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("picker", Path(__file__).resolve().parent / "picker.py")
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)

class ColorTests(unittest.TestCase):
    def test_hex_and_rgb(self):
        self.assertEqual(picker.hex_color(0x12ABCD), "#12ABCD")
        self.assertEqual(picker.hex_color(0), "#000000")
        self.assertEqual(picker.color_rgb(0xFF0080), (1, 0, 128 / 255))

    def test_selection_loading(self):
        original = picker.STATE
        try:
            with tempfile.TemporaryDirectory() as directory:
                picker.STATE = Path(directory) / "selection.json"
                self.assertIsNone(picker.load_selection())
                picker.STATE.write_text(json.dumps({"hex": "#12ABCD"}))
                self.assertEqual(picker.load_selection(), 0x12ABCD)
                for value in ["broken", '{"hex": "#xyzxyz"}', '{}']:
                    picker.STATE.write_text(value)
                    self.assertIsNone(picker.load_selection())
        finally:
            picker.STATE = original
