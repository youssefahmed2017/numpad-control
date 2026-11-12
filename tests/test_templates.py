"""Your own Python templates: listed without running, run in their own limited process, checked like an
imported profile, and only ever filling keys that have nothing yet."""

import os
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import config, templates  # noqa: E402

CFG = {"layer_key": "NumLock", "modes": ["Stream mode"], "profiles": []}


def profile(**layers):
    return {"name": "Default", "match": "", "bindings": layers.get("bindings", {}),
            "layer_bindings": layers.get("layer_bindings", {})}


class TemplatesTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patch = mock.patch.object(config, "CONFIG_DIR", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, name, code):
        templates.folder().mkdir(parents=True, exist_ok=True)
        path = templates.folder() / name
        path.write_text(textwrap.dedent(code))
        return path

    def test_listing_reads_names_without_running_anything(self):
        marker = self.root / "ran"
        self.write("a_pad.py", f'''
            NAME = "Streaming pro"
            DESCRIPTION = "Scenes and mute."
            open({str(marker)!r}, "w").write("ran")   # would only happen if it were run
            def build(pad):
                pass
        ''')
        self.write("broken.py", "def build(pad)\n    pass\n")
        self.write("no_build.py", '"""Just a docstring."""\n')
        self.write("_private.py", "def build(pad): pass\n")
        found = {t.path.name: t for t in templates.list_templates()}
        self.assertEqual(set(found), {"a_pad.py", "broken.py", "no_build.py"}, "_files are skipped")
        self.assertEqual((found["a_pad.py"].name, found["a_pad.py"].description, found["a_pad.py"].problem),
                         ("Streaming pro", "Scenes and mute.", ""))
        self.assertIn("line 1", found["broken.py"].problem)
        self.assertEqual(found["no_build.py"].problem, "has no build(pad) function")
        self.assertFalse(marker.exists(), "nothing was run to make the list")

    def test_a_template_fills_both_layers_with_defaults_macros_and_notes(self):
        path = self.write("pad.py", '''
            def build(pad):
                for n in range(1, 4):
                    pad.tap(str(n), "open_url", url=f"https://example.com/{n}")
                pad.hold("5", "mic_mute")
                pad.layer.tap("7", "volume_up")
                pad.macro("9", [step("press_keys", keys="ctrl+c"), step("press_keys", keys="ctrl+v")])
                pad.if_mode("8", "Stream mode", [step("mic_mute")], [step("media_play_pause")])
                pad.note(f"made for {pad.profile} on {pad.platform}, layer key {pad.layer_key}")
        ''')
        result = templates.run(path, CFG, profile())
        self.assertEqual(result.bindings["2"]["tap"], {"action": "open_url", "params": {"url": "https://example.com/2"}})
        self.assertEqual(result.bindings["5"]["hold"]["action"], "mic_mute")
        self.assertEqual(result.layer_bindings["7"]["tap"]["action"], "volume_up")
        self.assertEqual([s["action"] for s in result.bindings["9"]["tap"]["params"]["steps"]], ["press_keys"] * 2)
        self.assertEqual(result.bindings["8"]["tap"]["params"]["mode"], "Stream mode")
        self.assertEqual(result.notes, [f"made for Default on {'linux' if sys.platform.startswith('linux') else sys.platform}"
                                        ", layer key NumLock"])
        self.assertEqual(result.dropped, [])

    def test_what_a_profile_file_couldnt_have_is_left_out_with_reasons(self):
        path = self.write("odd.py", '''
            def build(pad):
                pad.tap("1", "no_such_action")
                pad.tap("2", "volume_up")
                pad.if_mode("3", "A mode that isn't there", [step("mic_mute")])
        ''')
        result = templates.run(path, CFG, profile())
        self.assertEqual(list(result.bindings), ["2"])
        self.assertTrue(any("no_such_action" in d for d in result.dropped))
        self.assertTrue(any("key 3" in d for d in result.dropped), result.dropped)

    def test_mistakes_say_what_and_where(self):
        cases = {
            "boom.py": ("def build(pad):\n    x = 1\n    return 1 / 0\n", "ZeroDivisionError: division by zero (line 3)"),
            "slot.py": ("def build(pad):\n    pad.set('1', 'triple', 'volume_up')\n", "slot must be"),
            "nobuild.py": ("X = 1\n", "no build(pad) function"),
        }
        for name, (code, words) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(templates.TemplateError, re.escape(words)):
                templates.run(self.write(name, code), CFG, profile())

    def test_a_runaway_template_is_stopped(self):
        path = self.write("forever.py", "def build(pad):\n    while True:\n        pass\n")
        with mock.patch.object(templates, "TIMEOUT", 1), \
                self.assertRaisesRegex(templates.TemplateError, "longer than 1 seconds|failed"):
            templates.run(path, CFG, profile())

    @unittest.skipUnless(sys.platform.startswith("linux"), "the file and process limits are Linux's")
    def test_on_linux_it_cant_write_files_or_start_programs(self):
        target = self.root / "written.txt"
        writes = self.write("writes.py", f"def build(pad):\n    with open({str(target)!r}, 'w') as f:\n"
                                         "        f.write('x' * 10)\n")
        with self.assertRaises(templates.TemplateError):
            templates.run(writes, CFG, profile())
        self.assertFalse(target.exists() and target.read_text())
        spawns = self.write("spawns.py", "import subprocess\ndef build(pad):\n    subprocess.run(['true'])\n")
        with self.assertRaises(templates.TemplateError):
            templates.run(spawns, CFG, profile())

    def test_applying_keeps_keys_that_already_do_something(self):
        path = self.write("pad.py", 'def build(pad):\n    pad.tap("1", "volume_up")\n    pad.tap("2", "volume_down")\n'
                                    '    pad.layer.tap("1", "mic_mute")\n')
        mine = profile(bindings={"1": {"tap": {"action": "lock_screen", "params": {}}}})
        result = templates.run(path, CFG, mine)
        self.assertEqual(templates.apply(result, mine), (2, 1))
        self.assertEqual(mine["bindings"]["1"]["tap"]["action"], "lock_screen")
        self.assertEqual(mine["bindings"]["2"]["tap"]["action"], "volume_down")
        self.assertEqual(mine["layer_bindings"]["1"]["tap"]["action"], "mic_mute")

    def test_the_example_template_works_as_written(self):
        path = templates.new_template("My pad")
        self.assertEqual(templates.describe(path).name, "My pad")
        self.assertNotEqual(templates.new_template("My pad"), path, "a second one gets a free name")
        result = templates.run(path, CFG, profile())
        self.assertEqual(result.dropped, [])
        self.assertGreaterEqual(len(result.bindings) + len(result.layer_bindings), 7)

    def test_the_action_list_for_template_writers(self):
        text = templates.describe_actions()
        self.assertIn("open_url", text)
        self.assertIn("settings: url=''", text)


