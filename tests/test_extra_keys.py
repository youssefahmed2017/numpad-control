"""Learn mode in the window: unknown keys are added to the pad, named, bound, saved and removed."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from numpadctl import config, keys, modes, ui_common  # noqa: E402
from numpadctl_ui import dialogs, window as window_module  # noqa: E402

APP = QApplication.instance() or QApplication([])


class FakeLink:
    connected = True

    def __init__(self, on_message, dispatch):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.path = root / "config.json"
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        self.path.write_text(json.dumps(cfg))
        for p in (mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", self.path),
                  mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "m.json"),
                  mock.patch.object(ui_common, "ServiceLink", FakeLink),
                  mock.patch.object(ui_common, "installed_apps", lambda: [])):
            p.start()
            self.addCleanup(p.stop)
        self.w = window_module.MainWindow()
        self.addCleanup(self.w.deleteLater)

    def press(self, key, label=None, unknown=True):
        self.w.on_service_message({"event": "key", "key": key, "label": label or keys.label_for(key), "unknown": unknown})

    def test_unknown_key_is_ignored_unless_learning(self):
        self.press("KEY_TAB")
        self.assertNotIn("KEY_TAB", self.w.key_buttons)
        self.assertEqual(self.w.cfg["extra_keys"], [])

    def test_learn_mode_adds_the_key_to_the_pad_and_selects_it(self):
        self.w.learn.setChecked(True)
        self.press("KEY_TAB")
        self.assertIn("KEY_TAB", self.w.key_buttons)
        self.assertEqual(self.w.selected, "KEY_TAB")
        self.assertEqual(self.w.key_buttons["KEY_TAB"].name.text(), "Tab")
        self.assertTrue(self.w.dirty)
        self.press("KEY_TAB")  # pressed again: not added twice
        self.assertEqual(len(self.w.cfg["extra_keys"]), 1)

    def test_bind_rename_save_and_remove(self):
        self.w.learn.setChecked(True)
        self.press("KEY_F13")
        from numpadctl import actions
        from numpadctl_ui import widgets
        combo = [c for c in self.w.editor_scroll.widget().findChildren(widgets.SearchCombo)
                 if c.count() == len(ui_common.ACTION_NAMES)][0]
        combo.setCurrentIndex(actions.ACTIONS.index(actions.BY_ID["media_next"]))
        APP.processEvents()
        name = [e for e in self.w.editor_scroll.widget().findChildren(QLineEdit) if e.accessibleName() == "Key name"][0]
        name.textEdited.emit("Next track")
        name.setText("Next track")
        self.assertEqual(self.w.key_buttons["KEY_F13"].name.text(), "Next track")
        self.assertTrue(self.w.save())
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["extra_keys"], [{"id": "KEY_F13", "label": "Next track"}])
        self.assertEqual(saved["profiles"][0]["bindings"]["KEY_F13"]["tap"]["action"], "media_next")
        self.w.remove_extra_key("KEY_F13")
        self.assertNotIn("KEY_F13", self.w.key_buttons)
        self.assertEqual(self.w.selected, "1")

    def test_an_extra_key_can_be_the_layer_key(self):
        self.w.cfg["extra_keys"] = [{"id": "KEY_F13", "label": "Fn"}]
        dialog = dialogs.SettingsDialog(self.w)
        dialog.layer_key.setCurrentIndex(dialog.layer_choices.index("KEY_F13"))
        self.assertEqual(dialog.values()["layer_key"], "KEY_F13")
        self.assertEqual(dialog.layer_key.itemText(dialog.layer_choices.index("KEY_F13")), "Fn")
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
