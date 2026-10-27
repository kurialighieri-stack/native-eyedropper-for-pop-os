#!/usr/bin/python3
"""Native live Wayland eyedropper. Screen pixels remain in anonymous memory."""
import ctypes
import json
import logging
import math
import os
from pathlib import Path
import signal
import sys
import threading

import gi
for name, version in [('Gtk', '3.0'), ('Gdk', '3.0'), ('GtkLayerShell', '0.1')]:
    gi.require_version(name, version)
from gi.repository import Gtk, Gdk, Gio, GLib, GtkLayerShell as Layer
import cairo

ROOT = Path(__file__).parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'okayu-color-picker/selection.json'
MOVE_TARGET = 'application/x-native-eyedropper-window'


def hex_color(value):
    return f'#{value:06X}'


def color_rgb(value):
    return ((value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255)


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value) + '\n')
    temporary.replace(path)


def load_selection():
    try:
        value = read_json(STATE, {})['hex']
        result = int(value[1:], 16)
        return result if len(value) == 7 and value.startswith('#') and 0 <= result <= 0xFFFFFF else None
    except (ValueError, KeyError, TypeError):
        return None


def load_palette():
    values = read_json(STATE.with_name('palette.json'), [])
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(v for v in values if type(v) is int and 0 <= v <= 0xFFFFFF))


