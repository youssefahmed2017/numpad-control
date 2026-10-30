"""Extra keyboards in the window: the device list, the keyboard picture, adding, removing, Learn and the grab switch."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from numpadctl import config, devices, keys, modes, ui_common  # noqa: E402
from numpadctl_ui import dialogs, picker as picker_module, window as window_module  # noqa: E402

APP = QApplication.instance() or QApplication([])

HP = {"id": "hp", "vendor": "03f0", "product": "344a", "name": "HP keyboard", "grab": True}
FOUND = [{"vendor": "03f0", "product": "344a", "name": "HP USB Slim Keyboard", "nodes": [], "readable": True},
         {"vendor": "258a", "product": "002a", "name": "SINO WEALTH Gaming Keyboard", "nodes": [], "readable": False}]


class FakeLink:
    connected = True

    def __init__(self, on_message, dispatch):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


class DeviceWindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.path = root / "config.json"
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        cfg["devices"] = [dict(HP)]
        cfg["profiles"][0]["bindings"]["hp:KEY_F1"] = {"tap": {"action": "volume_mute", "params": {}}}
        self.path.write_text(json.dumps(cfg))
        for p in (mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", self.path),
                  mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "m.json"),
                  mock.patch.object(picker_module, "RECENT_PATH", root / "recent.json"),
                  mock.patch.object(ui_common, "ServiceLink", FakeLink),
                  mock.patch.object(ui_common, "installed_apps", lambda: [])):
            p.start()
            self.addCleanup(p.stop)
        self.w = window_module.MainWindow()
        self.addCleanup(self.w.deleteLater)

    def press(self, key):
        self.w.on_service_message({"event": "key", "key": key, "label": keys.label_for(key), "unknown": False})

    def test_the_device_list_has_the_numpad_and_the_keyboard(self):
        self.assertEqual([self.w.device_combo.itemText(i) for i in range(self.w.device_combo.count())],
                         ["Numpad", "HP keyboard"])
        self.assertEqual(self.w.device, "")

    def test_choosing_the_keyboard_shows_its_picture(self):
        self.w.device_combo.setCurrentIndex(1)
        self.assertEqual(self.w.device, "hp")
        self.assertEqual(self.w.pad_stack.currentIndex(), 1)
        self.assertIn("hp:KEY_F1", self.w.key_buttons)
        self.assertIn("hp:KEY_KP5", self.w.key_buttons)
        self.assertEqual(self.w.selected, "hp:KEY_ESC")
        self.assertTrue(self.w.key_buttons["hp:KEY_F1"].compact)

    def test_going_back_to_the_numpad_drops_the_keyboard_keys(self):
        self.w.device_combo.setCurrentIndex(1)
        self.w.device_combo.setCurrentIndex(0)
        self.assertFalse([k for k in self.w.key_buttons if keys.split(k)[0]])
        self.assertEqual(self.w.selected, "1")
        self.assertIn("5", self.w.key_buttons)

    def test_a_bound_key_is_marked_and_its_action_is_in_the_tooltip(self):
        self.w.set_device("hp")
        f1, f2 = self.w.key_buttons["hp:KEY_F1"], self.w.key_buttons["hp:KEY_F2"]
        self.assertTrue(f1.property("bound"))
        self.assertFalse(f2.property("bound"))
        self.assertIn("Mute", f1.toolTip())

    def test_the_editor_names_the_keyboard(self):
        self.w.set_device("hp")
        self.w.select("hp:KEY_F1")
        titles = [lab.text() for lab in self.w.editor_scroll.widget().findChildren(type(self.w.dirty_label))]
        self.assertIn("Key  F1 on HP keyboard", titles)

    def test_binding_a_key_of_the_keyboard_saves_under_its_prefixed_id(self):
        self.w.set_device("hp")
        self.w.select("hp:KEY_F2")
        self.w.keymap().setdefault("hp:KEY_F2", {})["tap"] = {"action": "volume_mute", "params": {}}
        self.assertTrue(self.w.save())
        saved = json.loads(self.path.read_text())
        self.assertIn("hp:KEY_F2", saved["profiles"][0]["bindings"])

    def test_the_grab_switch_changes_the_config(self):
        self.w.set_device("hp")
        self.assertTrue(self.w.grab_action.isChecked())
        self.w.grab_action.setChecked(False)
        self.assertFalse(self.w.cfg["devices"][0]["grab"])
        self.assertTrue(self.w.dirty)

    def test_the_switch_and_remove_are_off_for_the_numpad(self):
        self.assertFalse(self.w.grab_action.isEnabled())
        self.assertFalse(self.w.remove_device_action.isEnabled())

    def test_removing_the_keyboard_also_removes_its_bindings(self):
        self.w.set_device("hp")
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.w.remove_device()
        self.assertEqual(self.w.cfg["devices"], [])
        self.assertNotIn("hp:KEY_F1", self.w.cfg["profiles"][0]["bindings"])
        self.assertIn("1", self.w.cfg["profiles"][0]["bindings"], "the numpad's keys stay")
        self.assertEqual(self.w.device, "")

    def test_a_key_pressed_on_the_keyboard_shows_it_while_following(self):
        self.w.learn.setChecked(True)
        self.press("hp:KEY_A")
        self.assertEqual(self.w.device, "hp")
        self.assertEqual(self.w.selected, "hp:KEY_A")

    def test_learn_adds_a_key_the_picture_does_not_have(self):
        self.w.set_device("hp")
        self.w.learn.setChecked(True)
        self.press("hp:KEY_MUTE")
        self.assertIn("hp:KEY_MUTE", self.w.key_buttons)
        self.assertEqual(self.w.cfg["devices"][0]["extra_keys"], [{"id": "hp:KEY_MUTE", "label": "Mute"}])
        self.assertEqual(self.w.selected, "hp:KEY_MUTE")
        self.w.remove_extra_key("hp:KEY_MUTE")
        self.assertNotIn("hp:KEY_MUTE", self.w.key_buttons)
        self.assertEqual(self.w.cfg["devices"][0]["extra_keys"], [])

    def test_keys_of_the_picture_are_not_added_again_by_learn(self):
        self.w.set_device("hp")
        self.w.learn.setChecked(True)
        self.press("hp:KEY_A")
        self.assertEqual(keys.device_extras(self.w.cfg, "hp"), [])

    def test_status_says_when_the_keyboard_is_given_back(self):
        self.w.on_service_message({"event": "status", "running": True, "connected": True, "devices": ["n"],
                                   "extra": {"hp": {"connected": False, "released": True}}})
        self.assertEqual(self.w.device_combo.itemText(1), "HP keyboard (given back)")

    def test_the_window_says_so_once_when_a_keyboard_is_given_back(self):
        status = {"event": "status", "running": True, "connected": True, "devices": ["n"],
                  "extra": {"hp": {"connected": False, "released": True}}}
        self.w.on_service_message({**status, "extra": {"hp": {"connected": True, "released": False}}})
        self.assertNotIn("typing again", self.w.statusBar().currentMessage())
        self.w.on_service_message(status)
        self.assertIn("HP keyboard is typing again", self.w.statusBar().currentMessage())
        self.w.statusBar().clearMessage()
        self.w.on_service_message(status)  # the same news again: not repeated
        self.assertEqual(self.w.statusBar().currentMessage(), "")

    def test_the_picture_has_every_key_once(self):
        names = [n for n, *_ in ui_common.KEYBOARD_LAYOUT]
        self.assertEqual(len(names), len(set(names)))


class AddDeviceDialogTest(unittest.TestCase):
    def make(self, found=FOUND):
        with mock.patch.object(devices, "keyboards", lambda skip=(): found):
            self.parent = QWidget()  # the dialog only needs its parent to have a .dispatch
            self.parent.dispatch = None
            return dialogs.AddDeviceDialog(self.parent, set(), {"hp"})

    def test_lists_the_keyboards_and_marks_the_ones_that_need_access(self):
        d = self.make()
        self.assertEqual(d.list.count(), 2)
        self.assertEqual(d.list.item(1).text(), "SINO WEALTH Gaming Keyboard  (needs access)")

    def test_a_readable_keyboard_can_be_added_with_a_fresh_id(self):
        d = self.make()
        d.list.setCurrentRow(0)
        self.assertTrue(d.ok.isEnabled())
        self.assertTrue(d.access.isHidden())
        self.assertEqual(d.values(), {"id": "hp2", "vendor": "03f0", "product": "344a",
                                      "name": "HP USB Slim Keyboard", "grab": True})

    def test_one_that_needs_access_cannot_be_added_yet(self):
        d = self.make()
        d.list.setCurrentRow(1)
        self.assertFalse(d.ok.isEnabled())
        self.assertFalse(d.access.isHidden())

    def test_nothing_plugged_in(self):
        d = self.make([])
        self.assertFalse(d.ok.isEnabled())


class DevicesModuleTest(unittest.TestCase):
    def test_make_id(self):
        self.assertEqual(devices.make_id("HP USB Slim Keyboard", set()), "hp")
        self.assertEqual(devices.make_id("HP USB Slim Keyboard", {"hp", "hp2"}), "hp3")
        self.assertEqual(devices.make_id("???", set()), "kbd")

    def test_has_key(self):
        self.assertTrue(devices._has_key("0 0 0 40000000", 30))
        self.assertFalse(devices._has_key("0 0 0 0", 30))
        self.assertFalse(devices._has_key("", 30))

    def test_ids_are_checked_before_they_reach_a_shell(self):
        with self.assertRaises(ValueError):
            devices.manual_command("03f0'; rm -rf ~; '", "344a")
        with self.assertRaises(ValueError):
            devices.install_rule("zzzz", "344a")

    def test_the_manual_command_uses_sudo_for_every_step(self):
        command = devices.manual_command("03f0", "344a")
        self.assertIn("sudo tee /etc/udev/rules.d/70-numpad-control-03f0-344a.rules", command)
        self.assertEqual(command.count("sudo"), 3)


if __name__ == "__main__":
    unittest.main()
