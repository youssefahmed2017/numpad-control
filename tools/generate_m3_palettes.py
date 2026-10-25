"""Writes numpadctl/qt/m3_palettes.json: Material 3 colour roles for each accent seed.

Same output as Google's Material Theme Builder (spec version 2021, tonal spot): the test
tests/test_tokens.py compares it with a real Theme Builder export. For each accent there is
light and dark, each in standard, medium and high contrast, plus "ok" and "warn" status colours
(custom colours, harmonized with the seed the way Theme Builder does it).

Needs `pip install materialyoucolor` (a development tool only: the app reads the JSON).
    .venv/bin/python tools/generate_m3_palettes.py
"""

import json
from pathlib import Path

from materialyoucolor.blend import Blend
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.palettes.tonal_palette import TonalPalette
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

SEEDS = {"Orchid": "#c82ce0", "Blue": "#3584e4", "Purple": "#6750a4", "Green": "#2e8b57",
         "Orange": "#e8710a", "Pink": "#c2185b", "Teal": "#00897b"}
CONTRASTS = {"standard": 0.0, "medium": 0.5, "high": 1.0}
CUSTOM = {"ok": 0xFF2E9E4F, "warn": 0xFFE0A800}  # the colours before they are harmonized with the seed
ROLES = ["primary", "surfaceTint", "onPrimary", "primaryContainer", "onPrimaryContainer",
         "secondary", "onSecondary", "secondaryContainer", "onSecondaryContainer",
         "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer",
         "error", "onError", "errorContainer", "onErrorContainer",
         "background", "onBackground", "surface", "onSurface", "surfaceVariant", "onSurfaceVariant",
         "outline", "outlineVariant", "shadow", "scrim", "inverseSurface", "inverseOnSurface", "inversePrimary",
         "primaryFixed", "onPrimaryFixed", "primaryFixedDim", "onPrimaryFixedVariant",
         "secondaryFixed", "onSecondaryFixed", "secondaryFixedDim", "onSecondaryFixedVariant",
         "tertiaryFixed", "onTertiaryFixed", "tertiaryFixedDim", "onTertiaryFixedVariant",
         "surfaceDim", "surfaceBright", "surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer",
         "surfaceContainerHigh", "surfaceContainerHighest"]


def hexed(argb):
    return "#%06x" % (argb & 0xFFFFFF)


def palette(seed_argb, dark, contrast):
    scheme = SchemeTonalSpot(Hct.from_int(seed_argb), dark, contrast, spec_version="2021")
    roles = {role: hexed(getattr(MaterialDynamicColors, role).get_argb(scheme)) for role in ROLES}
    for name, color in CUSTOM.items():  # Theme Builder's "custom colour" roles: tones 40/100/90/10 (light), 80/20/30/90 (dark)
        tones = TonalPalette.from_int(Blend.harmonize(color, seed_argb))
        pick = (80, 20, 30, 90) if dark else (40, 100, 90, 10)
        roles[name], roles["on" + name.capitalize()], roles[name + "Container"], roles["on" + name.capitalize() + "Container"] = \
            (hexed(tones.tone(t)) for t in pick)
    return roles


out = {"seeds": SEEDS, "palettes": {}}
for name, seed in SEEDS.items():
    argb = int("ff" + seed.lstrip("#"), 16)
    out["palettes"][name] = {mode: {level: palette(argb, mode == "dark", value) for level, value in CONTRASTS.items()}
                             for mode in ("light", "dark")}
path = Path(__file__).resolve().parent.parent / "numpadctl" / "qt" / "m3_palettes.json"
path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
print("wrote", path, f"({path.stat().st_size // 1024} KB)")
