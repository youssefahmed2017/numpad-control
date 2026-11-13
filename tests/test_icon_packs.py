"""Action icon packs: reading, storing, drawing (offscreen, in a temporary settings folder)."""

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl import config, icon_packs  # noqa: E402
from numpadctl.platform import paths  # noqa: E402
from numpadctl_ui import action_icons, icon_pack_ui  # noqa: E402

APP = QApplication.instance() or QApplication([])


def png(color="#ff0000", side=200):
    image = QImage(side, side, QImage.Format_ARGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(data)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        patch = mock.patch.object(paths, "config_dir", lambda: self.dir / "cfg")
        patch.start()
        self.addCleanup(patch.stop)

    def zip(self, entries, name="p.zip"):
        path = self.dir / name
        with zipfile.ZipFile(path, "w") as z:
            for n, d in entries.items():
                z.writestr(n, d)
        return path


class ReadingTest(Base):
    def test_only_action_ids(self):
        path = self.zip({"volume_up.png": png(), "7.png": png(), "nope.png": png(), "../volume_down.png": png()})
        pack = icon_packs.read_pack(path, ["volume_up", "volume_down"])
        self.assertEqual(sorted(pack.files), ["volume_down", "volume_up"])
        self.assertTrue(any("7.png" in i for i in pack.ignored))

    def test_empty_refused(self):
        with self.assertRaises(icon_packs.PackError):
            icon_packs.read_pack(self.zip({"7.png": png()}), ["volume_up"])

    def test_case_insensitive_and_extension(self):
        pack = icon_packs.read_pack(self.zip({"Volume_Up.PNG": png(), "volume_down.txt": b"x"}), ["volume_up", "volume_down"])
        self.assertEqual(list(pack.files), ["volume_up"])


class StorageTest(Base):
    def test_slug_rules(self):
        self.assertTrue(icon_packs.valid_slug("graphite-2"))
        for bad in ("", "../x", "A", "-x", "a/b", None, "x" * 41):
            self.assertFalse(icon_packs.valid_slug(bad), bad)

    def test_path_for_is_safe(self):
        icon_packs.save("p", {"name": "P"}, {"volume_up": png()})
        self.assertIsNotNone(icon_packs.path_for("p", "volume_up"))
        for slug, action in (("p", "../volume_up"), ("../p", "volume_up"), ("p", "missing"), ("q", "volume_up"), ("p", None)):
            self.assertIsNone(icon_packs.path_for(slug, action))

    def test_same_name_replaces_new_name_gets_slug(self):
        self.assertEqual(icon_packs.slug_for("Graphite Set"), "graphite-set")
        icon_packs.save("graphite-set", {"name": "Graphite Set"}, {"volume_up": png()})
        self.assertEqual(icon_packs.slug_for("graphite set"), "graphite-set")
        icon_packs.save("other", {"name": "Other"}, {"volume_up": png()})
        self.assertEqual([p["slug"] for p in icon_packs.installed()], ["graphite-set", "other"])
        self.assertEqual(icon_packs.installed()[0]["count"], 1)

    def test_slug_clash_numbered(self):
        icon_packs.save("a-b", {"name": "Something else"}, {"volume_up": png()})
        self.assertEqual(icon_packs.slug_for("A B"), "a-b-2")

    def test_max_packs(self):
        for i in range(icon_packs.MAX_PACKS):
            icon_packs.save(f"p{i}", {"name": f"P{i}"}, {"volume_up": png()})
        with self.assertRaises(icon_packs.PackError):
            icon_packs.slug_for("one more")
        self.assertEqual(icon_packs.slug_for("p3"), "p3")      # replacing is still fine

    def test_remove_stays_inside(self):
        icon_packs.save("p", {"name": "P"}, {"volume_up": png()})
        outside = self.dir / "cfg" / "precious"
        outside.mkdir()
        self.assertFalse(icon_packs.remove("../precious"))
        self.assertTrue(outside.exists())
        self.assertTrue(icon_packs.remove("p"))
        self.assertFalse(icon_packs.remove("p"))


class ConfigTest(unittest.TestCase):
    def test_look_validates_pack(self):
        self.assertEqual(config.look_settings({"look": {"icon_pack": "ok-1"}})["icon_pack"], "ok-1")
        for bad in ("../x", "A b", 5, None):
            self.assertEqual(config.look_settings({"look": {"icon_pack": bad}})["icon_pack"], "")


class DrawingTest(Base):
    def test_pack_picture_used_and_fallback(self):
        icon_packs.save("p", {"name": "P"}, {"volume_up": png("#00ff00")})
        self.assertTrue(action_icons.pack_has("p", "volume_up"))
        self.assertFalse(action_icons.pack_has("p", "mic_mute"))
        self.assertFalse(action_icons.pack_has("", "volume_up"))
        pm = action_icons.pixmap("volume_up", "#ffffff", 28, pack="p")
        self.assertEqual(pm.toImage().pixelColor(pm.width() // 2, pm.height() // 2).green(), 255)
        self.assertEqual(pm.toImage().pixelColor(pm.width() // 2, pm.height() // 2).red(), 0)
        built = action_icons.pixmap("mic_mute", "#ffffff", 28, pack="p")      # not in the pack
        self.assertFalse(built.isNull())

    def test_install_end_to_end(self):
        path = self.zip({"volume_up.png": png(), "pack.json": b'{"name": "Mine", "author": "Me"}', "x.png": png()})
        seen = []
        result = icon_pack_ui.install(path, lambda pack, missing: seen.append((len(pack.files), len(missing))) or True)
        self.assertEqual((result.slug, result.count), ("mine", 1))
        self.assertEqual(seen[0][0], 1)
        self.assertEqual(seen[0][1], len(action_icons.ICONS) - 1)
        stored = QImage(str(icon_packs.path_for("mine", "volume_up")))
        self.assertLessEqual(stored.width(), icon_packs.SIDE)
        self.assertIsNone(icon_pack_ui.install(path, lambda *_: False))
        with self.assertRaises(icon_packs.PackError):
            icon_pack_ui.install(self.zip({"volume_up.png": b"not a picture"}, "bad.zip"))

    def test_appearance_install_and_remove(self):
        from numpadctl_ui.appearance import AppearancePage
        page = AppearancePage({})
        path = self.zip({"volume_up.png": png(), "pack.json": b'{"name": "Mine"}'})
        self.assertTrue(page.install_pack(str(path), confirm=lambda pack, missing: True))
        self.assertEqual(page.values()["look"]["icon_pack"], "mine")
        self.assertTrue(page.action_icons.isChecked())
        self.assertFalse(page.install_pack(str(path), confirm=lambda *_: False))
        self.assertTrue(page.remove_pack(confirm=lambda: True))
        self.assertEqual(page.values()["look"]["icon_pack"], "")
        self.assertEqual(icon_packs.installed(), [])


if __name__ == "__main__":
    unittest.main()
