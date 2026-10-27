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

    def test_comparison_ring_pixels(self):
        # Sample centers of the two semicircles, away from the pipette.
        def rgb(surface, x, y):
            import sys
            offset = y * surface.get_stride() + x * 4
            pixel = int.from_bytes(surface.get_data()[offset:offset + 4], sys.byteorder)
            return pixel & 0xFFFFFF
        surface = picker.cursor_surface(0xFF0000, 0x0000FF)
        self.assertEqual(rgb(surface, 36, 12), 0xFF0000)
        self.assertEqual(rgb(surface, 36, 60), 0x0000FF)
        initial = picker.cursor_surface(0x12ABCD)
        self.assertEqual(rgb(initial, 36, 12), 0x12ABCD)
        self.assertEqual(rgb(initial, 36, 60), 0x12ABCD)

    def test_palette_rejects_invalid_values_and_duplicates(self):
        original = picker.STATE
        try:
            with tempfile.TemporaryDirectory() as directory:
                picker.STATE = Path(directory) / 'selection.json'
                picker.write_json(picker.STATE.with_name('palette.json'),
                                  [0, 0x12ABCD, 0, True, -1, 0x1000000, '#112233', None])
                self.assertEqual(picker.load_palette(), [0, 0x12ABCD])
                picker.write_json(picker.STATE.with_name('palette.json'), {})
                self.assertEqual(picker.load_palette(), [])
        finally:
            picker.STATE = original

    def test_capture_commands_preserve_click_then_palette_order(self):
        worker = picker.CaptureWorker(None, 1)
        worker.pick('output', .2, .3)
        worker.save_palette()
        worker.move('output', .8, .9)
        self.assertEqual(worker.commands, [('pick', 'output', .2, .3), ('palette',)])
        self.assertEqual(worker.position, ('output', .8, .9))

    def test_palette_file_round_trip(self):
        values = [0, 0x12ABCD, 0xFFFFFF]
        text = picker.palette_text(values, 'My palette\nMore')
        self.assertIn('Name: My palette More\n', text)
        self.assertEqual(picker.parse_palette(text), values)
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('.gpl',):
                path = Path(directory) / ('Okayu purple' + suffix)
                picker.save_palette_file(path, values)
                self.assertIn('Name: Okayu purple\n', path.read_text())
                self.assertEqual(picker.parse_palette(path.read_text()), values)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        self.assertEqual(picker.parse_palette(picker.palette_text([], 'Empty')), [])

    def test_palette_import_validation_and_deduplication(self):
        self.assertEqual(picker.parse_palette('\ufeffGIMP Palette\r\n# comment\r\n1 2 3 One\r\n1 2 3 Duplicate\r\n255 0 8\r\n'),
                         [0x010203, 0xFF0008])
        for content in ['invalid', 'GIMP Palette\n256 0 0', 'GIMP Palette\n-1 2 3',
                        'GIMP Palette\n1 2', 'GIMP Palette\nx y z', 'GIMP Palette\nColumns: 256']:
            with self.subTest(content=content), self.assertRaises(ValueError):
                picker.parse_palette(content)

    def test_pictures_palette_folder_is_created(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(picker.GLib, 'get_user_special_dir', return_value=directory):
                expected = Path(directory) / 'Palette'
                self.assertFalse(expected.exists())
                self.assertEqual(picker.palette_directory(), expected)
                self.assertTrue(expected.is_dir())
                self.assertEqual(picker.palette_directory(), expected)

    def test_saves_always_use_gpl_extension(self):
        for name, expected in [('Purple', 'Purple.gpl'), ('Purple.GPL', 'Purple.gpl'),
                               ('Purple.glp', 'Purple.gpl'), ('Purple.gpl', 'Purple.gpl')]:
            self.assertEqual(picker.palette_destination(Path('/tmp') / name), Path('/tmp') / expected)
