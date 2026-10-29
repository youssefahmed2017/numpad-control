"""Material 3 ("Material You") design tokens: colour roles, shapes, type and state layers.

The colour roles come from m3_palettes.json, generated from a seed colour with
tools/generate_m3_palettes.py (so the app needs no extra library). They match Google's
Material Theme Builder exactly (tests/test_tokens.py). The theme turns these tokens into
Qt's palette and stylesheet.
"""

import json
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name("m3_palettes.json").read_text())
ACCENTS = list(_DATA["palettes"])
SEEDS = _DATA["seeds"]          # {"Blue": "#3584e4", ...}: the accent choices
DEFAULT_ACCENT = "Orchid"

# Shape: corner radii in px (M3: extra small .. extra large; "full" is half the control's height).
SHAPE = {"xs": 4, "s": 8, "m": 12, "l": 20, "xl": 28, "full": 20}

# State layers: the share of the content colour mixed over a control when it is hovered / pressed / focused.
STATE = {"hover": 0.08, "focus": 0.10, "pressed": 0.10}

# Type scale (px, weight): M3's roles at the sizes a desktop settings window needs.
TYPE = {"titleLarge": (22, 500), "titleMedium": (16, 500), "titleSmall": (14, 500),
        "bodyLarge": (16, 400), "bodyMedium": (14, 400), "bodySmall": (12, 400),
        "labelLarge": (14, 500), "labelMedium": (12, 500)}

CONTRASTS = ("standard", "medium", "high")


def colors(accent=DEFAULT_ACCENT, dark=True, contrast="standard"):
    """{role: "#rrggbb"}: every Material 3 role for an accent name from SEEDS, plus the custom ok / warn colours."""
    palettes = _DATA["palettes"].get(accent) or _DATA["palettes"][DEFAULT_ACCENT]
    return dict(palettes["dark" if dark else "light"].get(contrast) or palettes["dark" if dark else "light"]["standard"])


def _rgb(color):
    color = color.lstrip("#")
    return [int(color[i:i + 2], 16) for i in (0, 2, 4)]


def blend(base, over, alpha):
    """base with `over` mixed in by alpha (a state layer over a solid colour), as "#rrggbb"."""
    mixed = [round(b * (1 - alpha) + o * alpha) for b, o in zip(_rgb(base), _rgb(over))]
    return "#%02x%02x%02x" % tuple(mixed)


def rgba(color, alpha):
    """A translucent version of a colour, for state layers over transparent backgrounds."""
    r, g, b = _rgb(color)
    return f"rgba({r},{g},{b},{alpha})"