def cursor_surface(live, selected=None):
    """Cairo uses downward Y: 0..pi is the lower semicircle."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 72, 72)
    cr = cairo.Context(surface)
    for width, color in [(10, (0, 0, 0)), (8, (1, 1, 1))]:
        cr.set_source_rgb(*color)
        cr.set_line_width(width)
        cr.arc(36, 36, 24, 0, math.tau)
        cr.stroke()
    cr.set_line_width(5)
    for value, start, end in [(live, -math.pi, 0), (live if selected is None else selected, 0, math.pi)]:
        cr.set_source_rgb(*color_rgb(value))
        cr.arc(36, 36, 24, start, end)
        cr.stroke()
    for width, color in [(9, (.03, .02, .05)), (5, (.95, .92, .98))]:
        cr.move_to(36, 36)
        cr.line_to(48, 24)
        cr.set_source_rgb(*color)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(width)
        cr.stroke()
    cr.move_to(44, 21)
    cr.line_to(51, 28)
    cr.set_source_rgb(.03, .02, .05)
    cr.set_line_width(5)
    cr.stroke()
    return surface


def cursor_image(live, selected=None):
    pixbuf = Gdk.pixbuf_get_from_surface(cursor_surface(live, selected), 0, 0, 72, 72)
    return Gdk.Cursor.new_from_pixbuf(Gdk.Display.get_default(), pixbuf, 36, 36)


class CaptureWorker(threading.Thread):
    def __init__(self, app, generation):
        super().__init__(daemon=True)
        self.app, self.generation = app, generation
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.position = None
        self.commands = []

    def move(self, name, x, y):
        with self.lock:
            self.position = (name, x, y)

    def pick(self, name, x, y):
        with self.lock:
            self.commands.append(('pick', name, x, y))
            self.position = (name, x, y)

    def save_palette(self):
        with self.lock:
            self.commands.append(('palette',))

    def run(self):
        ctx = None
        try:
            lib = ctypes.CDLL(str(ROOT / 'libpixel-capture.so'))
            lib.pixel_open.restype = ctypes.c_void_p
            lib.pixel_outputs.argtypes = [ctypes.c_void_p]
            lib.pixel_outputs.restype = ctypes.c_char_p
            lib.pixel_origin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
            lib.pixel_refresh.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lib.pixel_read.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_uint32)]
            lib.pixel_close.argtypes = [ctypes.c_void_p]
            ctx = lib.pixel_open()
            if not ctx:
                raise RuntimeError('COSMIC does not expose the required capture protocol in this session.')
            outputs = {}
            for name in lib.pixel_outputs(ctx).splitlines():
                origin = (ctypes.c_int * 2)()
                lib.pixel_origin(ctx, name, origin)
                if lib.pixel_refresh(ctx, name) != 0:
                    raise RuntimeError('Could not capture output ' + name.decode())
                outputs[tuple(origin)] = name.decode()
            GLib.idle_add(self.app.capture_ready, self.generation, outputs)
            while not self.stop_event.is_set():
                with self.lock:
                    command = self.commands.pop(0) if self.commands else None
                    position = self.position
                if command and command[0] == 'palette':
                    GLib.idle_add(self.app.palette_ready, self.generation)
                    continue
                picked = bool(command and command[0] == 'pick')
                if picked:
                    position = command[1:]
                if position:
                    name, x, y = position
                    encoded = name.encode()
                    result = lib.pixel_refresh(ctx, encoded)
                    value = ctypes.c_uint32()
                    if result == 0 and lib.pixel_read(ctx, encoded, x, y, ctypes.byref(value)) == 0:
                        GLib.idle_add(self.app.sample_ready, self.generation, name, value.value, picked)
                    elif result == -5 and picked:
                        with self.lock:
                            self.commands.insert(0, command)
                    elif result not in (0, -5):
                        raise RuntimeError('The output is no longer available. Reactivate the eyedropper.')
                self.stop_event.wait(.035)
        except Exception as error:
            GLib.idle_add(self.app.capture_error, self.generation, str(error))
        finally:
            if ctx:
                lib.pixel_close(ctx)


class Overlay(Gtk.Window):
    def __init__(self, app, monitor, name, drag_target=False):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app, self.monitor, self.output_name = app, monitor, name
        self.drag_target = drag_target
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_visual(self.get_screen().get_rgba_visual())
        Layer.init_for_window(self)
        Layer.set_namespace(self, 'okayu-eyedropper-drag' if drag_target else 'okayu-eyedropper')
        Layer.set_monitor(self, monitor)
        Layer.set_layer(self, Layer.Layer.OVERLAY)
        Layer.set_exclusive_zone(self, -1)
        for edge in [Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT]:
            Layer.set_anchor(self, edge, True)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.NONE if drag_target else Layer.KeyboardMode.EXCLUSIVE)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect('draw', self.draw)
        if drag_target:
            entries = [Gtk.TargetEntry.new(MOVE_TARGET, Gtk.TargetFlags.SAME_APP, 0)]
            self.drag_dest_set(Gtk.DestDefaults.MOTION, entries, Gdk.DragAction.MOVE)
            self.connect('drag-drop', self.request_drop)
            self.connect('drag-data-received', self.receive_drop)
        else:
            self.connect('motion-notify-event', self.motion)
            self.connect('enter-notify-event', self.motion)
            self.connect('button-press-event', self.press)
            self.connect('key-press-event', self.key)
            self.connect('realize', lambda *_: self.update_cursor())
        self.show_all()

    def draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        return True

    def update_cursor(self):
        if self.get_window():
            self.get_window().set_cursor(self.app.cursor)

    def normalized(self, event):
        return (max(0, min(.999999, event.x / max(1, self.get_allocated_width()))),
                max(0, min(.999999, event.y / max(1, self.get_allocated_height()))))

    def motion(self, widget, event):
        self.app.current_output = self.output_name
        x, y = self.normalized(event)
        if self.app.worker:
            self.app.worker.move(self.output_name, x, y)
        self.update_cursor()
        return True

    def press(self, widget, event):
        if event.button == 1 and self.app.worker:
            self.app.worker.pick(self.output_name, *self.normalized(event))
        elif event.button == 3:
            self.app.request_palette()
        return True

    def key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.app.stop()
        return True

    def request_drop(self, widget, context, x, y, timestamp):
        if not self.app.drag:
            return False
        self.drag_get_data(context, Gdk.Atom.intern(MOVE_TARGET, False), timestamp)
        return True

    def receive_drop(self, widget, context, x, y, selection, info, timestamp):
        drag = self.app.drag
        success = bool(drag and selection.get_data() == b'window')
        if success:
            window, hot_x, hot_y = drag
            self.app.drop_position = (self.monitor, round(x - hot_x), round(y - hot_y))
        Gtk.drag_finish(context, success, False, timestamp)


class FloatingWindow(Gtk.Window):
    """Layer-shell placement plus a compositor-owned, cross-output drag icon."""
    def __init__(self, app, monitor, kind, x, y):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app, self.kind = app, kind
        self.x, self.y = x, y
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.get_style_context().add_class('color-card')
        self.close_button = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
        self.close_button.set_relief(Gtk.ReliefStyle.NONE)
        title = 'Close palette' if kind == 'palette' else 'Close selected color'
        self.close_button.set_tooltip_text(title)
        self.close_button.get_accessible().set_name(title)
        self.close_button.connect('clicked', lambda *_: self.destroy())
        Layer.init_for_window(self)
        Layer.set_namespace(self, 'okayu-color-' + kind)
        Layer.set_layer(self, Layer.Layer.OVERLAY)
        Layer.set_exclusive_zone(self, -1)
        Layer.set_anchor(self, Layer.Edge.TOP, True)
        Layer.set_anchor(self, Layer.Edge.LEFT, True)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.ON_DEMAND)
        saved = app.positions.get(kind, {})
        if isinstance(saved, dict):
            display = Gdk.Display.get_default()
            candidates = [display.get_monitor(i) for i in range(display.get_n_monitors())]
            matching = [m for m in candidates if m.get_model() == saved.get('model')]
            for candidate in candidates:
                geometry = candidate.get_geometry()
                origin = [geometry.x, geometry.y]
                output = app.output_map.get(tuple(origin))
                if ((saved.get('output') and output == saved['output']) or
                        origin == saved.get('origin') or (len(matching) == 1 and candidate == matching[0])):
                    monitor = candidate
                    if type(saved.get('x')) is int and type(saved.get('y')) is int:
                        x, y = saved['x'], saved['y']
                    break
        g = monitor.get_geometry()
        # Recover an off-screen remembered window after resolution/layout changes.
        self.place(monitor, max(0, min(x, g.width - 60)), max(0, min(y, g.height - 40)))
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect('realize', lambda *_: self.update_cursor())
        self.connect('drag-end', self.drag_end)
        self.connect('drag-failed', lambda *_: True)
        self.connect('drag-data-get', self.drag_data)
        self.connect('key-press-event', self.key)

    def place(self, monitor, x, y):
        self.x, self.y = int(x), int(y)
        Layer.set_monitor(self, monitor)
        Layer.set_margin(self, Layer.Edge.LEFT, self.x)
        Layer.set_margin(self, Layer.Edge.TOP, self.y)

    def save_position(self):
        monitor = Layer.get_monitor(self)
        g = monitor.get_geometry()
        self.app.positions[self.kind] = {'output': self.app.output_map.get((g.x, g.y)),
            'model': monitor.get_model(), 'origin': [g.x, g.y], 'x': self.x, 'y': self.y}
        write_json(STATE.with_name('windows.json'), self.app.positions)

    def local_coords(self, event):
        source = Gtk.get_event_widget(event)
        x, y = event.x, event.y
        if source and source is not self:
            translated = source.translate_coordinates(self, int(x), int(y))
            if translated:
                x, y = translated
        return x, y

    def sample(self, event, picked=False):
        if not self.app.worker:
            return
        monitor = Layer.get_monitor(self)
        g = monitor.get_geometry()
        name = self.app.output_map.get((g.x, g.y))
        if not name:
            return
        x, y = self.local_coords(event)
        x, y = max(0, min(.999999, (self.x + x) / g.width)), max(0, min(.999999, (self.y + y) / g.height))
        self.app.current_output = name
        if picked:
            self.app.worker.pick(name, x, y)
        else:
            self.app.worker.move(name, x, y)

    def update_cursor(self):
        if self.get_window():
            self.get_window().set_cursor(self.app.cursor if self.app.active else None)

    def begin_drag(self, event):
        if self.app.drag:
            return
        x, y = self.local_coords(event)
        self.check_resize()
        self.size_allocate(self.get_allocation())
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.get_allocated_width(), self.get_allocated_height())
        self.draw(cairo.Context(surface))
        surface.set_device_offset(-x, -y)
        self.app.drop_position = None
        self.app.drag = (self, x, y)
        targets = Gtk.TargetList.new([Gtk.TargetEntry.new(MOVE_TARGET, Gtk.TargetFlags.SAME_APP, 0)])
        context = self.drag_begin_with_coordinates(targets, Gdk.DragAction.MOVE, 1, event, int(x), int(y))
        if not context:
            self.app.drag = None
            return
        Gtk.drag_set_icon_surface(context, surface)
        # Keep the source mapped for the Wayland drag's lifetime; only the icon is visible.
        Gtk.Widget.set_opacity(self, 0)
        display = Gdk.Display.get_default()
        self.app.drag_overlays = [Overlay(self.app, display.get_monitor(i), None, True)
                                  for i in range(display.get_n_monitors())]

    def drag_data(self, widget, context, selection, info, timestamp):
        selection.set(selection.get_target(), 8, b'window')

    def drag_end(self, *_):
        # Defer target destruction until GTK has finished dispatching the drop.
        GLib.idle_add(self.app.end_drag)

    def key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.app.active:
                self.app.stop()
            else:
                self.destroy()
            return True
        return False


class ColorCard(FloatingWindow):
    def __init__(self, app, monitor):
        super().__init__(app, monitor, 'selection', max(0, monitor.get_geometry().width - 354), 44)
        self.value = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(16)
        self.add(box)
        header = Gtk.Box(spacing=12)
        label = Gtk.Label(label='Selected color')
        label.set_xalign(0)
        header.pack_start(label, True, True, 0)
        header.pack_end(self.close_button, False, False, 0)
        box.pack_start(header, False, False, 0)
        row = Gtk.Box(spacing=14)
        self.swatch = Gtk.DrawingArea()
        self.swatch.set_size_request(76, 76)
        self.swatch.connect('draw', self.draw_swatch)
        row.pack_start(self.swatch, False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.entry = Gtk.Entry()
        self.entry.set_editable(False)
        self.entry.set_width_chars(9)
        self.entry.get_style_context().add_class('color-code')
        right.pack_start(self.entry, False, False, 0)
        self.copy_button = Gtk.Button(label='Copy HEX')
        self.copy_button.connect('clicked', self.copy_color)
        right.pack_start(self.copy_button, False, False, 0)
        row.pack_start(right, True, True, 0)
        box.pack_start(row, False, False, 0)
        hint = Gtk.Label(label='Super+Alt+8: toggle · Super+drag: move')
        hint.get_style_context().add_class('color-hint')
        box.pack_start(hint, False, False, 0)
        self.connect('destroy', self.closed)
        self.set_size_request(330, -1)

    def draw_swatch(self, widget, cr):
        cr.set_source_rgb(*color_rgb(self.value))
        cr.paint()
        return True

    def set_color(self, value):
        self.value = value
        self.entry.set_text(hex_color(value))
        self.swatch.queue_draw()
        self.copy_button.set_label('Copy HEX')

    def copy_color(self, *_):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(hex_color(self.value), -1)
        clipboard.store()
        self.copy_button.set_label('Copied')

    def closed(self, *_):
        if self.app.card is self:
            self.app.card = None


class PaletteWindow(FloatingWindow):
    def __init__(self, app, monitor):
        card = app.card
        x = card.x if card else max(0, monitor.get_geometry().width - 354)
        y = card.y + max(card.get_allocated_height(), card.get_preferred_height()[1]) + 10 if card else 260
        super().__init__(app, monitor, 'palette', x, y)
        self.set_tooltip_text('Click a color to select it · Super+drag to move · Escape to close')
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_max_content_height(172)
        self.scroll.set_min_content_height(40)
        self.scroll.set_min_content_width(284)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Gtk.Box()
        header.pack_end(self.close_button, False, False, 2)
        box.pack_start(header, False, False, 0)
        box.pack_start(self.scroll, True, True, 0)
        self.add(box)
        self.grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        self.grid.set_border_width(8)
        self.scroll.add(self.grid)
        self.connect('destroy', self.closed)
        self.rebuild()

    def rebuild(self):
        for child in self.grid.get_children():
            child.destroy()
        for i, value in enumerate(self.app.palette):
            button = Gtk.Button()
            button.get_style_context().add_class('palette-color')
            button.set_tooltip_text(hex_color(value))
            button.get_accessible().set_name(hex_color(value))
            swatch = Gtk.DrawingArea()
            swatch.set_size_request(26, 26)
            def draw(widget, cr, value=value):
                cr.set_source_rgb(*color_rgb(value))
                cr.paint()
                return True
            swatch.connect('draw', draw)
            button.add(swatch)
            button.connect('clicked', lambda _, value=value: self.app.show_color(value))
            self.grid.attach(button, i % 8, i // 8, 1, 1)
        self.show_all()

    def closed(self, *_):
        if self.app.palette_window is self:
            self.app.palette_window = None


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.okayu.ColorPicker', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.active = False
        self.worker = None
        self.generation = 0
        self.overlays = []
        self.card = None
        self.palette_window = None
        self.palette = load_palette()
        self.positions = read_json(STATE.with_name('windows.json'), {})
        if not isinstance(self.positions, dict):
            self.positions = {}
        self.selected = load_selection()
        self.live_color = self.selected if self.selected is not None else 0xA785D8
        self.current_output = None
        self.cursor = None
        self.output_map = {}
        self.drag = None
        self.drop_position = None
        self.drag_overlays = []

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.css = Gtk.CssProvider()
        self.css.load_from_data(b"""
            window.color-card { background-color: #241b33; color: #eee7f5; border: 1px solid #9381a3; border-radius: 12px; }
            .color-card label, .color-card button { color: #eee7f5; }
            .color-card entry { color: #eee7f5; background-color: #15111e; }
            .color-card .color-code { font: bold 16pt monospace; }
            .color-card .color-hint { color: #c7b7e6; font-size: 9pt; }
            .color-card button.palette-color { padding: 0; min-width: 0; min-height: 0; border-radius: 3px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 40)
        Gdk.event_handler_set(self.input_event)

    def input_event(self, event, *_):
        try:
            if self.handle_event(event):
                return
        except Exception:
            logging.exception('Could not handle pointer event')
        Gtk.main_do_event(event)

    def handle_event(self, event):
        child = Gtk.get_event_widget(event)
        window = child.get_toplevel() if child else None
        if window not in (self.card, self.palette_window) or window is None:
            return False
        # event_handler_set receives a Gdk.Event union, NOT a Gdk.EventButton.
        # Its .button member is a structure; use accessors for the actual number.
        valid_button, button = event.get_button()
        valid_state, modifiers = event.get_state()
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if (not self.active and valid_button and button == 1 and valid_state and
                    modifiers & (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK)):
                window.begin_drag(event)
                return True
        # Close controls must remain usable even while sampling.
        target = child
        while target and target is not window:
            if target is window.close_button:
                if event.type in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
                    return False
                break
            target = target.get_parent()
        if self.active and event.type == Gdk.EventType.BUTTON_PRESS:
            if valid_button and button == 1:
                window.sample(event, picked=True)
            elif valid_button and button == 3:
                self.request_palette()
            return True
        if self.active and event.type in (Gdk.EventType.MOTION_NOTIFY, Gdk.EventType.ENTER_NOTIFY):
            window.sample(event)
        if self.active and event.type == Gdk.EventType.BUTTON_RELEASE:
            return True
        return False

    def windows(self):
        return [window for window in (self.card, self.palette_window) if window]

    def refresh_cursor(self):
        self.cursor = cursor_image(self.live_color, self.selected)
        for window in self.overlays + self.windows():
            window.update_cursor()

    def toggle(self):
        if self.active:
            self.stop()
        elif not self.drag:
            self.active = True
            self.generation += 1
            self.refresh_cursor()
            self.worker = CaptureWorker(self, self.generation)
            self.worker.start()

    def stop(self):
        self.active = False
        self.generation += 1
        if self.worker:
            self.worker.stop_event.set()
            self.worker = None
        for window in self.overlays:
            window.destroy()
        self.overlays = []
        self.current_output = None
        for window in self.windows():
            window.update_cursor()

    def end_drag(self):
        drag, self.drag = self.drag, None
        if drag:
            window = drag[0]
            if self.drop_position:
                window.place(*self.drop_position)
                window.save_position()
            Gtk.Widget.set_opacity(window, 1)
        self.drop_position = None
        overlays, self.drag_overlays = self.drag_overlays, []
        for overlay in overlays:
            overlay.destroy()

    def capture_ready(self, generation, outputs):
        if not self.active or generation != self.generation:
            return False
        self.output_map = outputs
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            monitor = display.get_monitor(i)
            g = monitor.get_geometry()
            name = outputs.get((g.x, g.y))
            if name:
                self.overlays.append(Overlay(self, monitor, name))
        if not self.overlays:
            self.capture_error(generation, 'Could not match monitors to COSMIC capture outputs.')
        else:
            for window in self.windows():
                window.hide()
                window.show_all()
                window.update_cursor()
        return False

    def sample_ready(self, generation, name, value, picked):
        if not self.active or generation != self.generation:
            return False
        if name == self.current_output or picked:
            self.live_color = value
        if picked:
            monitor = next((w.monitor for w in self.overlays if w.output_name == name), Gdk.Display.get_default().get_monitor(0))
            self.show_color(value, monitor)
        self.refresh_cursor()
        return False

    def show_color(self, value, monitor=None):
        self.selected = value
        write_json(STATE, {'hex': hex_color(value)})
        if not self.card:
            self.card = ColorCard(self, monitor or Gdk.Display.get_default().get_monitor(0))
        self.card.set_color(value)
        self.card.show_all()
        self.card.update_cursor()
        if self.active:
            self.refresh_cursor()

    def request_palette(self):
        # Serialize right-clicks after queued capture clicks, even on slow outputs.
        if self.worker:
            self.worker.save_palette()

    def palette_ready(self, generation):
        if self.active and generation == self.generation:
            self.add_palette()
        return False

    def add_palette(self):
        if self.selected is None:
            return False
        added = self.selected not in self.palette
        if added:
            self.palette.append(self.selected)
            write_json(STATE.with_name('palette.json'), self.palette)
        if not self.palette_window:
            monitor = Layer.get_monitor(self.card) if self.card else Gdk.Display.get_default().get_monitor(0)
            self.palette_window = PaletteWindow(self, monitor)
        elif added:
            self.palette_window.rebuild()
        self.palette_window.show_all()
        self.palette_window.update_cursor()
        return added

    def capture_error(self, generation, message):
        if generation != self.generation:
            return False
        self.stop()
        logging.error('%s', message)
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE, text='Could not activate the eyedropper')
        dialog.format_secondary_text(message)
        dialog.connect('response', lambda d, *_: d.destroy())
        dialog.show_all()
        return False

    def do_command_line(self, command):
        args = command.get_arguments()[1:]
        if '--quit' in args:
            self.stop()
            self.quit()
        elif '--status' in args:
            command.print_literal(json.dumps({'active': self.active, 'overlays': len(self.overlays),
                'selected': None if self.selected is None else hex_color(self.selected), 'window_open': self.card is not None,
                'palette': [hex_color(v) for v in self.palette], 'palette_open': self.palette_window is not None,
                'dragging': self.drag is not None}) + '\n')
        elif '--idle' in args:
            pass
        elif '--show-color' in args:
            try:
                value = int(args[args.index('--show-color') + 1].lstrip('#'), 16)
                if not 0 <= value <= 0xFFFFFF:
                    return 2
                self.show_color(value)
            except (ValueError, IndexError):
                return 2
        else:
            self.toggle()
        return 0

    def do_shutdown(self):
        self.stop()
        self.end_drag()
        for window in self.windows():
            window.destroy()
        Gtk.Application.do_shutdown(self)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    app = App()
    signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(app.quit))
    sys.exit(app.run(sys.argv))