class PresetDialogTest(unittest.TestCase):
    def test_templates_are_listed_after_the_presets_and_broken_ones_cant_be_picked(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from numpadctl import presets
        from numpadctl_ui import dialogs, theme, tokens
        theme.apply(QApplication.instance(), "dark", tokens.DEFAULT_ACCENT, "standard")
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(config, "CONFIG_DIR", Path(folder)):
            templates.new_template("Mine")
            (templates.folder() / "bad.py").write_text("def build(:\n")
            dialog = dialogs.PresetDialog(None, "Default")
            self.addCleanup(dialog.deleteLater)
            self.assertEqual(dialog.list.count(), len(presets.PRESETS) + 2)
            names = [e.name for e in dialog.entries]
            dialog.list.setCurrentRow(names.index("Mine"))
            self.assertIsInstance(dialog.chosen(), templates.Template)
            dialog.list.setCurrentRow(names.index("Bad"))
            self.assertIsNone(dialog.chosen())
            self.assertFalse(dialog.ok.isEnabled())


if __name__ == "__main__":
    unittest.main()


class ManageInTheAppTest(unittest.TestCase):
    """Everything without a terminal: write, try, save, import and delete templates from the dialogs."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from numpadctl_ui import theme, tokens
        theme.apply(QApplication.instance(), "dark", tokens.DEFAULT_ACCENT, "standard")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(config, "CONFIG_DIR", Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)

        class Window:   # what the editor reads from the main window
            cfg = CFG
            profile = profile()
        self.window = Window()

    def editor(self, path=None):
        from numpadctl_ui.template_editor import TemplateEditor
        editor = TemplateEditor(None, self.window, path)
        self.addCleanup(editor.deleteLater)
        return editor

    def test_write_insert_try_and_save_a_new_template(self):
        editor = self.editor()
        editor.code.setPlainText('NAME = "Desk pad"\n\ndef build(pad):\n    pad.tap("1", "volume_up")\n')
        cursor = editor.code.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.Up)   # on the pad.tap line
        editor.code.setTextCursor(cursor)
        row = next(r for r in range(editor.list.count()) if editor.list.item(r).data(Qt_UserRole_1()) == "lock_screen")
        editor.insert(editor.list.item(row))
        self.assertIn('    pad.tap("1", "lock_screen")', editor.code.toPlainText())
        editor.try_it()
        self.assertTrue(editor.result.text().startswith("✓"), editor.result.text())
        self.assertIn("Lock screen", editor.result.text())
        self.assertEqual(list(templates.folder().glob("*.py")), [], "trying saves nothing")
        editor.save()
        self.assertEqual(editor.path.name, "desk_pad.py")
        self.assertEqual(templates.describe(editor.path).name, "Desk pad")

    def test_try_it_reports_mistakes_with_their_line(self):
        editor = self.editor()
        editor.code.setPlainText("def build(pad):\n    pad.tap('1', 'volume_up'\n")
        editor.try_it()
        self.assertTrue(editor.result.text().startswith("✗ Line"), editor.result.text())
        editor.code.setPlainText("def build(pad):\n    x = [][3]\n")
        editor.try_it()
        self.assertIn("IndexError", editor.result.text())
        self.assertIn("line 2", editor.result.text())

    def test_editing_keeps_the_same_file(self):
        path = templates.new_template("Mine")
        editor = self.editor(path)
        self.assertIn('NAME = "Mine"', editor.code.toPlainText())
        editor.code.setPlainText(editor.code.toPlainText().replace('"Mine"', '"Mine v2"'))
        editor.save()
        self.assertEqual(editor.path, path)
        self.assertEqual(templates.describe(path).name, "Mine v2")

    def test_import_and_delete(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            shared = Path(elsewhere) / "from_a_friend.py"
            shared.write_text('NAME = "Friend\'s pad"\ndef build(pad):\n    pad.tap("1", "mic_mute")\n')
            path = templates.import_template(shared)
            (Path(elsewhere) / "notes.txt").write_text("hi")
            with self.assertRaisesRegex(templates.TemplateError, "isn't a Python file"):
                templates.import_template(Path(elsewhere) / "notes.txt")
        self.assertEqual(path.parent, templates.folder())
        self.assertEqual(templates.describe(path).name, "Friend's pad")
        templates.delete_template(path)
        self.assertFalse(path.exists())
        with self.assertRaises(templates.TemplateError):
            templates.delete_template(Path("/etc/hosts"))

    def test_a_broken_template_can_be_opened_to_fix_but_not_applied(self):
        from numpadctl_ui import dialogs
        (templates.folder()).mkdir(parents=True, exist_ok=True)
        (templates.folder() / "half.py").write_text("def build(pad:\n")
        dialog = dialogs.PresetDialog(None, "Default")
        self.addCleanup(dialog.deleteLater)
        names = [e.name for e in dialog.entries]
        dialog.list.setCurrentRow(names.index("Half"))
        self.assertIsNone(dialog.chosen())
        self.assertFalse(dialog.ok.isEnabled())
        self.assertTrue(dialog.template_buttons["Edit…"].isEnabled())
        dialog.list.setCurrentRow(0)   # a built-in preset: nothing to edit or delete
        self.assertFalse(dialog.template_buttons["Delete"].isEnabled())


def Qt_UserRole_1():
    from numpadctl_ui.template_editor import ID_ROLE
    return ID_ROLE
