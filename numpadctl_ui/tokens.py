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

# ---------------------------------------------------------------- BeerCSS metrics
# The numbers below are BeerCSS 5.0.3's (https://www.beercss.com, MIT license, the library the website uses), so the app
# and the site are the same size. 1rem = 16 px. Qt style sheets have no calc(), var() or transitions, so what BeerCSS
# computes with calc() is worked out here once (BeerCSS: "--_round: calc(var(--_size) / 2)"), and the stylesheet
# in theme.py gets the finished px values. Animations stay with motion.py (springs); BeerCSS's plain CSS transitions
# are only the named durations in SPEED.
REM = 16
BEER_BUTTON = {"small": (32, 12), "medium": (40, 16), "large": (48, 20), "extra": (56, 24)}   # (height, side padding)
BEER_CHIP = {"height": 32, "padding": 12, "radius": 8, "gap": 8}
BEER_CARD = {"radius": 12, "padding": 16}
BEER_DIALOG = {"radius": 28, "padding": 24, "min_width": 320}
BEER_MENU = {"radius": 16, "padding": 4, "gap": 2, "item_padding": (8, 16), "item_height": 44, "item_radius": 4}
BEER_LIST_ITEM = {"padding": (8, 16), "height": 56}
BEER_TAB = {"padding": (8, 16), "height": 48, "indicator": 2}
BEER_FIELD = {"padding": 15, "focus_padding": 14, "font": 16, "radius": 4, "height": 48, "small_height": 40, "pad_y": 8, "border": 1}   # height: BeerCSS --_input 3rem
BEER_LETTER_SPACING = 0.5      # body: letter-spacing 0.0313rem
SPEED = {"speed1": 100, "speed2": 200, "speed3": 300, "speed4": 400}   # ms: BeerCSS --speed1..4
ELEVATE = {1: (2, 0.32), 2: (4, 0.40), 3: (6, 0.48)}   # BeerCSS --elevate1..3: y offset px, shadow alpha


def beer_button_radius(size):
    """calc(var(--_size) / 2): a BeerCSS button is a full pill."""
    return BEER_BUTTON[size][0] / 2


def beer_vars(factor=1.0):
    """The values the stylesheet template (theme.STYLE) takes, as "Npx" strings. `factor` scales the corner radii
    with the shape setting (1.0 round, 0.6 rounded, 0.25 square); paddings and heights do not change."""
    def px(value):
        return f"{round(value)}px"

    def radius(value):
        return px(value * factor)

    small_h, small_pad = BEER_BUTTON["small"]
    medium_h, medium_pad = BEER_BUTTON["medium"]
    item_y, item_x = BEER_MENU["item_padding"]
    list_y, list_x = BEER_LIST_ITEM["padding"]
    tab_y, tab_x = BEER_TAB["padding"]
    return {
        "beer_button_height": px(medium_h), "beer_button_pad": px(medium_pad),
        "beer_small_height": px(small_h), "beer_small_pad": px(small_pad),
        "beer_chip_radius": radius(BEER_CHIP["radius"]),
        "beer_menu_radius": radius(BEER_MENU["radius"]), "beer_menu_pad": px(BEER_MENU["padding"]),
        "beer_item_pad_y": px(item_y), "beer_item_pad_x": px(item_x),
        "beer_item_min": px(BEER_MENU["item_height"] - 2 * item_y), "beer_item_radius": radius(BEER_MENU["item_radius"]),
        "beer_list_pad_y": px(list_y), "beer_list_pad_x": px(list_x), "beer_list_min": px(BEER_LIST_ITEM["height"] - 2 * list_y),
        "beer_tab_pad_y": px(tab_y), "beer_tab_pad_x": px(tab_x), "beer_tab_indicator": px(BEER_TAB["indicator"]),
        "beer_tab_min": px(BEER_TAB["height"] - 2 * tab_y - BEER_TAB["indicator"]),
        "beer_field_pad": px(BEER_FIELD["padding"]), "beer_field_pad_focus": px(BEER_FIELD["focus_padding"]),
        "beer_field_pad_y": px(BEER_FIELD["pad_y"]), "beer_field_pad_y_focus": px(BEER_FIELD["pad_y"] - 1),
        "beer_field_min": px(BEER_FIELD["height"] - 2 * BEER_FIELD["pad_y"] - 2 * BEER_FIELD["border"]),   # the content box
        "beer_spin_min": px(BEER_FIELD["height"] - 2 * BEER_FIELD["pad_y"] - 2 * BEER_FIELD["border"] - 3),   # QSpinBox adds 3 px of its own
    }


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
