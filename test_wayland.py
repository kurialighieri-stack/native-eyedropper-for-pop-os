"""Opt-in integration tests: briefly display native windows on your desktop."""
import os
import functools
import subprocess
import re
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
        if self.id().endswith('test_native_focus_colors_and_continuous_blur'):
            environment['WAYLAND_DEBUG'] = 'client'
        with tempfile.TemporaryDirectory() as config:
            environment['XDG_CONFIG_HOME'] = config
            result = subprocess.run([sys.executable, '-m', 'unittest', self.id(), '-v'],
                                    cwd=Path(__file__).resolve().parent, env=environment,
                                    capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('CRITICAL', result.stderr, result.stderr)
        if self.id().endswith('test_native_focus_colors_and_continuous_blur'):
            regions = {}
            blur_count = 0
            for line in result.stderr.splitlines():
                created = re.search(r'create_region\(new id wl_region#(\d+)\)', line)
                if created:
                    regions[created[1]] = []
                added = re.search(r'wl_region#(\d+)\.add\((-?\d+), (-?\d+), (\d+), (\d+)\)', line)
                if added:
                    regions.setdefault(added[1], []).append(tuple(map(int, added.groups()[1:])))
                blurred = re.search(r'set_blur_region\(wl_region#(\d+)\)', line)
                if blurred:
                    rectangles = regions[blurred[1]]
                    self.assertEqual(len(rectangles), 1, 'blur must not be split into scanlines')
                    self.assertEqual(rectangles[0][:2], (0, 0))
                    self.assertGreater(rectangles[0][2], 1)
                    self.assertGreater(rectangles[0][3], 1)
                    blur_count += 1
            self.assertGreaterEqual(blur_count, 2)
            self.assertIn('set_radius(12, 12, 12, 12)', result.stderr)
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
            app.style.glass = 'on'
            app.style.refresh()
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
                                begin.assert_called_once_with(event, 1)
                            event.button.button = 2
                            event.button.state = Gdk.ModifierType(0)
                            with patch.object(window, 'begin_drag') as begin:
                                self.assertTrue(app.handle_event(event))
                                begin.assert_called_once_with(event, 2)
                            event.button.button = 1
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
                with patch.object(app, 'copy_color') as copy:
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

    @isolated_session
    def test_update_formats_languages_preferences_and_zoom(self):
        with tempfile.TemporaryDirectory() as directory:
            original=picker.STATE
            picker.STATE=Path(directory)/'selection.json'
            app=picker.App();app.set_application_id('local.okayu.ColorPickerUpdateTest')
            app.set_flags(app.get_flags()|picker.Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
            try:
                app.show_color(0x12ABCD);app.add_palette();rgb=list(app.palette)
                app.card.next_format.clicked()
                self.assertEqual(app.color_format,'RGB')
                self.assertEqual(app.card.entry.get_text(),'rgb(18, 171, 205)')
                self.assertEqual(app.palette,rgb)
                self.assertEqual(app.palette_window.grid.get_children()[0].get_tooltip_text(),'rgb(18, 171, 205)')
                with patch.object(Gtk.Clipboard,'set_text') as copy,patch.object(Gtk.Clipboard,'store'):
                    app.card.copy_color();self.assertEqual(copy.call_args.args[0],'rgb(18, 171, 205)')
                app.change_format(2);self.assertEqual(app.color_format,'CMYK')
                self.assertTrue(app.card.approximation.get_visible())
                app.active=True
                event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.key.keyval=Gdk.KEY_Right
                self.assertTrue(app.handle_event(event));self.assertEqual(app.color_format,'HEX')
                scroll=Gdk.Event.new(Gdk.EventType.SCROLL);scroll.scroll.direction=Gdk.ScrollDirection.UP
                self.assertTrue(app.handle_event(scroll));self.assertEqual(app.zoom.value,8)
                app.pixels=tuple([0x12ABCD]*(picker.PATCH_SIDE*picker.PATCH_SIDE))
                app.pointer_position=(.3,.3);app.refresh_cursor();retained=app.cursor
                for update in range(5):
                    app.pixels=tuple(list(app.pixels));app.pointer_position=(.31,.32);app.refresh_cursor()
                    self.assertIs(app.cursor,retained)
                app.stop();self.assertEqual(app.zoom.value,4);self.assertIsNone(app.pixels)
                app.card.preferences_button.clicked();dialog=app.settings_window
                self.assertIsNotNone(dialog);self.assertFalse(app.card.get_visible())
                grid=dialog.get_content_area().get_children()[0]
                language=grid.get_child_at(1,0);language.set_active_id('es')
                self.assertEqual(app.card.title_label.get_text(),'Color seleccionado')
                self.assertEqual(app.palette_window.save_button.get_tooltip_text(),'Guardar paleta')
                self.assertFalse(app.palette_window.get_visible())
                grid=dialog.get_content_area().get_children()[0]
                grid.get_child_at(1,0).set_active_id('pt_BR')
                self.assertEqual(app.card.title_label.get_text(),'Cor selecionada')
                self.assertEqual(app.palette_window.save_button.get_tooltip_text(),'Salvar paleta')
                grid=dialog.get_content_area().get_children()[0]
                grid.get_child_at(1,1).set_active_id('off');self.assertFalse(app.style.frosted)
                dialog.response(Gtk.ResponseType.CLOSE)
                self.assertIsNone(app.settings_window);self.assertTrue(app.card.get_visible())
                self.assertEqual(app.palette,rgb)
                app.palette_window.clear_button.clicked()
                self.assertEqual(app.palette_window.action_dialog.get_property('text'),'Limpar a paleta atual?')
                app.palette_window.action_dialog.response(Gtk.ResponseType.CANCEL)
            finally:
                app.stop()
                if app.settings_window:app.settings_window.destroy()
                for window in app.windows():window.destroy()
                app.style.close()
                picker.STATE=original

    @isolated_session
    def test_cursor_and_magnifier_are_excluded_from_real_capture(self):
        import ctypes
        windows=[];loop=GLib.MainLoop();errors=[]
        display=Gdk.Display.get_default()
        # A deliberately magenta cursor magnifier over uniform teal must not
        # contaminate the captured image, irrespective of physical pointer position.
        pixels=[0xFF00FF]*(picker.PATCH_SIDE*picker.PATCH_SIDE)
        cursor=picker.cursor_image(0xFFFFFF,0xFF0000,pixels,16)
        for i in range(display.get_n_monitors()):
            window=Gtk.Window();window.set_decorated(False);window.set_app_paintable(True)
            Layer.init_for_window(window);Layer.set_monitor(window,display.get_monitor(i))
            Layer.set_layer(window,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(window,-1)
            Layer.set_keyboard_mode(window,Layer.KeyboardMode.NONE)
            for edge in (Layer.Edge.TOP,Layer.Edge.BOTTOM,Layer.Edge.LEFT,Layer.Edge.RIGHT):Layer.set_anchor(window,edge,True)
            def draw(widget,cr):
                cr.set_source_rgb(0x12/255,0x34/255,0x56/255);cr.paint();return True
            window.connect('draw',draw)
            window.connect('realize',lambda widget:widget.get_window().set_cursor(cursor))
            window.show_all();windows.append(window)
        def capture():
            lib=ctypes.CDLL(str(picker.ROOT/'libpixel-capture.so'))
            lib.pixel_open.restype=ctypes.c_void_p
            lib.pixel_outputs.argtypes=[ctypes.c_void_p];lib.pixel_outputs.restype=ctypes.c_char_p
            lib.pixel_refresh.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            lib.pixel_read.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_double,ctypes.c_double,ctypes.POINTER(ctypes.c_uint32)]
            lib.pixel_region.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_double,ctypes.c_double,ctypes.c_int,ctypes.POINTER(ctypes.c_uint32)]
            lib.pixel_close.argtypes=[ctypes.c_void_p]
            lib.pixel_backend.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            ctx=lib.pixel_open()
            try:
                self.assertTrue(ctx)
                for output in lib.pixel_outputs(ctx).splitlines():
                    result=-5
                    for attempt in range(5):
                        result=lib.pixel_refresh(ctx,output)
                        if result==0:break
                    self.assertEqual(result,0)
                    self.assertEqual(lib.pixel_backend(ctx,output),1)
                    value=ctypes.c_uint32()
                    for x in range(64):
                        for y in range(36):
                            self.assertEqual(lib.pixel_read(ctx,output,(x+.5)/64,(y+.5)/36,ctypes.byref(value)),0)
                            self.assertEqual(value.value,0x123456)
                    patch_pixels=(ctypes.c_uint32*(picker.PATCH_SIDE*picker.PATCH_SIDE))()
                    self.assertEqual(lib.pixel_region(ctx,output,.5,.5,picker.PATCH_SIDE,patch_pixels),0)
                    self.assertEqual(set(patch_pixels),{0x123456})
            except Exception as error:errors.append(error)
            finally:
                if ctx:lib.pixel_close(ctx)
                loop.quit()
            return False
        try:
            GLib.timeout_add(350,capture);loop.run()
            if errors:raise errors[0]
        finally:
            for window in windows:window.destroy()

    @isolated_session
    def test_live_sampler_keeps_cursor_visible_during_readback(self):
        import ctypes
        with tempfile.TemporaryDirectory() as directory:
            original=picker.STATE;picker.STATE=Path(directory)/'selection.json'
            app=picker.App();app.set_application_id('local.okayu.CursorGuardTest')
            app.set_flags(app.get_flags()|picker.Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
            patches=[];display=Gdk.Display.get_default();loop=GLib.MainLoop();errors=[]
            for i in range(display.get_n_monitors()):
                window=Gtk.Window();window.set_decorated(False);window.set_app_paintable(True)
                Layer.init_for_window(window);Layer.set_monitor(window,display.get_monitor(i));Layer.set_layer(window,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(window,-1);Layer.set_keyboard_mode(window,Layer.KeyboardMode.NONE)
                for edge in (Layer.Edge.TOP,Layer.Edge.BOTTOM,Layer.Edge.LEFT,Layer.Edge.RIGHT):Layer.set_anchor(window,edge,True)
                def draw(widget,cr):cr.set_source_rgb(0x12/255,0x34/255,0x56/255);cr.paint();return True
                window.connect('draw',draw);window.show_all();patches.append(window)
            actual=ctypes.CDLL(str(picker.ROOT/'libpixel-capture.so'))
            actual.pixel_refresh.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            actual.pixel_backend.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            captures=[];picks=[]
            def refresh(context,output):
                self.assertIsNotNone(app.cursor)
                self.assertNotEqual(app.cursor.get_cursor_type(),Gdk.CursorType.BLANK_CURSOR)
                for overlay in app.overlays:
                    self.assertEqual(overlay.get_window().get_cursor(),app.cursor)
                captures.append(output)
                result=actual.pixel_refresh(context,output)
                if result==0:self.assertEqual(actual.pixel_backend(context,output),1,'COSMIC must render the workspace without cursors')
                return result
            class Library:
                pixel_refresh=staticmethod(refresh)
                def __getattr__(self,name):return getattr(actual,name)
            real_sample=app.sample_ready
            def sample(generation,name,value,picked,pixels=None,position=(.5,.5)):
                self.assertEqual(value,0x123456)
                self.assertEqual(set(pixels),{0x123456})
                if picked:picks.append(value)
                return real_sample(generation,name,value,picked,pixels,position)
            def show(value,monitor=None):app.selected=value
            started=time.monotonic();state={'queued':False}
            def tick():
                try:
                    if time.monotonic()-started>8:raise AssertionError('cursor-guard capture timeout')
                    if not app.active:app.toggle()
                    if app.overlays and not state['queued']:
                        self.assertFalse(Gtk.Settings.get_default().get_property('gtk-enable-tooltips'))
                        for overlay in app.overlays:
                            app.worker.pick(overlay.output_name,.25,.25)
                            app.worker.pick(overlay.output_name,.75,.75)
                        state['queued']=True
                    if len(picks)>=display.get_n_monitors()*2:
                        self.assertGreaterEqual(len(captures),len(picks))
                        app.stop()
                        self.assertTrue(Gtk.Settings.get_default().get_property('gtk-enable-tooltips'))
                        loop.quit();return False
                except Exception as error:errors.append(error);loop.quit();return False
                return True
            try:
                with patch.object(picker.ctypes,'CDLL',return_value=Library()),patch.object(app,'sample_ready',side_effect=sample),patch.object(app,'show_color',side_effect=show):
                    GLib.timeout_add(40,tick);loop.run()
                if errors:raise errors[0]
            finally:
                app.stop()
                for window in patches:window.destroy()
                for window in app.windows():window.destroy()
                app.style.close();picker.STATE=original

    @isolated_session
    def test_native_focus_colors_and_continuous_blur(self):
        with tempfile.TemporaryDirectory() as directory:
            original=picker.STATE;picker.STATE=Path(directory)/'selection.json'
            app=picker.App();app.set_application_id('local.okayu.NativeFocusTest')
            app.set_flags(app.get_flags()|picker.Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
            app.style.glass='on';app.style.refresh()
            app.show_color(0x12ABCD);app.add_palette()
            card,palette=app.card,app.palette_window
            loop=GLib.MainLoop();errors=[];state={'stage':0};started=time.monotonic()
            active=Gdk.RGBA();active.parse(app.style.state[8])
            inactive=Gdk.RGBA();inactive.parse(app.style.state[9])
            def color_matches(button,expected):
                actual=button.get_style_context().get_color(button.get_state_flags())
                for component in ('red','green','blue','alpha'):
                    self.assertAlmostEqual(getattr(actual,component),getattr(expected,component),places=4)
            Layer.set_keyboard_mode(card,Layer.KeyboardMode.EXCLUSIVE)
            def tick():
                try:
                    if time.monotonic()-started>5:raise AssertionError('native keyboard-focus transition timeout')
                    if state['stage']==0 and card.get_style_context().has_class('window-active'):
                        color_matches(card.close_button,active)
                        Layer.set_keyboard_mode(card,Layer.KeyboardMode.ON_DEMAND)
                        Layer.set_keyboard_mode(palette,Layer.KeyboardMode.EXCLUSIVE)
                        state['stage']=1
                    elif state['stage']==1 and palette.get_style_context().has_class('window-active') and card.get_style_context().has_class('window-inactive'):
                        color_matches(palette.save_button,active)
                        color_matches(card.close_button,inactive)
                        palette.hide()
                        Layer.set_keyboard_mode(card,Layer.KeyboardMode.EXCLUSIVE)
                        state['stage']=2
                    elif state['stage']==2 and card.get_style_context().has_class('window-active'):
                        color_matches(card.close_button,active)
                        palette.show_all()
                        Layer.set_keyboard_mode(palette,Layer.KeyboardMode.ON_DEMAND)
                        loop.quit();return False
                except Exception as error:errors.append(error);loop.quit();return False
                return True
            try:
                GLib.timeout_add(30,tick);loop.run()
                if errors:raise errors[0]
            finally:
                for window in app.windows():window.destroy()
                app.style.close();picker.STATE=original
