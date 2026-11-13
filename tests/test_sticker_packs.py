"""Sticker packs: reading a pack strictly, making one with the tool, and applying one in the window (offscreen)."""

import importlib.util
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import sticker_packs, stickers  # noqa: E402
from tests import test_qt_window  # noqa: E402  (module, so its tests are not collected twice)

ROOT = Path(__file__).resolve().parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 256, 256) + b"x" * 20   # enough to be told apart


def png(side=256):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", side, side) + b"x" * 20


class ReadingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def zip(self, entries, name="pack.zip"):
        path = self.dir / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for filename, data in entries.items():
                z.writestr(filename, data)
        return path

    def test_the_19_keys_and_their_file_names(self):
        self.assertEqual(len(sticker_packs.ALL_KEYS), 19)
        names = {"7": "7", "000": "000", "dot": ".", "plus": "+", "minus": "-", "star": "*", "slash": "/",
                 "enter": "Enter", "numlock": "NumLock", "backspace": "Backspace"}
        for name, key in names.items():
            self.assertEqual(sticker_packs.KEY_FILE_NAMES[name], key)

    def test_a_folder_names_are_matched_in_any_case_and_odd_files_are_reported(self):
        for name, data in (("7.png", PNG), ("Plus.PNG", PNG), ("ENTER.svg", b"<svg/>"), ("dot.jpg", PNG), ("notes.txt", b"hi"),
                           ("seven.png", PNG), (".hidden.png", PNG)):
            (self.dir / name).write_bytes(data)
        (self.dir / "pack.json").write_text(json.dumps({"name": "Pastel", "author": "Me", "license": "Personal use"}))
        pack = sticker_packs.read_pack(self.dir)
        self.assertEqual(sorted(pack.files), ["+", ".", "7", "Enter"])
        self.assertEqual((pack.name, pack.author, pack.license), ("Pastel", "Me", "Personal use"))
        self.assertEqual(pack.files["Enter"], (".svg", b"<svg/>"))
        self.assertTrue(any("notes.txt" in note for note in pack.ignored) and any("seven.png" in note for note in pack.ignored))

    def test_a_zip_works_even_when_the_pictures_sit_in_a_folder_and_junk_is_skipped(self):
        path = self.zip({"My pack/7.png": PNG, "My pack/pack.json": json.dumps({"name": "In a folder"}), "__MACOSX/._7.png": b"junk"})
        pack = sticker_packs.read_pack(path)
        self.assertEqual((sorted(pack.files), pack.name), (["7"], "In a folder"))

    def test_names_that_try_to_leave_the_folder_never_touch_the_disk(self):
        path = self.zip({"../../7.png": PNG, "/etc/passwd": b"x", "a/../../evil.png": PNG})
        before = sorted(p.name for p in self.dir.parent.iterdir())
        pack = sticker_packs.read_pack(path)
        self.assertEqual(sorted(pack.files), ["7"])           # only the bare name counts, and nothing is extracted anywhere
        self.assertEqual(sorted(p.name for p in self.dir.parent.iterdir()), before)

    def test_text_in_pack_json_is_cleaned_and_a_broken_file_is_only_reported(self):
        path = self.zip({"7.png": PNG, "pack.json": json.dumps({"name": "A‮B\x00C" + "x" * 200, "author": 5, "license": ["x"]})})
        pack = sticker_packs.read_pack(path)
        self.assertNotIn("‮", pack.name)
        self.assertEqual((len(pack.name) <= sticker_packs.MAX_TEXT, pack.author, pack.license), (True, "", ""))
        bad = sticker_packs.read_pack(self.zip({"7.png": PNG, "pack.json": "{not json"}, "bad.zip"))
        self.assertEqual((bad.name, sorted(bad.files)), ("", ["7"]))
        self.assertTrue(any("pack.json" in n for n in bad.ignored))
        self.assertEqual(sticker_packs.read_pack(self.zip({"7.png": PNG, "pack.json": "[1]"}, "list.zip")).name, "")

    def test_two_pictures_for_one_key_use_the_first_by_name(self):
        pack = sticker_packs.read_pack(self.zip({"7.svg": b"<svg/>", "7.png": PNG}))
        self.assertEqual(pack.files["7"][0], ".png")
        self.assertTrue(any("already used" in n for n in pack.ignored))

    def test_what_is_not_a_pack_is_refused_in_words(self):
        for make, message in ((lambda: self.dir / "missing.zip", "isn't a zip"),
                              (lambda: self.zip({"readme.txt": b"x"}, "empty.zip"), "no pictures named after keys")):
            with self.assertRaisesRegex(sticker_packs.PackError, message):
                sticker_packs.read_pack(make())
        notzip = self.dir / "fake.zip"
        notzip.write_bytes(b"this is not a zip")
        with self.assertRaisesRegex(sticker_packs.PackError, "isn't a zip"):
            sticker_packs.read_pack(notzip)
        corrupt = self.zip({"7.png": PNG}, "corrupt.zip")
        corrupt.write_bytes(corrupt.read_bytes()[:-30])
        with self.assertRaises(sticker_packs.PackError):
            sticker_packs.read_pack(corrupt)

    def test_a_picture_too_big_and_a_zip_bomb_are_refused(self):
        with mock.patch.object(sticker_packs, "MAX_PICTURE_BYTES", 1000):
            with self.assertRaisesRegex(sticker_packs.PackError, "bigger than"):
                sticker_packs.read_pack(self.zip({"7.png": b"x" * 5000}))
        bomb = self.zip({"7.png": b"\0" * 6_000_000}, "bomb.zip")      # a few KB on disk, 6 MB when read
        self.assertLess(bomb.stat().st_size, 20_000)
        with self.assertRaisesRegex(sticker_packs.PackError, "bigger than"):
            sticker_packs.read_pack(bomb)
        with mock.patch.object(sticker_packs, "MAX_TOTAL_BYTES", 150):
            with self.assertRaisesRegex(sticker_packs.PackError, "together"):
                sticker_packs.read_pack(self.zip({"7.png": b"x" * 100, "8.png": b"x" * 100}, "total.zip"))

    def test_only_the_first_entries_are_looked_at(self):
        junk = {f"1junk{i:03}.txt": b"x" for i in range(sticker_packs.MAX_ENTRIES - 1)}      # these sort before "7.png"
        self.assertEqual(sorted(sticker_packs.read_pack(self.zip({**junk, "7.png": PNG}, "ok.zip")).files), ["7"])   # the 64th entry
        junk["1junk999.txt"] = b"x"
        with self.assertRaisesRegex(sticker_packs.PackError, "no pictures"):                  # now "7.png" is the 65th: not looked at
            sticker_packs.read_pack(self.zip({**junk, "7.png": PNG}, "many.zip"))


