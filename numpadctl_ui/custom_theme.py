"""Your own Material You colours: from any colour, a picture (your wallpaper), pywal, or a theme file.

Every source ends as the same thing the built-in accents give (tokens.colors): {role: "#rrggbb"} with all of
Material 3's colour roles plus the custom "ok" / "warn" ones. Where to take the colours from is the "look"
settings (config.look_settings), "source":

  "accent"   the built-in accents (m3_palettes.json, made ahead of time: no maths at runtime)
  "color"    a seed colour you pick; the scheme is computed with Google's colour maths (materialyoucolor)
  "image"    the most fitting seed colour of a picture, picked the way Android picks it from a wallpaper
  "pywal"    pywal's last wallpaper (~/.cache/wal/colors.json), or its colour 1 if there is no picture
  "file"     a theme file: a Material Theme Builder export ("schemes": {"light": ..., "dark-high-contrast": ...}),
             matugen's JSON (snake_case roles, light/dark per role or per scheme), or a flat {"primary": ...};
             roles the file leaves out are filled in from its primary colour

"file", "image" and "pywal" are files: theme.watch_look() applies them again when they change, so a wallpaper
script (matugen, pywal, wallust...) re-colours the window by itself.

Anything that goes wrong (a missing file, a broken JSON, no materialyoucolor) raises ThemeError with a sentence
for the Settings window; the caller falls back to the built-in accent, so a bad theme never leaves you without
a usable window.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from . import tokens

VARIANTS = {   # scheme styles: Material's own names (what Theme Builder and Android call them)
    "tonal_spot": "Tonal spot (Android's default)", "vibrant": "Vibrant", "expressive": "Expressive",
    "fidelity": "Fidelity (closest to the colour)", "content": "Content", "neutral": "Neutral",
    "monochrome": "Monochrome", "rainbow": "Rainbow", "fruit_salad": "Fruit salad",
}
CONTRAST_LEVELS = {"standard": 0.0, "medium": 0.5, "high": 1.0}
CUSTOM = {"ok": 0xFF2E9E4F, "warn": 0xFFE0A800}   # as in tools/generate_m3_palettes.py
PYWAL = Path.home() / ".cache" / "wal" / "colors.json"
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")


class ThemeError(Exception):
    """The colours couldn't be made; the message is shown in Settings as it is."""


def available():
    """True when Google's colour maths (materialyoucolor) is installed: needed for "color", "image", "pywal"."""
    try:
        import materialyoucolor  # noqa: F401
        return True
    except ImportError:
        return False


def _argb(color):
    match = _HEX.match(str(color).strip())
    if not match:
        raise ThemeError(f"“{color}” isn't a colour (use #rrggbb)")
    return int("ff" + match.group(1), 16)


def _hexed(argb):
    return "#%06x" % (argb & 0xFFFFFF)


def _snake_to_camel(name):
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


# ---------------------------------------------------------------- from a seed colour
@lru_cache(maxsize=32)
def generate(seed, dark, contrast="standard", variant="tonal_spot"):
    """Every role for a seed colour ("#rrggbb"), as Theme Builder / Android would make it."""
    try:
        from materialyoucolor.blend import Blend
        from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
        from materialyoucolor.hct import Hct
        from materialyoucolor.palettes.tonal_palette import TonalPalette
    except ImportError:
        raise ThemeError("Making colours from your own colour needs the materialyoucolor package "
                         "(run the installer again, or: pip install materialyoucolor)") from None
    import importlib
    if variant not in VARIANTS:
        variant = "tonal_spot"
    module = importlib.import_module(f"materialyoucolor.scheme.scheme_{variant}")
    scheme_class = getattr(module, "Scheme" + "".join(part.capitalize() for part in variant.split("_")))
    seed_argb = _argb(seed)
    scheme = scheme_class(Hct.from_int(seed_argb), bool(dark), CONTRAST_LEVELS.get(contrast, 0.0), spec_version="2021")
    roles = {}
    for role in tokens.colors(dark=dark):   # exactly the roles the built-in accents have
        rule = getattr(MaterialDynamicColors, role, None)
        if rule is not None:
            roles[role] = _hexed(rule.get_argb(scheme))
    for name, color in CUSTOM.items():   # "ok" / "warn", harmonized with the seed like Theme Builder's custom colours
        tones = TonalPalette.from_int(Blend.harmonize(color, seed_argb))
        pick = (80, 20, 30, 90) if dark else (40, 100, 90, 10)
        cap = name.capitalize()
        roles[name], roles[f"on{cap}"], roles[f"{name}Container"], roles[f"on{cap}Container"] = \
            (_hexed(tones.tone(t)) for t in pick)
    return roles


