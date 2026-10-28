"""Color representations, validated preferences and native gettext localization."""
import colorsys
import gettext
import json
import os
from pathlib import Path

FORMATS = ('HEX', 'RGB', 'HSL', 'CMYK')
ZOOMS = (1, 2, 4, 8, 16)
DEFAULTS = {'language': 'auto', 'format': 'HEX', 'glass': 'auto'}


def number(value):
    return f'{value:.1f}'.rstrip('0').rstrip('.')


def format_color(value, kind='HEX'):
    r, g, b = (value >> 16 & 255, value >> 8 & 255, value & 255)
    if kind == 'RGB':
        return f'rgb({r}, {g}, {b})'
    if kind == 'HSL':
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return f'hsl({number((h * 360) % 360)}, {number(s * 100)}%, {number(l * 100)}%)'
    if kind == 'CMYK':
        maximum = max(r, g, b) / 255
        channels = [0, 0, 0] if maximum == 0 else [(1 - v / 255 / maximum) * 100 for v in (r, g, b)]
        return 'cmyk(' + ', '.join(number(v) + '%' for v in channels + [(1 - maximum) * 100]) + ')'
    return f'#{value:06X}'


def cycle_format(kind, direction):
    return FORMATS[(FORMATS.index(kind) + direction) % len(FORMATS)]


class Zoom:
    def __init__(self):
        self.reset()

    def reset(self):
        self.value, self.remainder = 4, 0.0

    def step(self, amount):
        self.remainder += amount
        steps = int(self.remainder)
        self.remainder -= steps
        index = max(0, min(len(ZOOMS) - 1, ZOOMS.index(self.value) + steps))
        self.value = ZOOMS[index]
        return self.value


class Preferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'okayu-color-picker/settings.json'
        self.values = dict(DEFAULTS)
        try:
            values = json.loads(self.path.read_text())
            if isinstance(values, dict):
                for key, choices in self.choices().items():
                    if values.get(key) in choices:
                        self.values[key] = values[key]
        except (OSError, ValueError):
            pass

    @staticmethod
    def choices():
        return {'language': ('auto', 'en', 'es', 'pt_BR'), 'format': FORMATS, 'glass': ('auto', 'on', 'off')}

    def set(self, key, value):
        if value not in self.choices()[key]:
            raise ValueError('Invalid preference')
        candidate = dict(self.values, **{key: value})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(candidate) + '\n')
        temporary.replace(self.path)
        self.values = candidate


def detect_language(environment=None):
    env = os.environ if environment is None else environment
    # An explicitly C/POSIX messages locale has English semantics.
    base = env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG', 'en')
    if base.upper() in ('C', 'POSIX', 'C.UTF-8', 'C.UTF8'):
        return 'en'
    for item in (env.get('LANGUAGE', '') + ':' + base).split(':'):
        code = item.replace('-', '_').split('.')[0].split('@')[0].lower()
        if code.startswith('es'):
            return 'es'
        if code.startswith('pt'):
            return 'pt_BR'
        if code.startswith('en'):
            return 'en'
    return 'en'


class Translator:
    def __init__(self, language='auto', directory=None):
        self.directory = directory or Path(__file__).parent / 'locale'
        self.set_language(language)

    def set_language(self, language):
        self.language = detect_language() if language == 'auto' else language
        self.catalog = gettext.translation('okayu-picker', localedir=self.directory,
                                           languages=[self.language], fallback=True)

    def __call__(self, message):
        return self.catalog.gettext(message)
