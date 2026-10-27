"""Opt-in integration tests: briefly display native windows on your desktop."""
import os
import functools
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import picker
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell as Layer


def isolated_session(test):
    """GTK/portal application state is process-global; give each scenario its own process."""
    @functools.wraps(test)
    def run(self):
        if os.environ.get('EYEDROPPER_TEST_CHILD') == '1':
            return test(self)
        environment = dict(os.environ, EYEDROPPER_TEST_CHILD='1')
        result = subprocess.run([sys.executable, '-m', 'unittest', self.id(), '-v'],
                                cwd=Path(__file__).resolve().parent, env=environment,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('CRITICAL', result.stderr, result.stderr)
    return run


@unittest.skipUnless(os.environ.get('EYEDROPPER_WAYLAND_TEST') == '1', 'requires an explicitly enabled COSMIC Wayland session')
class WaylandTests(unittest.TestCase):
    @isolated_session
    def test_native_palette_capture_and_window_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            original = picker.STATE
            picker.STATE = Path(directory) / 'selection.json'
            app = picker.App()
            app.set_application_id('local.okayu.ColorPickerIntegrationTest')
            app.set_flags(app.get_flags() | picker.Gio.ApplicationFlags.NON_UNIQUE)
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
                        # Regress the actual Gdk.Event union delivered to event_handler_set.
                        # A .button == 1 comparison fails for this event type.
                        for window in app.windows():
                            event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
                            event.button.window = window.get_window()
                            event.button.button = 1
                            event.button.state = Gdk.ModifierType.MOD4_MASK
                            event.button.x, event.button.y = 20, 20
                            with patch.object(window, 'begin_drag') as begin:
                                self.assertTrue(app.handle_event(event))
                                begin.assert_called_once_with(event)
                            app.active = True
                            event.button.state = Gdk.ModifierType(0)
                            with patch.object(window, 'sample') as sample:
                                self.assertTrue(app.handle_event(event))
                                sample.assert_called_once_with(event, picked=True)
                            event.button.button = 3
                            with patch.object(app, 'request_palette') as save:
                                self.assertTrue(app.handle_event(event))
                                save.assert_called_once()
                            close_event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
                            close_event.button.window = window.close_button.get_event_window()
                            close_event.button.button = 1
                            self.assertFalse(app.handle_event(close_event))
                            app.active = False
                        saved_colors = list(app.palette)
                        app.palette_window.close_button.clicked()
                        self.assertIsNone(app.palette_window)
                        self.assertIsNotNone(app.card)
                        self.assertEqual(app.palette, saved_colors)
                        app.add_palette()
                        self.assertTrue(app.palette_window.get_mapped())
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

    @isolated_session
    def test_palette_toolbar_files_context_menu_and_clear_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            original = picker.STATE
            picker.STATE = Path(directory) / 'state/selection.json'
            app = picker.App()
            app.set_application_id('local.okayu.ColorPickerPaletteFilesTest')
            app.set_flags(app.get_flags() | picker.Gio.ApplicationFlags.NON_UNIQUE)
            app.register(None)
            app.show_color(0x12ABCD)
            app.add_palette()
            app.show_color(0xA1B2C3)
            app.add_palette()
            window = app.palette_window
            initial = list(app.palette)
            try:
                # Toolbar controls sit to the left of the independent close control.
                controls = window.save_button.get_parent().get_children()
                self.assertEqual(controls[:3], [window.save_button, window.load_button, window.clear_button])
                app.active = True
                for control in (window.save_button, window.load_button, window.clear_button):
                    event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
                    event.button.window = control.get_event_window()
                    event.button.button = 1
                    self.assertFalse(app.handle_event(event))
                app.active = False
                menu = window.swatch_menu(0x12ABCD)
                with patch.object(picker, 'copy_hex') as copy:
                    menu.get_children()[0].activate()
                    copy.assert_called_once_with(0x12ABCD)
                menu.get_children()[1].activate()
                self.assertEqual(app.palette, [0xA1B2C3])
                self.assertEqual(app.selected, 0xA1B2C3)
                window.close_menu()
                window.replace_colors(initial)
                window.clear_button.clicked()
                self.assertEqual(app.palette, initial)
                self.assertTrue(window.action_dialog.get_visible())
                self.assertEqual(window.action_dialog.get_response_for_widget(window.action_dialog.get_default_widget()), Gtk.ResponseType.CANCEL)
                window.action_dialog.response(Gtk.ResponseType.CANCEL)
                self.assertEqual(app.palette, initial)
                self.assertTrue(window.get_visible())
                window.clear_button.clicked()
                window.action_dialog.response(Gtk.ResponseType.ACCEPT)
                self.assertEqual(app.palette, [])
                self.assertEqual(picker.load_palette(), [])
                self.assertEqual(app.selected, 0xA1B2C3)
                window.replace_colors(initial)
                # Exercise the actual native chooser, then cancel without user interaction.
                pictures = Path(directory) / 'Pictures'
                with patch.object(picker.GLib, 'get_user_special_dir', return_value=str(pictures)):
                    window.save_button.clicked()
                    self.assertTrue((pictures / 'Palette').is_dir())
                    self.assertFalse(window.get_visible())
                    self.assertIsInstance(window.file_chooser, Gtk.FileChooserNative)
                    loop = GLib.MainLoop()
                    def cancel():
                        window.file_chooser.emit('response', Gtk.ResponseType.CANCEL)
                        loop.quit()
                        return False
                    GLib.timeout_add(150, cancel)
                    loop.run()
                self.assertIsNone(window.file_chooser)
                self.assertTrue(window.get_visible())
                self.assertEqual(app.palette, initial)
                # Accepted filename gets .gpl automatically; the filename determines Name:.
                destination = Path(directory) / 'My purple palette'
                chooser = types.SimpleNamespace(get_filename=lambda: str(destination), destroy=lambda: None)
                window.file_response(chooser, Gtk.ResponseType.ACCEPT, True)
                saved = Path(str(destination) + '.gpl')
                self.assertTrue(saved.is_file())
                self.assertIn('Name: My purple palette\n', saved.read_text())
                window.replace_colors([])
                window.suspend_windows()
                window.finish_file(saved, False)
                self.assertEqual(app.palette, initial)
                self.assertTrue(window.get_visible())
                invalid = Path(directory) / 'bad.gpl'
                invalid.write_text('GIMP Palette\n256 0 0\n')
                with patch.object(window, 'show_file_error') as error:
                    window.finish_file(invalid, False)
                    error.assert_called_once()
                self.assertEqual(app.palette, initial)
                self.assertEqual(picker.parse_palette(saved.read_text()), initial)
            finally:
                app.stop()
                for item in app.windows():
                    item.destroy()
                picker.STATE = original