def load_tool():
    spec = importlib.util.spec_from_file_location("make_sticker_pack", ROOT / "tools" / "make-sticker-pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pics = self.dir / "pictures"
        self.pics.mkdir()
        self.tool = load_tool()

    def run_tool(self, *args):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            code = self.tool.main([str(self.pics), *args])
        return code, out.getvalue()

    def test_it_makes_a_pack_the_app_can_read_and_says_what_is_missing(self):
        for name in ("7", "8", "plus", "enter"):
            (self.pics / f"{name}.png").write_bytes(png(256))
        code, text = self.run_tool("--name", "Pastel Pack!", "--author", "Me", "--license", "Personal use only")
        self.assertEqual(code, 0)
        zip_path = self.dir / "NumpadControl-stickers-pastel-pack.zip"
        self.assertTrue(zip_path.exists())
        self.assertIn("4 of 19 keys have a picture; missing:", text)
        pack = sticker_packs.read_pack(zip_path)
        self.assertEqual((pack.name, pack.author, pack.license, sorted(pack.files)), ("Pastel Pack!", "Me", "Personal use only", ["+", "7", "8", "Enter"]))
        names = zipfile.ZipFile(zip_path).namelist()
        self.assertEqual((names[0], sorted(names[1:])), ("pack.json", ["7.png", "8.png", "enter.png", "plus.png"]))

    def test_the_same_pictures_always_make_the_same_zip(self):
        (self.pics / "7.png").write_bytes(png(256))
        self.run_tool("--name", "Same", "-o", str(self.dir / "a.zip"))
        self.run_tool("--name", "Same", "-o", str(self.dir / "b.zip"))
        self.assertEqual((self.dir / "a.zip").read_bytes(), (self.dir / "b.zip").read_bytes())

    def test_small_or_non_square_pictures_are_flagged_and_a_license_file_is_included(self):
        (self.pics / "7.png").write_bytes(png(64))
        (self.pics / "8.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 300, 150) + b"x" * 20)
        licence = self.dir / "TERMS.txt"
        licence.write_text("Personal use only.")
        code, text = self.run_tool("--name", "Warn", "--license-file", str(licence))
        self.assertEqual(code, 0)
        self.assertIn("key 7: 64x64 is smaller than 128 px", text)
        self.assertIn("key 8: 300x150 isn't square", text)
        self.assertIn("LICENSE.txt", zipfile.ZipFile(self.dir / "NumpadControl-stickers-warn.zip").namelist())

    def test_a_folder_with_no_key_pictures_is_an_error_and_writes_nothing(self):
        (self.pics / "readme.txt").write_text("x")
        code, text = self.run_tool("--name", "Nothing")
        self.assertEqual(code, 1)
        self.assertIn("no pictures named after keys", text)
        self.assertEqual(list(self.dir.glob("*.zip")), [])


def real_png(path, colour="#e91e63"):
    from PySide6.QtGui import QColor, QImage
    image = QImage(200, 200, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    image.save(str(path), "PNG")
    return path


class WindowTest(unittest.TestCase):
    def setUp(self):
        test_qt_window.QtWindowTest.setUp(self)          # a real settings window on a temporary config
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.object(stickers.paths, "config_dir", lambda: self.root)   # pictures go to the temporary folder
        patch.start()
        self.addCleanup(patch.stop)

    def pack(self, names, name="packs.zip", info=None):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.write(real_png(self.root / f"_{n}.png"), f"{n}.png")
            if info:
                z.writestr("pack.json", json.dumps(info))
        return path

    def test_applying_a_pack_gives_the_keys_their_stickers(self):
        path = self.pack(["7", "plus", "enter"], info={"name": "Pastel", "author": "Me"})
        seen = []
        self.assertTrue(self.w.apply_sticker_pack(path, confirm=lambda pack, keys, replacing: seen.append((pack.name, sorted(keys), replacing)) or True))
        self.assertEqual(seen, [("Pastel", ["+", "7", "Enter"], [])])
        stickers_set = self.w.profile["stickers"]
        self.assertEqual(sorted(stickers_set), ["+", "7", "Enter"])
        self.assertTrue(all(stickers.path_for(n) and stickers.path_for(n).exists() for n in stickers_set.values()))
        self.assertTrue(self.w.dirty)
        self.assertTrue(self.w.key_buttons["7"].sticker)

    def test_saying_no_changes_nothing_and_applying_again_says_what_it_replaces(self):
        path = self.pack(["7", "8"])
        self.assertFalse(self.w.apply_sticker_pack(path, confirm=lambda *a: False))
        self.assertNotIn("stickers", self.w.profile)
        self.w.apply_sticker_pack(path, confirm=lambda *a: True)
        seen = []
        self.w.apply_sticker_pack(path, confirm=lambda pack, keys, replacing: seen.append(sorted(replacing)) or True)
        self.assertEqual(seen, [["7", "8"]])

    def test_a_pack_for_keys_this_pad_does_not_show_is_refused_in_words(self):
        from PySide6.QtWidgets import QMessageBox
        path = self.pack(["7"])
        with mock.patch.dict(self.w.key_buttons, clear=True), mock.patch.object(QMessageBox, "warning") as warned:
            self.assertFalse(self.w.apply_sticker_pack(path, confirm=lambda *a: self.fail("nothing to apply")))
        self.assertIn("None of this pack's pictures", warned.call_args.args[2])

    def test_something_that_is_not_a_pack_shows_a_message_and_changes_nothing(self):
        from PySide6.QtWidgets import QMessageBox
        bad = self.root / "bad.zip"
        bad.write_bytes(b"not a zip")
        with mock.patch.object(QMessageBox, "warning") as warned:
            self.assertFalse(self.w.apply_sticker_pack(bad, confirm=lambda *a: self.fail("should not ask")))
        self.assertIn("can't be used", warned.call_args.args[2])
        self.assertNotIn("stickers", self.w.profile)

    def test_a_picture_that_is_not_really_a_picture_is_skipped_but_the_rest_apply(self):
        path = self.root / "mixed.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.write(real_png(self.root / "_7.png"), "7.png")
            z.writestr("8.png", b"this is not a picture")
        self.assertTrue(self.w.apply_sticker_pack(path, confirm=lambda *a: True))
        self.assertEqual(sorted(self.w.profile["stickers"]), ["7"])


if __name__ == "__main__":
    unittest.main()