# ---------------------------------------------------------------- from a picture
@lru_cache(maxsize=8)
def _seed_of_image(path, mtime):   # mtime is in the key: a new picture at the same path is read again
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    image = QImage(path)
    if image.isNull():
        raise ThemeError(f"{Path(path).name} isn't a picture this can read")
    small = image.scaled(112, 112, Qt.KeepAspectRatio, Qt.FastTransformation).convertToFormat(QImage.Format_ARGB32)
    pixels = []
    for y in range(small.height()):
        for x in range(small.width()):
            argb = small.pixel(x, y)
            pixels.append(((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, 255))
    try:
        from materialyoucolor.quantize import QuantizeCelebi
        from materialyoucolor.score.score import Score
    except ImportError:
        raise ThemeError("Colours from a picture need the materialyoucolor package") from None
    best = Score.score(QuantizeCelebi(pixels, 128))   # Android's own pick of the wallpaper's colour
    return _hexed(best[0])


def seed_of_image(path):
    """The seed colour Android would take from this picture ("#rrggbb")."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise ThemeError(f"Picture not found: {file}")
    return _seed_of_image(str(file), file.stat().st_mtime)


def pywal_seed(colors_file=PYWAL):
    """pywal's wallpaper's colour, or its colour 1 when the wallpaper is gone; and what it came from."""
    file = Path(colors_file)
    try:
        data = json.loads(file.read_text())
    except OSError:
        raise ThemeError("No pywal colours yet (run wal -i <picture> first)") from None
    except ValueError:
        raise ThemeError(f"{file} isn't valid JSON") from None
    wallpaper = data.get("wallpaper") if isinstance(data, dict) else None
    if wallpaper and Path(wallpaper).expanduser().is_file():
        return seed_of_image(wallpaper), Path(wallpaper).name
    color = (data.get("colors") or {}).get("color1") if isinstance(data, dict) else None
    if not color:
        raise ThemeError(f"{file} has neither a wallpaper nor colours")
    return color, "pywal colour 1"


# ---------------------------------------------------------------- from a theme file
def _flat_roles(mapping):
    """{role: colour} from one scheme's mapping, roles in camelCase whatever the file used."""
    roles = {}
    for name, value in mapping.items():
        if isinstance(value, dict):   # matugen: {"color": "#..."} or {"hex": "#..."}
            value = value.get("color") or value.get("hex") or value.get("default")
        if isinstance(value, str) and _HEX.match(value.strip()):
            roles[_snake_to_camel(name)] = "#" + _HEX.match(value.strip()).group(1).lower()
    return roles


def _schemes_in(data):
    """{"light"|"dark"|"light-medium-contrast"|...: {role: colour}} from any of the supported layouts."""
    if not isinstance(data, dict):
        raise ThemeError("The theme file must be a JSON object")
    if isinstance(data.get("schemes"), dict):   # Material Theme Builder export
        return {name: _flat_roles(roles) for name, roles in data["schemes"].items() if isinstance(roles, dict)}
    colors = data.get("colors")
    if isinstance(colors, dict):   # matugen
        if isinstance(colors.get("dark"), dict) or isinstance(colors.get("light"), dict):
            return {name: _flat_roles(colors[name]) for name in ("light", "dark") if isinstance(colors.get(name), dict)}
        schemes = {"light": {}, "dark": {}}   # newer matugen: per role {"light": ..., "dark": ..., "default": ...}
        for role, value in colors.items():
            if isinstance(value, dict):
                for mode in ("light", "dark"):
                    if mode in value:
                        schemes[mode][role] = value[mode]
        return {mode: _flat_roles(roles) for mode, roles in schemes.items() if roles}
    flat = _flat_roles(data)   # a plain {"primary": "#...", ...}: the same colours light and dark
    return {"light": flat, "dark": flat} if flat else {}


def from_file(path, dark, contrast="standard", variant="tonal_spot"):
    file = Path(path).expanduser()
    try:
        data = json.loads(file.read_text())
    except OSError:
        raise ThemeError(f"Theme file not found: {file}") from None
    except ValueError as e:
        raise ThemeError(f"{file.name} isn't valid JSON ({e})") from None
    schemes = _schemes_in(data)
    mode = "dark" if dark else "light"
    wanted = mode if contrast == "standard" else f"{mode}-{contrast}-contrast"
    roles = schemes.get(wanted) or schemes.get(mode) or next(iter(schemes.values()), {})
    if "primary" not in roles:
        seed = data.get("seed") or data.get("source") or (data.get("coreColors") or {}).get("primary")
        if not seed:
            raise ThemeError(f"{file.name} has no Material colours in it (no “primary”)")
        return generate(str(seed), dark, contrast, variant)
    missing = set(tokens.colors(dark=dark)) - set(roles)
    if missing:   # an older export or a short file: the rest comes from its primary colour
        try:
            base = generate(roles["primary"], dark, contrast, variant)
        except ThemeError:
            base = tokens.colors(dark=dark, contrast=contrast)
        roles = {**base, **roles}
    return roles


# ---------------------------------------------------------------- the one entry point
def colors(look, dark, contrast="standard", accent=tokens.DEFAULT_ACCENT):
    """{role: colour} for the look settings, plus a note on where they came from (for Settings)."""
    source, variant = look.get("source", "accent"), look.get("variant", "tonal_spot")
    if source == "color":
        return generate(look.get("seed") or "#6750a4", dark, contrast, variant), "your colour"
    if source == "image":
        if not look.get("image"):
            raise ThemeError("Choose a picture first")
        seed = seed_of_image(look["image"])
        return generate(seed, dark, contrast, variant), f"{Path(look['image']).name} ({seed})"
    if source == "pywal":
        seed, origin = pywal_seed()
        return generate(seed, dark, contrast, variant), f"pywal: {origin} ({seed})"
    if source == "file":
        if not look.get("file"):
            raise ThemeError("Choose a theme file first")
        return from_file(look["file"], dark, contrast, variant), Path(look["file"]).name
    return tokens.colors(accent, dark, contrast), f"{accent} accent"


def watched_files(look):
    """The files whose change should re-colour the window (theme.watch_look)."""
    source = look.get("source")
    if source == "file" and look.get("file"):
        return [str(Path(look["file"]).expanduser())]
    if source == "image" and look.get("image"):
        return [str(Path(look["image"]).expanduser())]
    if source == "pywal":
        return [str(PYWAL)]
    return []


def export(look, contrast="standard", accent=tokens.DEFAULT_ACCENT):
    """The current colours as a Material Theme Builder-style JSON object (light and dark), to share or edit."""
    schemes = {}
    for dark in (False, True):
        roles, origin = colors(look, dark, contrast, accent)
        schemes["dark" if dark else "light"] = {k: v.upper() for k, v in sorted(roles.items())}
    return {"description": f"NumpadControl theme ({origin})", "seed": schemes["light"].get("primary", ""),
            "schemes": schemes}
