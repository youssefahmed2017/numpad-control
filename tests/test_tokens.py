"""The Material 3 palettes match Google's Material Theme Builder, and the theme builds from them."""

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl_ui import theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
EXPORT = json.loads((Path(__file__).parent / "fixtures" / "material-theme-orchid.json").read_text())
SCHEMES = {"light": (False, "standard"), "light-medium-contrast": (False, "medium"),
           "light-high-contrast": (False, "high"), "dark": (True, "standard"),
           "dark-medium-contrast": (True, "medium"), "dark-high-contrast": (True, "high")}


class TokensTest(unittest.TestCase):
    def test_orchid_matches_a_real_theme_builder_export(self):
        """tests/fixtures/material-theme-orchid.json was exported from material-foundation.github.io for seed #C82CE0."""
        self.assertEqual(tokens.SEEDS["Orchid"].upper(), EXPORT["seed"].upper())
        for name, (dark, contrast) in SCHEMES.items():
            mine = tokens.colors("Orchid", dark, contrast)
            for role, expected in EXPORT["schemes"][name].items():
                with self.subTest(f"{name} {role}"):
                    self.assertEqual(mine[role].upper(), expected.upper())

    def test_every_accent_has_every_scheme_and_status_colours(self):
        for accent in tokens.SEEDS:
            for dark in (False, True):
                for contrast in tokens.CONTRASTS:
                    roles = tokens.colors(accent, dark, contrast)
                    for needed in ("primary", "onPrimary", "surfaceContainerHigh", "okContainer", "onOkContainer",
                                   "warnContainer", "onWarnContainer"):
                        self.assertRegex(roles[needed], r"^#[0-9a-f]{6}$", f"{accent} {dark} {contrast} {needed}")

    def test_unknown_accent_or_contrast_falls_back(self):
        self.assertEqual(tokens.colors("Nope", True, "extreme"), tokens.colors(tokens.DEFAULT_ACCENT, True))

    def test_state_layers_blend_toward_the_content_colour(self):
        self.assertEqual(tokens.blend("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(tokens.rgba("#ff8000", 0.08), "rgba(255,128,0,0.08)")

    def test_theme_applies_for_every_accent_and_contrast(self):
        combos = [(a, "dark", "standard") for a in tokens.SEEDS] + [("Orchid", m, c) for m in ("dark", "light")
                                                                    for c in tokens.CONTRASTS]
        for accent, appearance, contrast in combos:
            c = theme.apply(APP, appearance, accent, contrast)
            self.assertEqual(c["primary"], tokens.colors(accent, appearance == "dark", contrast)["primary"])
        self.assertNotIn("${", APP.styleSheet(), "every token in the stylesheet was filled in")


if __name__ == "__main__":
    unittest.main()
