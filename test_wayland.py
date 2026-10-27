"""Opt-in integration tests: briefly display native windows on your desktop."""
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import picker
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell as Layer


@unittest.skipUnless(os.environ.get('EYEDROPPER_WAYLAND_TEST') == '1', 'requires an explicitly enabled COSMIC Wayland session')
class WaylandTests(unittest.TestCase):
    def test_native_palette_capture_and_window_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            original = picker.STATE
            picker.STATE = Path(directory) / 'selection.json'
            app = picker.App()
            app.set_application_id('local.okayu.ColorPickerIntegrationTest')
            app.register(None)
            loop = GLib.MainLoop()
            errors = []
            state = {'stage': 0, 'patch': None}
            started = time.monotonic()

            def tick():
                try:
                    if time.monotonic() - started > 8:
                        raise AssertionError('capture/UI timeout')
                    if state['stage'] == 0:
                        app.show_color(0x12ABCD)
                        self.assertTrue(app.add_palette())
                        self.assertFalse(app.add_palette())
                        app.show_color(0xA1B2C3)
                        self.assertTrue(app.add_palette())
                        app.palette_window.grid.get_children()[-1].clicked()
                        self.assertEqual(app.card.entry.get_text(), '#12ABCD')
                        self.assertEqual(picker.load_palette(), [0x12ABCD, 0xA1B2C3])
                        for window in app.windows():
                            # Exercise actual icon construction and every output's drop handler.
                            display = Gdk.Display.get_default()
                            for i in range(display.get_n_monitors()):
                                with patch.object(window, 'local_coords', return_value=(47, 29)), \
                                     patch.object(window, 'drag_begin_with_coordinates', return_value=object()), \
                                     patch.object(Gtk, 'drag_set_icon_surface') as set_icon:
                                    window.begin_drag(None)
                                    self.assertEqual(set_icon.call_args.args[1].get_device_offset(), (-47, -29))
                                    self.assertEqual(len(app.drag_overlays), display.get_n_monitors())
                                    target = app.drag_overlays[i]
                                    with patch.object(Gtk, 'drag_finish'):
                                        target.receive_drop(None, None, 200, 250,
                                            types.SimpleNamespace(get_data=lambda: b'window'), 0, 0)
                                    monitor = target.monitor
                                    app.end_drag()
                                    self.assertEqual(Layer.get_monitor(window), monitor)
                                    self.assertEqual((window.x, window.y), (153, 221))
                                    self.assertEqual(Gtk.Widget.get_opacity(window), 1)
                        app.toggle()
                        state['stage'] = 1
                    elif state['stage'] == 1 and app.overlays:
                        self.assertEqual(len(app.overlays), Gdk.Display.get_default().get_n_monitors())
                        target = app.overlays[0]
                        patch_window = Gtk.Window()
                        patch_window.set_decorated(False)
                        patch_window.set_size_request(120, 120)
                        Layer.init_for_window(patch_window)
                        Layer.set_monitor(patch_window, target.monitor)
                        Layer.set_layer(patch_window, Layer.Layer.OVERLAY)
                        Layer.set_exclusive_zone(patch_window, -1)
                        Layer.set_keyboard_mode(patch_window, Layer.KeyboardMode.NONE)
                        for edge in [Layer.Edge.TOP, Layer.Edge.LEFT]:
                            Layer.set_anchor(patch_window, edge, True)
                            Layer.set_margin(patch_window, edge, 80)
                        def draw(widget, cr):
                            cr.set_source_rgb(0x45 / 255, 0x67 / 255, 0x89 / 255)
                            cr.paint()
                            return True
                        patch_window.connect('draw', draw)
                        patch_window.show_all()
                        state.update(stage=2, patch=patch_window, target=target, when=time.monotonic())
                    elif state['stage'] == 2 and time.monotonic() - state['when'] > .25:
                        target = state['target']
                        # Queue a right-click immediately after the selection, before capture finishes.
                        target.press(None, types.SimpleNamespace(button=1, x=120, y=120))
                        target.press(None, types.SimpleNamespace(button=3))
                        state['stage'] = 3
                    elif state['stage'] == 3 and 0x456789 in app.palette:
                        self.assertEqual(app.selected, 0x456789)
                        self.assertEqual(app.card.entry.get_text(), '#456789')
                        app.stop()
                        self.assertTrue(app.card.get_mapped())
                        self.assertTrue(app.palette_window.get_mapped())
                        state['patch'].destroy()
                        state['patch'] = None
                        # Sample the palette itself through real screen capture.
                        app.toggle()
                        state.update(stage=4, when=time.monotonic())
                    elif state['stage'] == 4 and app.overlays and time.monotonic() - state['when'] > .3:
                        window = app.palette_window
                        button = window.grid.get_children()[-1]
                        x, y = button.translate_coordinates(window, 13, 13)
                        geometry = Layer.get_monitor(window).get_geometry()
                        output = app.output_map[(geometry.x, geometry.y)]
                        app.worker.pick(output, (window.x + x) / geometry.width,
                                        (window.y + y) / geometry.height)
                        state['stage'] = 5
                    elif state['stage'] == 5 and app.selected == 0x12ABCD:
                        app.stop()
                        self.assertTrue(app.card.get_mapped())
                        self.assertTrue(app.palette_window.get_mapped())
                        self.assertEqual(app.card.entry.get_text(), '#12ABCD')
                        loop.quit()
                        return False
                except Exception as error:
                    errors.append(error)
                    loop.quit()
                    return False
                return True

            try:
                GLib.timeout_add(30, tick)
                loop.run()
                if errors:
                    raise errors[0]
            finally:
                app.stop()
                app.end_drag()
                if state['patch']:
                    state['patch'].destroy()
                for window in app.windows():
                    window.destroy()
                picker.STATE = original
