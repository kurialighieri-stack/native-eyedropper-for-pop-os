"""Follow the generated COSMIC theme and opt into compositor-owned blur."""
import ctypes
import logging
import os
from pathlib import Path
import re
import math

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib


def pointer(obj):
    get = ctypes.pythonapi.PyCapsule_GetPointer
    get.restype = ctypes.c_void_p
    get.argtypes = [ctypes.py_object, ctypes.c_char_p]
    return get(obj.__gpointer__, None)


def rgba(value):
    if not re.fullmatch(r'#[0-9a-fA-F]{8}', value):
        raise ValueError('Invalid COSMIC color')
    r,g,b,a = (int(value[i:i+2],16) for i in (1,3,5,7))
    return f'rgba({r},{g},{b},{a/255:.5f})'


def color(text, name, fallback):
    # Theme files use RON. Only read fixed root-level scalar colors, never eval.
    match = re.search(r'^    '+re.escape(name)+r':\s*"(#[0-9a-fA-F]{8})"', text, re.M)
    return match.group(1) if match else fallback


def optional_color(text, fallback):
    """Read COSMIC's Option<Srgba> accent text without evaluating RON."""
    if not text.lstrip().startswith('Some('):
        return fallback
    channels = {}
    for name, value in re.findall(r'\b(red|green|blue|alpha):\s*([0-9.eE+-]+)', text):
        try:
            number = float(value)
        except ValueError:
            return fallback
        if not math.isfinite(number) or not 0 <= number <= 1:
            return fallback
        channels[name] = round(number * 255)
    if set(channels) != {'red', 'green', 'blue', 'alpha'}:
        return fallback
    return '#' + ''.join(f'{channels[name]:02X}' for name in ('red', 'green', 'blue', 'alpha'))


CORNER_RADIUS = 12


