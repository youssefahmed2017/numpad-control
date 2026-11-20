"""The sizes the app takes from BeerCSS (tokens.py), and that the stylesheet and the dialogs really use them."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox  # noqa: E402

from numpadctl_ui import buttons, dialogs, theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")


class TokensTest(unittest.TestCase):
    def test_the_calc_values_are_worked_out(self):
        self.assertEqual(tokens.beer_button_radius("medium"), 20)     # calc(var(--_size) / 2)
        self.assertEqual(tokens.beer_button_radius("small"), 16)
        v = tokens.beer_vars(1.0)
        self.assertEqual((v["beer_button_height"], v["beer_button_pad"]), ("40px", "16px"))
        self.assertEqual((v["beer_small_height"], v["beer_small_pad"]), ("32px", "12px"))
        self.assertEqual(v["beer_field_min"], "30px", "48 px field minus 2 x 8 px padding and 2 x 1 px border")
        self.assertEqual(v["beer_item_min"], "28px", "a 44 px menu row minus its 2 x 8 px padding")
        self.assertEqual(v["beer_tab_min"], "30px", "a 48 px tab minus padding and the 2 px indicator")

    def test_only_the_corners_follow_the_shape_setting(self):
        round_, square = tokens.beer_vars(1.0), tokens.beer_vars(0.25)
        self.assertEqual((round_["beer_menu_radius"], square["beer_menu_radius"]), ("16px", "4px"))
        self.assertEqual(round_["beer_button_height"], square["beer_button_height"])
        self.assertEqual(round_["beer_field_min"], square["beer_field_min"])

    def test_the_timing_and_shadow_levels_are_beercss_s(self):
        self.assertEqual(tokens.SPEED, {"speed1": 100, "speed2": 200, "speed3": 300, "speed4": 400})
        self.assertEqual([tokens.ELEVATE[i][0] for i in (1, 2, 3)], [2, 4, 6])
        self.assertEqual([tokens.ELEVATE[i][1] for i in (1, 2, 3)], [0.32, 0.40, 0.48])


class WidgetsTest(unittest.TestCase):
    def test_fields_are_48_px_tall(self):
        for widget in (QLineEdit(), QSpinBox(), buttons.ComboBox()):
            widget.ensurePolished()
            self.assertEqual(widget.sizeHint().height(), tokens.BEER_FIELD["height"], type(widget).__name__)

    def test_buttons_use_beercss_s_height_and_padding(self):
        plain, flat = buttons.PushButton("Cancel"), buttons.PushButton("Cancel")
        flat.setObjectName("flat")
        for b in (plain, flat):
            b.ensurePolished()
        self.assertEqual(plain.sizeHint().height(), tokens.BEER_BUTTON["medium"][0])
        self.assertEqual(flat.sizeHint().height(), tokens.BEER_BUTTON["small"][0])

    def test_the_apps_dialogs_get_24_px_of_padding_and_320_px_of_width(self):
        d = dialogs.PresetDialog(None, "Default")
        d.show()
        APP.processEvents()
        pad = tokens.BEER_DIALOG["padding"]
        self.assertEqual(d.layout().contentsMargins().left(), pad)
        self.assertEqual(d.layout().contentsMargins().bottom(), pad)
        self.assertGreaterEqual(d.minimumWidth(), tokens.BEER_DIALOG["min_width"])
        d.close()


if __name__ == "__main__":
    unittest.main()
