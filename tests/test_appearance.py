"""Settings → Appearance: your own colours (any colour, a picture, pywal, theme files), Material on/off, shapes,
fonts, motion and transparency (run invisibly, offscreen)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl import config  # noqa: E402
from numpadctl_ui import custom_theme, motion, theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
ROLES = set(tokens.colors(dark=True))


def tmpdir(test):
    folder = tempfile.TemporaryDirectory()
    test.addCleanup(folder.cleanup)
    return Path(folder.name)


class LookSettingsTest(unittest.TestCase):
    def test_defaults_ranges_and_junk(self):
        self.assertEqual(config.look_settings({}), config.LOOK_DEFAULTS)
        look = config.look_settings({"look": {"opacity": 5, "speed": "fast", "shape": "blob", "source": "file",
                                              "material": 0, "font": 3, "font_scale": 500}})
        self.assertEqual((look["opacity"], look["speed"], look["shape"], look["source"], look["material"],
                          look["font"], look["font_scale"]), (60, 1.0, "round", "file", False, "", 130))
        self.assertEqual(config.look_settings({"look": "nope"}), config.LOOK_DEFAULTS)


@unittest.skipUnless(custom_theme.available(), "needs materialyoucolor")
class GenerateTest(unittest.TestCase):
    def test_a_colour_gives_every_role_in_every_style(self):
        for variant in custom_theme.VARIANTS:
            roles = custom_theme.generate("#1e88e5", True, "standard", variant)
            self.assertTrue(ROLES <= set(roles), f"{variant} misses {ROLES - set(roles)}")
        light, dark = custom_theme.generate("#1e88e5", False), custom_theme.generate("#1e88e5", True)
        self.assertLess(QColor(dark["surface"]).lightness(), QColor(light["surface"]).lightness())

    def test_the_builtin_accent_matches_its_own_generation(self):
        """The ahead-of-time accents and the runtime maths are the same thing (no drift between sources)."""
        built_in = tokens.colors("Blue", True, "standard")
        generated = custom_theme.generate(tokens.SEEDS["Blue"], True, "standard", "tonal_spot")
        self.assertEqual(built_in["primary"], generated["primary"])
        self.assertEqual(built_in["surfaceContainer"], generated["surfaceContainer"])

    def test_bad_colours_say_so(self):
        with self.assertRaisesRegex(custom_theme.ThemeError, "isn't a colour"):
            custom_theme.generate("bluish", True)

    def test_a_picture_gives_its_main_colour(self):
        folder = tmpdir(self)
        image = QImage(64, 64, QImage.Format_ARGB32)
        image.fill(QColor("#d81b60"))   # a pink wallpaper
        image.save(str(folder / "wall.png"))
        seed = custom_theme.seed_of_image(folder / "wall.png")
        self.assertGreater(QColor(seed).red(), QColor(seed).blue())
        roles, origin = custom_theme.colors({"source": "image", "image": str(folder / "wall.png")}, True)
        self.assertIn("wall.png", origin)
        self.assertTrue(ROLES <= set(roles))

    def test_pywal_uses_its_wallpaper_or_its_colours(self):
        folder = tmpdir(self)
        (folder / "colors.json").write_text(json.dumps({"wallpaper": "/nowhere.png", "colors": {"color1": "#2e7d32"}}))
        self.assertEqual(custom_theme.pywal_seed(folder / "colors.json"), ("#2e7d32", "pywal colour 1"))
        with self.assertRaisesRegex(custom_theme.ThemeError, "wal -i"):
            custom_theme.pywal_seed(folder / "missing.json")


class ThemeFileTest(unittest.TestCase):
    def write(self, data):
        file = tmpdir(self) / "theme.json"
        file.write_text(json.dumps(data))
        return file

    def full(self, primary):
        return {role: "#123456" for role in ROLES} | {"primary": primary}

    def test_material_theme_builder_export_with_contrast_levels(self):
        file = self.write({"schemes": {"light": self.full("#aa0000"), "dark": self.full("#00aa00"),
                                       "dark-high-contrast": self.full("#0000aa")}})
        self.assertEqual(custom_theme.from_file(file, False)["primary"], "#aa0000")
        self.assertEqual(custom_theme.from_file(file, True)["primary"], "#00aa00")
        self.assertEqual(custom_theme.from_file(file, True, "high")["primary"], "#0000aa")
        self.assertEqual(custom_theme.from_file(file, True, "medium")["primary"], "#00aa00", "missing level: plain dark")

    def test_matugen_layouts_in_snake_case(self):
        per_scheme = {"colors": {"dark": {"primary": "#00aa00", "on_primary": "#ffffff"},
                                 "light": {"primary": "#aa0000", "on_primary": "#000000"}}}
        per_role = {"colors": {"primary": {"dark": "#00aa00", "light": "#aa0000", "default": "#00aa00"},
                               "surface_container": {"dark": {"color": "#101010"}, "light": {"color": "#f0f0f0"}}}}
        for data in (per_scheme, per_role):
            dark = custom_theme.from_file(self.write(data), True)
            self.assertEqual(dark["primary"], "#00aa00")
            self.assertTrue(ROLES <= set(dark), "roles it leaves out are filled in")
        self.assertEqual(custom_theme.from_file(self.write(per_role), True)["surfaceContainer"], "#101010")

    def test_a_flat_file_and_a_seed_only_file(self):
        self.assertEqual(custom_theme.from_file(self.write({"primary": "#AA00AA"}), True)["primary"], "#aa00aa")
        if custom_theme.available():
            self.assertTrue(ROLES <= set(custom_theme.from_file(self.write({"seed": "#1e88e5"}), True)))

    def test_broken_files_say_why(self):
        file = tmpdir(self) / "bad.json"
        file.write_text("{nope")
        for path, words in ((file, "isn't valid JSON"), (file.parent / "gone.json", "not found"),
                            (self.write({"name": "x"}), "no Material colours")):
            with self.assertRaisesRegex(custom_theme.ThemeError, words):
                custom_theme.from_file(path, True)

    def test_export_reads_back_as_the_same_colours(self):
        data = custom_theme.export({"source": "accent"}, accent="Teal")
        file = self.write(data)
        self.assertEqual(custom_theme.from_file(file, True)["primary"], tokens.colors("Teal", True)["primary"])
        self.assertEqual(custom_theme.from_file(file, False)["surface"], tokens.colors("Teal", False)["surface"])


class ApplyTest(unittest.TestCase):
    def tearDown(self):
        theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")   # the defaults again for the other tests

    def look(self, **changes):
        return config.look_settings({"look": changes})

    def test_a_broken_source_falls_back_to_the_accent_and_says_why(self):
        theme.apply(APP, "dark", "Blue", "standard", self.look(source="file", file="/nowhere.json"))
        self.assertEqual(theme.current["primary"], tokens.colors("Blue", True)["primary"])
        self.assertIn("not found", theme.status["error"])

    def test_material_off_gives_the_classic_look_in_the_same_colours(self):
        theme.apply(APP, "dark", "Blue", "standard", self.look(material=False))
        self.assertFalse(theme.material())
        self.assertEqual(theme.painted(), {})
        self.assertEqual(theme.current["primary"], tokens.colors("Blue", True)["primary"], "the overlay still has colours")
        self.assertNotIn("QPushButton#primary", APP.styleSheet())

    def test_shapes(self):
        for shape, expected in (("round", 20), ("rounded", 12), ("square", 4)):
            theme.apply(APP, "dark", "Blue", "standard", self.look(shape=shape))
            self.assertEqual(theme.button_radius(40), expected)

    def test_transparency_and_text_size_reach_the_stylesheet(self):
        theme.apply(APP, "dark", "Blue", "standard", self.look(opacity=80, font_scale=120))
        self.assertIn("rgba(", APP.styleSheet().split("QMainWindow, QDialog {")[1].split("}")[0])
        self.assertIn(f"font-size: {round(tokens.TYPE['titleLarge'][0] * 1.2)}px", APP.styleSheet())

    def test_motion_off_and_speed(self):
        theme.apply(APP, "dark", "Blue", "standard", self.look(animations=False))
        seen, done = [], []
        move = motion.Tween(None, motion.MEDIUM1, "standard", seen.append)
        move.when_done(lambda: done.append(True))
        move.go(0, 10)
        self.assertEqual((seen[-1], done, move.running()), (10.0, [True], False), "jumps to the end and says so")
        theme.apply(APP, "dark", "Blue", "standard", self.look(speed=2.0))
        move.go(0, 10)
        self.assertEqual(move.duration, motion.MEDIUM1 // 2)
        move.stop()


class SettingsTabTest(unittest.TestCase):
    def test_the_appearance_tab_round_trips_and_previews(self):
        from numpadctl_ui import appearance
        cfg = {"appearance": "dark", "accent": "Teal", "contrast": "medium",
               "look": {"source": "color", "seed": "#1e88e5", "shape": "square", "opacity": 85, "speed": 2.0}}
        page = appearance.AppearancePage(cfg)
        values = page.values()
        self.assertEqual((values["appearance"], values["accent"], values["contrast"]), ("dark", "Teal", "medium"))
        self.assertEqual({k: values["look"][k] for k in ("source", "seed", "shape", "opacity", "speed")},
                         {"source": "color", "seed": "#1e88e5", "shape": "square", "opacity": 85, "speed": 2.0})
        seen = []
        page.changed.connect(lambda: seen.append(page.values()["look"]["material"]))
        page.material.setChecked(False)
        self.assertEqual(seen, [False])
        page.reset()
        self.assertEqual(page.values()["look"], config.LOOK_DEFAULTS)

    def test_export_writes_a_theme_file(self):
        from numpadctl_ui import appearance
        page = appearance.AppearancePage({"accent": "Green"})
        file = tmpdir(self) / "mine.json"
        page.export(str(file))
        self.assertIn("schemes", json.loads(file.read_text()))


class WatchTest(unittest.TestCase):
    def test_a_changed_theme_file_recolours_the_app(self):
        file = tmpdir(self) / "theme.json"
        file.write_text(json.dumps({"primary": "#aa0000"}))
        cfg = {"appearance": "dark", "look": {"source": "file", "file": str(file)}}
        theme.apply(APP, "dark", "Blue", "standard", config.look_settings(cfg))
        self.addCleanup(lambda: theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard"))
        with mock.patch.object(theme, "apply", wraps=theme.apply) as applied:
            theme.watch_look(APP, lambda: cfg)
            file.write_text(json.dumps({"primary": "#00aa00"}))
            from PySide6.QtCore import QDeadlineTimer, QThread
            deadline = QDeadlineTimer(3000)
            while not applied.called and not deadline.hasExpired():
                APP.processEvents()
                QThread.msleep(20)
        self.assertTrue(applied.called, "the change was noticed")
        self.assertEqual(theme.current["primary"], "#00aa00")


if __name__ == "__main__":
    unittest.main()