class CosmicStyle:
    def __init__(self, root=None, glass="auto"):
        self.glass = glass
        self.root = Path(root) if root else Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'cosmic'
        self.monitors = []
        self.watched = set()
        self.pending = 0
        self.surfaces = {}
        self.widgets = set()
        self.lib = None
        self.ctx = None
        self.frosted = False
        self.css = Gtk.CssProvider()
        self.state = None
        try:
            lib = ctypes.CDLL(str(Path(__file__).with_name('libcosmic-effects.so')))
            lib.cf_init.argtypes = [ctypes.c_void_p]
            lib.cf_init.restype = ctypes.c_void_p
            lib.cf_free.argtypes = [ctypes.c_void_p]
            lib.cf_supported.argtypes = [ctypes.c_void_p]
            lib.cf_supported.restype = ctypes.c_int
            lib.cf_attach.argtypes = [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
            lib.cf_attach.restype = ctypes.c_void_p
            lib.cf_surface.argtypes = [ctypes.c_void_p]
            lib.cf_surface.restype = ctypes.c_void_p
            lib.cf_update.argtypes = [ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_int]*4)]
            lib.cf_detach.argtypes = [ctypes.c_void_p]
            self.ctx = lib.cf_init(pointer(Gdk.Display.get_default()))
            if self.ctx:
                self.lib = lib
        except (OSError,AttributeError,ValueError) as exc:
            logging.warning('Native blur unavailable: %s',exc)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+20)
        self.refresh()
        self.watch()
        logging.info('COSMIC: blur protocol=%s, frosted=%s', self.supported, self.frosted)

    @property
    def supported(self):
        return bool(self.lib and self.ctx and self.lib.cf_supported(self.ctx))

    def read(self, folder, key, fallback=''):
        try:
            return (self.root/folder/key).read_text().strip()
        except OSError:
            try:
                return (Path('/usr/share/cosmic')/folder/key).read_text().strip()
            except OSError:
                return fallback

    def watch(self):
        # Watch the parent too: theme directories may be created on first use.
        paths = [self.root, self.root/'com.system76.CosmicTheme.Mode', self.root/'com.system76.CosmicTheme.Mode/v1']
        paths += [self.root/f'com.system76.CosmicTheme.{mode}' for mode in ('Dark','Light')]
        paths += [self.root/f'com.system76.CosmicTheme.{mode}/v2' for mode in ('Dark','Light')]
        for path in paths:
            if path in self.watched or not path.is_dir():
                continue
            try:
                monitor = Gio.File.new_for_path(str(path)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES,None)
                monitor.set_rate_limit(150)
                monitor.connect('changed',self.changed)
                self.monitors.append(monitor)
                self.watched.add(path)
            except GLib.Error:
                pass

    def changed(self,*_):
        if not self.pending:
            def update():
                self.pending = 0
                self.watch()
                self.refresh()
                return False
            self.pending = GLib.timeout_add(160,update)

    def refresh(self):
        dark = self.read('com.system76.CosmicTheme.Mode/v1','is_dark','true') != 'false'
        folder = f'com.system76.CosmicTheme.{"Dark" if dark else "Light"}/v2'
        enabled = self.read(folder,'frosted_windows',self.read(folder,'frosted_system_interface','false')) == 'true'
        self.frosted = (enabled if self.glass == 'auto' else self.glass == 'on') and self.supported
        prefix = 'transparent_' if self.frosted else ''
        bg = self.read(folder,prefix+'background')
        primary = self.read(folder,prefix+'primary')
        fallback = '#242936FF' if dark else '#F4F5F8FF'
        foreground = '#F4F5FAFF' if dark else '#20242EFF'
        base = color(bg,'base',fallback)
        tile_base = color(primary,'base',fallback)
        background = rgba(base if self.frosted else base[:7]+'FF')
        tile = rgba(tile_base if self.frosted else tile_base[:7]+'FF')
        fg = rgba(color(bg,'on',foreground))
        divider = rgba(color(bg,'divider','#FFFFFF33' if dark else '#00000033'))
        hover = rgba('#FFFFFF22' if dark else '#00000014')
        entry = rgba('#00000033' if dark else '#FFFFFF66')
        accent = rgba(color(self.read(folder,'accent'),'base','#A785D8FF'))
        icon = self.read(folder, 'icon_button')
        accent_raw = color(self.read(folder, 'accent'), 'base', '#A785D8FF')
        active_icon = rgba(optional_color(self.read(folder, 'accent_text'), accent_raw))
        inactive_icon = rgba(color(icon, 'on_disabled', '#AAAAAAA6' if dark else '#555555A6'))
        icon_hover = rgba(color(icon, 'hover', '#FFFFFF22' if dark else '#00000014'))
        icon_pressed = rgba(color(icon, 'pressed', '#00000044' if dark else '#00000022'))
        new_state = (background,tile,fg,divider,hover,entry,accent,self.frosted,active_icon,inactive_icon,icon_hover,icon_pressed)
        if new_state != self.state:
            css = f'''
            window.color-card {{ background-color: {background}; color: {fg}; border: 1px solid {divider}; border-radius: {CORNER_RADIUS}px; }}
            .color-card label, .color-card button, .color-card entry {{ color: {fg}; }}
            .color-card button:hover, .color-card button:focus {{ background-color: {hover}; border-color: {accent}; }}
            .color-card entry {{ background-color: {entry}; border-color: {divider}; }}
            .color-card .color-code {{ font: bold 12pt monospace; }}
            .color-card .color-hint {{ font-size: 9pt; }}
            .color-card button.palette-color {{ padding: 0; min-width: 0; min-height: 0; border-radius: 3px; }}
            .color-card .format-name {{ color: {accent}; font-weight: bold; }}
            .color-card button.window-control {{
                background-color: transparent; background-image: none; box-shadow: none;
                border: 1px solid transparent; border-radius: 8px;
                padding: 4px; min-width: 20px; min-height: 20px;
            }}
            .color-card.window-active button.window-control,
            .color-card.window-active button.window-control image {{ color: {active_icon}; }}
            .color-card.window-inactive button.window-control,
            .color-card.window-inactive button.window-control image {{ color: {inactive_icon}; }}
            .color-card button.window-control:hover {{ background-color: {icon_hover}; border-color: transparent; }}
            .color-card button.window-control:active {{ background-color: {icon_pressed}; border-color: transparent; }}
            .color-card button.window-control:focus {{ border-color: {accent}; }}
            .color-card.window-inactive button.window-control:focus {{ border-color: transparent; }}
            '''
            self.css.load_from_data(css.encode())
            self.state = new_state
            for widget in list(self.widgets):
                self.apply(widget,force=True)
                widget.queue_draw()

    def track(self, widget):
        if widget in self.widgets:
            return
        self.widgets.add(widget)
        widget.connect('map',lambda w: self.apply(w,force=True))
        widget.connect('size-allocate',lambda w,alloc: self.apply(w))
        widget.connect('unmap',self.detach)
        widget.connect('focus-in-event', self.focus_in)
        widget.connect('focus-out-event', self.focus_out)
        widget.connect('notify::is-active', self.active_changed)
        self.set_focused(widget, widget.is_active())
        widget.connect('destroy',self.forget)
        if widget.get_mapped():
            self.apply(widget,force=True)

    def set_focused(self, widget, active):
        context = widget.get_style_context()
        context.remove_class('window-inactive' if active else 'window-active')
        context.add_class('window-active' if active else 'window-inactive')
        widget.queue_draw()

    def focus_in(self, widget, event):
        self.set_focused(widget, True)
        return False

    def focus_out(self, widget, event):
        self.set_focused(widget, False)
        return False

    def active_changed(self, widget, parameter):
        self.set_focused(widget, widget.is_active())

    def apply(self,widget,force=False):
        if not self.lib or not self.ctx or not widget.get_mapped():
            return
        window = widget.get_window()
        if not window:
            return
        gdk_pointer = pointer(window)
        native = self.lib.cf_surface(gdk_pointer)
        if not native:
            return
        record = self.surfaces.get(widget)
        if record and record[0] != native:
            self.detach(widget)
            record = None
        if not record:
            if any(r[0] == native for r in self.surfaces.values()):
                return  # Some GTK child widgets share their parent's surface.
            effect = self.lib.cf_attach(self.ctx,gdk_pointer,pointer(widget))
            if not effect:
                return
            record = (native,effect,None)
        shape = (window.get_width(),window.get_height(),CORNER_RADIUS,bool(getattr(widget,"okayu_blur",self.frosted)) and self.supported)
        if force or record[2] != shape:
            self.lib.cf_update(self.ctx,record[1],*shape)
            self.surfaces[widget] = (native,record[1],shape)
            widget.queue_draw()

    def detach(self,widget,*_):
        record = self.surfaces.pop(widget,None)
        if record and self.lib:
            self.lib.cf_detach(record[1])

    def forget(self,widget,*_):
        self.detach(widget)
        self.widgets.discard(widget)

    def close(self):
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = 0
        for monitor in self.monitors:
            monitor.cancel()
        self.monitors.clear()
        for widget in list(self.widgets):
            self.detach(widget)
        self.widgets.clear()
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),self.css)
        if self.lib and self.ctx:
            self.lib.cf_free(self.ctx)
            self.ctx = None
