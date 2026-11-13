"""Stickers: a picture for a key, shown on the pad in the settings window and on the key map overlay."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from numpadctl import config, daemon, modes, profile_io, stickers, ui_common  # noqa: E402
from numpadctl_ui import hud as hud_module, picker as picker_module, sticker_image, window as window_module  # noqa: E402

APP = QApplication.instance() or QApplication([])
A, B = "0123456789abcdef.png", "fedcba9876543210.png"


def picture(path, width=300, height=200, colour="#e91e63"):
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    assert image.save(str(path))
    return str(path)


class NamesAndLookupTest(unittest.TestCase):
    def test_only_names_we_made_are_paths(self):
        for bad in ("../x.png", "/etc/passwd", "0123456789abcdef", "0123456789ABCDEF.png", "0123456789abcdef.png\n",
                    "a/0123456789abcdef.png", None, 5, ""):
            self.assertIsNone(stickers.path_for(bad), repr(bad))
        self.assertEqual(stickers.path_for(A), stickers.folder() / A)

    def test_clean_drops_what_is_not_a_sticker(self):
        profile = {"stickers": {"7": A, "8": "../../etc/passwd", "9": 5, 3: A}}
        self.assertEqual(stickers.clean(profile), {"7": A})
        self.assertEqual(stickers.clean({"stickers": "nope"}), {})
        self.assertEqual(stickers.clean({}), {})

    def test_a_profile_uses_the_defaults_sticker_for_keys_it_has_none_for(self):
        profiles = [{"name": "Default", "match": "", "stickers": {"7": A, "8": A}},
                    {"name": "OBS", "match": "obs", "stickers": {"7": B}}]
        self.assertEqual(stickers.lookup(profiles, "7", index=1), B)
        self.assertEqual(stickers.lookup(profiles, "8", index=1), A)
        self.assertEqual(stickers.lookup(profiles, "7", index=0), A)
        self.assertEqual(stickers.lookup(profiles, "9", index=1), "")

    def test_the_focused_apps_profile_wins(self):
        profiles = [{"name": "Default", "match": "", "stickers": {"7": A}},
                    {"name": "OBS", "match": "obs", "stickers": {"7": B}}]
        self.assertEqual(stickers.lookup(profiles, "7", "obs"), B)
        self.assertEqual(stickers.lookup(profiles, "7", "kitty"), A)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.object(stickers.paths, "config_dir", lambda: self.root)
        patch.start()
        self.addCleanup(patch.stop)
        sticker_image._cache.clear()

    def test_a_picture_becomes_a_small_png_named_after_its_content(self):
        name = sticker_image.make(picture(self.root / "big.png", 1000, 500))
        self.assertTrue(stickers.NAME.fullmatch(name))
        stored = QImage(str(stickers.path_for(name)))
        self.assertEqual((stored.width(), stored.height()), (128, 64), "shrunk to fit, same proportions")
        self.assertEqual(sticker_image.make(picture(self.root / "same.png", 1000, 500)), name, "stored once")

    def test_a_small_picture_is_not_blown_up(self):
        name = sticker_image.make(picture(self.root / "tiny.png", 20, 20))
        self.assertEqual(QImage(str(stickers.path_for(name))).width(), 20)

    def test_what_isnt_a_picture_is_refused_plainly(self):
        (self.root / "notes.txt").write_text("hello")
        with self.assertRaisesRegex(sticker_image.StickerError, "doesn't look like a picture"):
            sticker_image.make(self.root / "notes.txt")
        with self.assertRaisesRegex(sticker_image.StickerError, "Couldn't read"):
            sticker_image.make(self.root / "missing.png")
        self.assertFalse((self.root / "stickers").exists() and list((self.root / "stickers").iterdir()))

    def test_huge_files_are_refused_before_opening(self):
        big = self.root / "big.png"
        big.write_bytes(b"x")
        with mock.patch.object(stickers, "MAX_SOURCE_BYTES", 0), \
                self.assertRaisesRegex(sticker_image.StickerError, "too big"):
            sticker_image.make(big)

    def test_saving_deletes_the_pictures_nothing_uses(self):
        used, orphan = sticker_image.make(picture(self.root / "a.png", colour="#00ff00")), \
            sticker_image.make(picture(self.root / "b.png", colour="#0000ff"))
        (stickers.folder() / "notes.txt").write_text("not ours: stays")
        other_set = {"name": "Other", "profiles": [{"name": "Default", "stickers": {"1": used}}]}
        stickers.prune({"sets": [other_set], "profiles": []})
        self.assertTrue(stickers.path_for(used).exists(), "a picture used in another set is kept")
        self.assertFalse(stickers.path_for(orphan).exists())
        self.assertTrue((stickers.folder() / "notes.txt").exists())

    def test_exporting_a_profile_leaves_stickers_out(self):
        profile = {"name": "P", "match": "", "stickers": {"7": A},
                   "bindings": {"7": {"tap": {"action": "mic_mute", "params": {}}}}, "layer_bindings": {}}
        self.assertNotIn(A, json.dumps(profile_io.export_profile(profile, "0.3.1")))


class FakeLink:
    connected = False

    def __init__(self, on_message, dispatch):
        pass

    def send(self, message):
        pass


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        path = root / "config.json"
        path.write_text(json.dumps({
            "device": {"vendor": "c0f4", "product": "05f5"}, "layer_key": None,
            "profiles": [{"name": "Default", "match": "", "layer_bindings": {}, "bindings": {}},
                         {"name": "OBS", "match": "obs", "layer_bindings": {}, "bindings": {}}]}))
        self.config_path = path
        patches = [mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", path),
                   mock.patch.object(stickers.paths, "config_dir", lambda: root),
                   mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "m.json"),
                   mock.patch.object(picker_module, "RECENT_PATH", root / "recent.json"),
                   mock.patch.object(ui_common, "ServiceLink", FakeLink)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        sticker_image._cache.clear()
        self.root = root
        self.w = window_module.MainWindow()
        self.addCleanup(self.w.deleteLater)

    def test_choosing_a_picture_puts_it_on_the_key_and_saving_keeps_it(self):
        self.w.select("7")
        self.assertFalse(self.w.key_buttons["7"].sticker)
        self.assertTrue(self.w.choose_sticker("7", picture(self.root / "p.png")))
        button = self.w.key_buttons["7"]
        self.assertTrue(button.sticker)
        self.assertFalse(button.picture.isHidden())
        self.assertTrue(button.name.isHidden(), "the picture takes the place of the key's name")
        self.assertTrue(self.w.dirty)
        self.assertTrue(self.w.save())
        saved = json.loads(self.config_path.read_text())["sets"][0]["profiles"][0]["stickers"]
        self.assertEqual(saved, {"7": button.sticker})
        self.assertTrue(stickers.path_for(button.sticker).exists())

    def test_each_profile_has_its_own_stickers_and_falls_back_to_default(self):
        self.w.select("7")
        self.w.choose_sticker("7", picture(self.root / "p.png"))
        default_sticker = self.w.key_buttons["7"].sticker
        self.w.profile_index = 1
        self.w.refresh_pad()
        self.assertEqual(self.w.key_buttons["7"].sticker, default_sticker, "OBS has none: Default's shows")
        self.w.choose_sticker("7", picture(self.root / "q.png", colour="#2196f3"))
        own = self.w.key_buttons["7"].sticker
        self.assertNotEqual(own, default_sticker)
        self.w.profile_index = 0
        self.w.refresh_pad()
        self.assertEqual(self.w.key_buttons["7"].sticker, default_sticker, "Default is untouched")
        self.w.profile_index = 1
        self.w.set_sticker("7", "")
        self.w.refresh_pad()
        self.assertEqual(self.w.key_buttons["7"].sticker, default_sticker, "removing falls back again")

    def test_a_bad_file_shows_a_message_and_changes_nothing(self):
        (self.root / "notes.txt").write_text("hello")
        with mock.patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self.w.choose_sticker("7", str(self.root / "notes.txt")))
        warning.assert_called_once()
        self.assertFalse(self.w.dirty and self.w.profile.get("stickers"))

    def test_removing_the_sticker_brings_the_name_back(self):
        self.w.choose_sticker("7", picture(self.root / "p.png"))
        self.w.set_sticker("7", "")
        button = self.w.key_buttons["7"]
        self.assertFalse(button.sticker)
        self.assertFalse(button.name.isHidden())


class ServiceAndOverlayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patch = mock.patch.object(stickers.paths, "config_dir", lambda: root)
        patch.start()
        self.addCleanup(patch.stop)
        sticker_image._cache.clear()
        self.root = root

    def test_the_service_sends_the_stickers_of_the_keys_the_overlay_shows(self):
        name = sticker_image.make(picture(self.root / "p.png"))
        cfg = config._migrate({"layer_key": ".", "profiles": [
            {"name": "Default", "match": "", "stickers": {"7": name, "9": name},
             "bindings": {}, "layer_bindings": {"7": {"tap": {"action": "mic_mute", "params": {}}}}}]})
        d = daemon.Daemon.__new__(daemon.Daemon)
        d.cfg = cfg
        message = d.hud_message(True)
        self.assertEqual(message["stickers"], {"7": name}, "only for keys that are shown")
        self.assertEqual(d.hud_message(False)["stickers"], {})

    def test_the_overlay_draws_a_sticker_instead_of_the_key_name(self):
        name = sticker_image.make(picture(self.root / "p.png", colour="#ff0000"))
        from numpadctl_ui import theme, tokens
        theme.apply(APP, "light", tokens.DEFAULT_ACCENT, "standard")
        hud = hud_module.Hud()
        hud.show_keys({"7": "Mute"}, 100, {"7": name, "8": "../../etc/passwd"})
        hud.alpha = 1.0
        image = hud.grab().toImage()
        # the 7 key sits at row 1, column 0: its sticker (red) is where the name would be
        x = hud_module.PAD + hud_module.CELL_W // 2
        y = hud_module.PAD + hud_module.TITLE_H + 1 * (hud_module.CELL_H + hud_module.GAP) + 4 + hud_module.STICKER // 2
        self.assertGreater(image.pixelColor(x, y).red(), 200)
        self.assertLess(image.pixelColor(x, y).green(), 80)
        hud.deleteLater()


class KeySizingTest(unittest.TestCase):
    """A sticker is drawn as big as its key has room for, not at one fixed size."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.object(stickers.paths, "config_dir", lambda: self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.name = sticker_image.make(picture(self.root / "p.png", 128, 128))

    @staticmethod
    def resized(button, w, h):
        """Resize `button` and deliver the resize event the way a shown key gets it (a hidden widget only gets it on show)."""
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QResizeEvent
        old = button.size()
        button.resize(w, h)
        button.resizeEvent(QResizeEvent(QSize(w, h), old))

    def key(self, w, h, compact=False):
        from numpadctl_ui.window import KeyButton
        button = KeyButton("7", compact=compact)
        self.addCleanup(button.deleteLater)
        button.resize(w, h)
        button.set_sticker(self.name)
        return button

    def test_a_bigger_key_gets_a_bigger_sticker_up_to_a_limit(self):
        small, normal, huge = self.key(60, 50), self.key(105, 66), self.key(400, 400)
        sides = [b._sticker_side_now for b in (small, normal, huge)]
        self.assertLess(sides[0], sides[1])
        self.assertLess(sides[1], sides[2])
        self.assertEqual(sides[2], 64)                     # a sticker is stored at 128 px: no bigger than that is useful
        self.assertGreater(sides[1], 30)                   # more than the old fixed size on a normal key

    def test_the_sticker_follows_the_key_when_it_is_resized(self):
        button = self.key(105, 66)
        before = button._sticker_side_now
        self.resized(button, 200, 160)
        self.assertGreater(button._sticker_side_now, before)
        self.resized(button, 60, 50)
        self.assertLess(button._sticker_side_now, before)
        self.assertEqual(button._sticker_pix.deviceIndependentSize().width(), button._sticker_side_now)

    def test_a_compact_key_keeps_a_small_sticker_and_never_goes_below_a_minimum(self):
        compact = self.key(40, 30, compact=True)
        self.assertLessEqual(compact._sticker_side_now, 30)
        self.assertGreaterEqual(compact._sticker_side_now, 14)
        tiny = self.key(5, 5)
        self.assertGreaterEqual(tiny._sticker_side_now, 24)


if __name__ == "__main__":
    unittest.main()
