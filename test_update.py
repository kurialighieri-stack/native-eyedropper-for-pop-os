import array
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, PropertyMock

import picker
from picker_model import Preferences, Translator, Zoom, format_color, cycle_format, detect_language
from magnifier import PATCH_SIDE, render_cursor
from cosmic_style import CosmicStyle, optional_color
from gi.repository import Gdk, Gtk, GLib


class ModelTests(unittest.TestCase):
    def test_formats_and_edges(self):
        for value, rgb, hsl, cmyk in [
            (0, 'rgb(0, 0, 0)', 'hsl(0, 0%, 0%)', 'cmyk(0%, 0%, 0%, 100%)'),
            (0xFFFFFF, 'rgb(255, 255, 255)', 'hsl(0, 0%, 100%)', 'cmyk(0%, 0%, 0%, 0%)'),
            (0xFF0000, 'rgb(255, 0, 0)', 'hsl(0, 100%, 50%)', 'cmyk(0%, 100%, 100%, 0%)')]:
            self.assertEqual(format_color(value,'RGB'),rgb)
            self.assertEqual(format_color(value,'HSL'),hsl)
            self.assertEqual(format_color(value,'CMYK'),cmyk)
        self.assertEqual(format_color(0x12ABCD), '#12ABCD')
        self.assertEqual(format_color(0x12ABCD,'HSL'), 'hsl(190.9, 83.9%, 43.7%)')
        self.assertEqual(cycle_format('HEX',-1),'CMYK')
        self.assertEqual(cycle_format('CMYK',1),'HEX')

    def test_zoom_clamping_accumulation_and_reset(self):
        zoom=Zoom();self.assertEqual(zoom.value,4)
        self.assertEqual(zoom.step(.4),4);self.assertEqual(zoom.step(.7),8)
        self.assertEqual(zoom.step(10),16);self.assertEqual(zoom.step(-20),1)
        zoom.reset();self.assertEqual((zoom.value,zoom.remainder),(4,0))

    def test_preferences_validate_and_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            prefs=Preferences(path);self.assertEqual(prefs.values,{'language':'auto','format':'HEX','glass':'auto'})
            prefs.set('format','HSL');prefs.set('language','pt_BR');prefs.set('glass','off')
            self.assertEqual(Preferences(path).values,prefs.values)
            with self.assertRaises(ValueError):prefs.set('format','bad')
            path.write_text('{"language":"bad", "format":"RGB", "glass":1}')
            self.assertEqual(Preferences(path).values,{'language':'auto','format':'RGB','glass':'auto'})

    def test_locales_and_catalog_fallback(self):
        for locale,expected in [('es_MX.UTF-8','es'),('pt-PT.UTF-8','pt_BR'),('pt_BR','pt_BR'),('fr_FR','en'),('C.UTF-8','en')]:
            self.assertEqual(detect_language({'LANG':locale}),expected)
        self.assertEqual(detect_language({'LANG':'es_MX','LC_ALL':'C.UTF-8'}),'en')
        self.assertEqual(detect_language({'LANG':'en_US','LANGUAGE':'pt_PT:es'}),'pt_BR')
        self.assertEqual(Translator('es')('Save palette'),'Guardar paleta')
        self.assertEqual(Translator('pt_BR')('Save palette'),'Salvar paleta')
        self.assertEqual(Translator('es')('Unknown fallback string'),'Unknown fallback string')
        for language in ('es','pt_BR'):
            import ast
            tree=ast.parse(Path(picker.__file__).read_text())
            messages={n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_' and n.args and isinstance(n.args[0],ast.Constant)}
            catalog=Translator(language).catalog._catalog
            self.assertFalse(messages-set(catalog))

    def test_magnifier_center_is_exact_at_every_zoom_and_corner(self):
        data=[0xABCDEF]*(PATCH_SIDE*PATCH_SIDE);data[len(data)//2]=0x12ABCD
        ring=picker.cursor_surface(0x12ABCD)
        for zoom in (1,2,4,8,16):
            for position in ((.1,.1),(.9,.1),(.1,.9),(.9,.9)):
                surface,hotspot=render_cursor(ring,data,zoom,position)
                self.assertLessEqual(surface.get_width(),256);self.assertLessEqual(surface.get_height(),256)
                mx=0 if position[0]>.65 else 80
                x=mx+144//2-zoom//2+zoom//2;y=144//2
                i=y*surface.get_stride()+x*4
                pixel=int.from_bytes(surface.get_data()[i:i+4],sys.byteorder)
                self.assertEqual(pixel,0xFF12ABCD)
                self.assertTrue(0<=hotspot[0]<surface.get_width())
                self.assertTrue(0<=hotspot[1]<surface.get_height())

    def test_cosmic_optional_accent_text_color(self):
        fallback = '#123456FF'
        self.assertEqual(optional_color('Some((red: 1.0, green: 0.5, blue: 0.0, alpha: 1.0))', fallback), '#FF8000FF')
        for value in ('None', 'Some((red: 2, green: 0, blue: 0, alpha: 1))', 'Some((red: nan))', 'invalid'):
            self.assertEqual(optional_color(value, fallback), fallback)

    def test_native_pixel_region_all_transformations(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'region-test'
            flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
            subprocess.run(['gcc','-O2',str(root/'test_pixel_region.c'),str(root/'capture.c'),str(root/'source.c'),str(root/'foreign.c'),str(root/'workspace.c'),str(root/'cosmic-source.c'),'-o',str(binary),*flags,'-lm'],check=True)
            subprocess.run([str(binary)],check=True)


@unittest.skipUnless(os.environ.get('EYEDROPPER_WAYLAND_TEST')=='1','requires Wayland')
class ThemeTests(unittest.TestCase):
    def test_live_theme_and_opaque_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);mode=root/'com.system76.CosmicTheme.Mode/v1';mode.mkdir(parents=True)
            (mode/'is_dark').write_text('true')
            for name in ('Dark','Light'):
                folder=root/f'com.system76.CosmicTheme.{name}/v2';folder.mkdir(parents=True)
                (folder/'background').write_text('(\n    base: "#112233FF",\n    on: "#EEEEEEFF",\n)')
                (folder/'transparent_background').write_text('(\n    base: "#11223380",\n    on: "#EEEEEEFF",\n)')
                (folder/'accent').write_text('(\n    base: "#123456FF",\n)')
                (folder/'frosted_windows').write_text('true')
            with patch.object(CosmicStyle,'supported',new_callable=PropertyMock,return_value=True):
                style=CosmicStyle(root)
                self.assertTrue(style.frosted);self.assertIn('0.50196',style.state[0]);before=style.state
                (root/'com.system76.CosmicTheme.Dark/v2/accent').write_text('(\n    base: "#FF0000FF",\n)')
                loop=GLib.MainLoop()
                changed=[]
                def check():
                    if style.state!=before:
                        changed.append(True);loop.quit();return False
                    return True
                poll=GLib.timeout_add(30,check)
                timeout=GLib.timeout_add(1500,lambda:loop.quit() or False)
                loop.run()
                self.assertTrue(changed,'Gio theme watcher did not update the stylesheet')
                GLib.source_remove(timeout)
                (mode/'is_dark').write_text('false');style.refresh();self.assertTrue(style.frosted)
                style.glass='off';style.refresh();self.assertFalse(style.frosted);self.assertIn('1.00000',style.state[0])
                style.close()
            with patch.object(CosmicStyle,'supported',new_callable=PropertyMock,return_value=False):
                style=CosmicStyle(root,glass='on');self.assertFalse(style.frosted);self.assertIn('1.00000',style.state[0]);style.close()
