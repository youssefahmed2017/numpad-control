"""The Qt settings window, run invisibly (offscreen) against a temporary config."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox  # noqa: E402

from numpadctl import config, modes, ui_common  # noqa: E402
from numpadctl_ui import dialogs, picker as picker_module, tools, widgets, window as window_module  # noqa: E402
from numpadctl_ui.picker import ActionPicker  # noqa: E402

APP = QApplication.instance() or QApplication([])


def b(action, **params):
    return {"action": action, "params": params}


CONFIG = {
    "device": {"vendor": "c0f4", "product": "05f5"}, "grab": True, "feedback": True,
    "layer_key": None, "modes": ["Stream mode"], "obs": {"host": "localhost", "port": 4455, "password": ""},
    "profiles": [{"name": "Default", "match": "", "layer_bindings": {}, "bindings": {
        "1": {"tap": b("open_browser", url="")},
        "8": {"tap": b("if_mode", mode="Stream mode", then=[b("media_next")], otherwise=[b("mic_mute")])},
    }}],
}


class FakeLink:
    connected = False

    def __init__(self, on_message, dispatch):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


class QtWindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config_path = root / "config.json"
        self.config_path.write_text(json.dumps(CONFIG))
        patches = [mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", self.config_path),
                   mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "modes.json"),
                   mock.patch.object(picker_module, "RECENT_PATH", root / "recent.json"),
                   mock.patch.object(ui_common, "ServiceLink", FakeLink),
                   mock.patch.object(ui_common, "installed_apps", lambda: [("Kitty", "kitty.desktop"), ("Firefox", "firefox.desktop")])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.w = window_module.MainWindow()
        self.addCleanup(self.w.deleteLater)

    def saved(self):
        return json.loads(self.config_path.read_text())["sets"][0]["profiles"][0]["bindings"]

    def editor(self, kind):
        return self.w.editor_scroll.widget().findChildren(kind)

    def pick(self, slot_index, action_id):
        """Choose an action in the slot's dropdown (0 = Press, 1 = Hold, 2 = Double tap)."""
        from numpadctl import actions
        picker = self.editor(ActionPicker)[slot_index]
        picker.choose(actions.ACTIONS.index(actions.BY_ID[action_id]))
        APP.processEvents()  # the editor is rebuilt right after the signal

    def test_choose_action_edit_and_save(self):
        self.w.select("2")
        self.pick(0, "open_url")
        self.assertTrue(self.w.dirty)
        url = [e for e in self.editor(QLineEdit) if e.accessibleName() == "URL"][0]
        url.setText("https://example.com")
        self.assertEqual(self.w.keymap()["2"]["tap"]["params"]["url"], "https://example.com", "written straight in")
        self.assertTrue(self.w.key_buttons["2"].action.text().startswith("Open a"))
        self.assertTrue(self.w.save())
        self.assertEqual(self.saved()["2"], {"tap": b("open_url", url="https://example.com")})
        self.assertFalse(self.w.dirty)

    def test_if_otherwise_steps_survive_editing_and_save(self):
        """Regression: the GTK window once wiped these lists on Save."""
        self.w.select("8")
        mode = [e for e in self.editor(QLineEdit) if e.accessibleName() == "Mode"][0]
        mode.setText("Stream mode")
        self.assertTrue(self.w.save())
        self.assertEqual(self.saved()["8"]["tap"]["params"]["then"], [b("media_next")])
        self.assertEqual(self.saved()["8"]["tap"]["params"]["otherwise"], [b("mic_mute")])

    def test_macro_steps_add_move_remove(self):
        self.w.select("7")
        self.pick(0, "macro")
        steps_widget = self.editor(widgets.StepList)[0]
        steps_widget.add("wait")
        steps_widget.add("open_browser")
        steps = self.w.keymap()["7"]["tap"]["params"]["steps"]
        self.assertEqual([s["action"] for s in steps], ["wait", "open_browser"])
        steps_widget.move(1, -1)
        self.assertEqual([s["action"] for s in steps], ["open_browser", "wait"])
        steps_widget.change(lambda: steps.pop(0), None)
        self.assertEqual([s["action"] for s in steps], ["wait"])
        self.assertTrue(self.w.save())
        self.assertEqual(self.saved()["7"]["tap"]["params"]["steps"], [b("wait", seconds="1")])

    def test_app_picker_and_rapid_fire(self):
        self.w.select("4")
        self.pick(0, "launch_app")
        self.assertEqual(self.w.keymap()["4"]["tap"]["params"]["app"], "kitty.desktop", "first app chosen")
        self.pick(1, "volume_down")
        from PySide6.QtWidgets import QCheckBox
        rapid = [c for c in self.editor(QCheckBox) if "Rapid" in c.text()][0]
        self.assertTrue(rapid.isChecked(), "on by default for volume")
        rapid.setChecked(False)
        self.assertFalse(self.w.keymap()["4"]["hold"]["rapid"])

    def test_search_finds_actions_by_any_word_of_their_name_group_or_sentence(self):
        from numpadctl import actions
        found = lambda q: [a.id for a in actions.ACTIONS if picker_module.matches(a, q)]
        self.assertEqual(found("shut"), ["shutdown"])
        self.assertIn("mic_mute", found("mute"))
        self.assertIn("obs_toggle_mute", found("mute"))
        self.assertEqual(found("obs live"), ["obs_start_streaming", "obs_toggle_streaming", "obs_start_both"])
        self.assertEqual(found("zzz"), [])

    def test_picker_popup_lists_groups_and_picks_with_enter(self):
        from numpadctl import actions
        picker = self.editor(ActionPicker)[0]
        popup = picker_module._Popup(picker.items, picker.index)
        titles = [popup.list.item(r).text() for r in range(popup.list.count()) if popup.list.item(r).data(picker_module.HEADER_ROLE)]
        self.assertIn("OBS", titles)
        popup.search.setText("volume up")
        got = []
        popup.chosen.connect(got.append)
        popup._clicked(popup.list.currentItem())
        self.assertEqual(actions.ACTIONS[got[0]].id, "volume_up")

    def test_recently_used_actions_come_first(self):
        picker = self.editor(ActionPicker)[0]
        self.pick(0, "media_next")
        popup = picker_module._Popup(picker.items, 0)
        self.assertEqual(popup.list.item(0).text(), "Recently used")
        self.assertEqual(popup.list.item(1).text(), "Next track")

    def test_bad_settings_block_save(self):
        self.w.select("9")
        self.pick(0, "press_keys")
        keys = [e for e in self.editor(QLineEdit) if e.accessibleName().startswith("Keys")][0]
        keys.setText("ctrl+banana")
        with mock.patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self.w.save())
        self.assertIn("unknown key", warning.call_args.args[2])

    def test_duplicate_profile_is_a_separate_copy(self):
        with mock.patch.object(dialogs.ProfileDialog, "ask", return_value=("Streaming", "obs")):
            self.w.profile_dialog(None, copy_from=0)
        profiles = self.w.cfg["profiles"]
        self.assertEqual([p["name"] for p in profiles], ["Default", "Streaming"])
        self.assertEqual(self.w.profile_index, 1, "the window shows the new profile")
        profiles[1]["bindings"]["8"]["tap"]["params"]["then"].clear()
        self.assertEqual(profiles[0]["bindings"]["8"]["tap"]["params"]["then"], [b("media_next")])

    def test_settings_dialog_values_and_modes(self):
        dialog = dialogs.SettingsDialog(self.w)
        dialog.new_mode.setText("  Gaming   time ")
        dialog.add_mode()
        dialog.layer_key.setCurrentIndex(dialog.layer_choices.index("Enter"))
        values = dialog.values()
        self.assertEqual(values["modes"], ["Stream mode", "Gaming time"])
        self.assertEqual(values["layer_key"], "Enter")
        self.assertEqual(values["appearance"], "auto")
        dialog.deleteLater()

    def test_the_numpad_layout_setting_moves_the_key_buttons_but_not_their_names(self):
        grid = self.w.numpad_grid

        def spot(key):
            row, column, _, _ = grid.getItemPosition(grid.indexOf(self.w.key_buttons[key]))
            return row, column
        self.assertEqual([spot(k) for k in ("Backspace", "-", "+")], [(0, 3), (1, 3), (2, 3)])
        dialog = dialogs.SettingsDialog(self.w)
        dialog.numpad_layout.setCurrentIndex(dialog.layout_ids.index("backspace_below"))
        values = dialog.values()
        dialog.deleteLater()
        self.assertEqual(values["numpad_layout"], "backspace_below")
        self.w.cfg.update(values)
        self.w.arrange_keys()
        self.assertEqual([spot(k) for k in ("-", "+", "Backspace")], [(0, 3), (1, 3), (2, 3)])
        self.assertEqual(sorted(self.w.key_buttons), sorted(k for k, *_ in ui_common.LAYOUT))   # same keys, same names
        self.w.select("Backspace")
        self.assertEqual(self.w.selected, "Backspace")

    def test_a_profile_exported_and_imported_is_a_new_profile_with_the_same_keys(self):
        self.w.cfg["obs"]["password"] = "hunter2"
        path = Path(self.tmp.name) / "p.json"
        self.assertTrue(self.w.export_profile_to(str(path)))
        self.assertNotIn("hunter2", path.read_text())   # only the profile goes into the file
        before = len(self.w.cfg["profiles"])
        seen = []
        self.assertTrue(self.w.import_profile_from(str(path), confirm=lambda profile, dropped: seen.append((profile, dropped)) or True))
        self.assertEqual(len(self.w.cfg["profiles"]), before + 1)
        new = self.w.cfg["profiles"][-1]
        self.assertEqual(new["name"], "Default (2)")
        self.assertEqual(new["bindings"], self.w.cfg["profiles"][0]["bindings"])
        self.assertIsNot(new["bindings"], self.w.cfg["profiles"][0]["bindings"])   # a copy, not the same dict
        self.assertEqual(self.w.profile_index, before)
        self.assertEqual(seen[0][1], [])

    def test_a_cancelled_import_changes_nothing(self):
        path = Path(self.tmp.name) / "p.json"
        self.w.export_profile_to(str(path))
        before = copy.deepcopy(self.w.cfg["profiles"])
        self.assertFalse(self.w.import_profile_from(str(path), confirm=lambda profile, dropped: False))
        self.assertEqual(self.w.cfg["profiles"], before)

    def test_a_bad_file_is_refused_with_a_message_and_a_hostile_one_loses_what_it_cannot_use(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_text("not json")
        with mock.patch.object(window_module.QMessageBox, "warning") as warning:
            self.assertFalse(self.w.import_profile_from(str(path), confirm=lambda profile, dropped: True))
        self.assertIn("can't be imported", warning.call_args.args[2])
        hostile = {"format": "numpadcontrol-profile", "version": 1, "profile": {
            "name": "Gift", "match": "", "bindings": {"1": {"tap": {"action": "launch_missiles", "params": {}}},
                                                       "2": {"tap": {"action": "mic_mute", "params": {}}}}}}
        path.write_text(json.dumps(hostile))
        seen = []
        self.w.import_profile_from(str(path), confirm=lambda profile, dropped: seen.append((profile, dropped)) or True)
        imported = self.w.cfg["profiles"][-1]
        self.assertEqual(sorted(imported["bindings"]), ["2"])
        self.assertEqual(len(seen[0][1]), 1)

    def test_close_with_unsaved_changes_can_discard(self):
        self.w.select("2")
        self.pick(0, "media_stop")
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
            self.w.close()
        self.assertFalse(self.w.dirty)
        self.assertNotIn("2", self.w.keymap(), "discarding reloads the saved setup")

    def test_placeholder_is_inserted_at_the_cursor(self):
        self.w.select("3")
        self.pick(0, "type_text")
        field = [f for f in self.editor(widgets.TextField) if f.edit.accessibleName() == "Text to type"][0]
        field.edit.setText("Live since  today")
        field.edit.setCursorPosition(11)
        button = [b for b in field.findChildren(widgets.QToolButton) if b.text() == "{…}"][0]
        [a for a in button.menu().actions() if a.text().startswith("{time}")][0].trigger()
        self.assertEqual(field.edit.text(), "Live since {time} today")
        self.assertEqual(self.w.keymap()["3"]["tap"]["params"]["text"], "Live since {time} today")

    def test_key_tester_lists_raw_events_and_the_000_result(self):
        self.w.link.connected = True
        self.w.open_tester()
        self.assertIn({"cmd": "raw", "on": True}, self.w.link.sent)
        for event in ({"event": "raw", "key": "0", "down": True, "t": 1.000},
                      {"event": "raw", "key": "0", "down": True, "t": 1.004},
                      {"event": "key", "key": "000"}):
            self.w.on_service_message(event)
        text = self.w.tester.text.toPlainText()
        self.assertIn("+     4 ms", text)
        self.assertIn("→ 000", text)
        self.w.tester.accept()
        self.assertIn({"cmd": "raw", "on": False}, self.w.link.sent)
        self.assertIsNone(self.w.tester)

    def test_diagnostics_dialog_shows_a_report_and_copies_it(self):
        from numpadctl import diagnostics
        with mock.patch.object(diagnostics, "collect", return_value="REPORT TEXT"), \
                mock.patch.object(ui_common, "run_in_background", lambda work, done, dispatch: done(work(), None)):
            dialog = tools.DiagnosticsDialog(self.w)
        self.assertEqual(dialog.text.toPlainText(), "REPORT TEXT")
        dialog.copy()
        self.assertEqual(APP.clipboard().text(), "REPORT TEXT")
        dialog.deleteLater()

    def test_starter_preset_fills_only_empty_keys(self):
        from numpadctl import presets
        with mock.patch.object(dialogs.PresetDialog, "ask", return_value=presets.BY_NAME["Media and volume"]):
            self.w.add_preset()
        self.assertIn("kept as they were", self.w.snackbar.text())
        self.assertTrue(self.w.save())
        keymap = self.saved()
        self.assertEqual(keymap["8"]["tap"]["action"], "if_mode", "key 8 already had a setup: kept")
        self.assertEqual(keymap["7"]["tap"]["action"], "media_previous")

    def test_learn_needs_the_service(self):
        self.w.learn.setChecked(True)
        self.assertFalse(self.w.learn.isChecked())
        self.assertIn("needs the background service", self.w.snackbar.text())

    def test_welcome_flow(self):
        from numpadctl_ui import welcome
        dialog = welcome.WelcomeDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        self.assertIs(self.w.tour, dialog)
        self.w.last_status = {"running": True, "connected": True, "devices": ["USB Keyboard"]}
        dialog.refresh_status()
        self.assertIn("USB Keyboard connected", dialog.status.text())
        dialog.advance()
        self.assertEqual(dialog.pages.currentIndex(), 1)
        dialog.advance()  # the default choice, media keys: filled in and saved
        self.assertEqual(self.saved()["5"]["tap"]["action"], "volume_mute")
        self.assertEqual(self.saved()["8"]["tap"]["action"], "if_mode", "what was there stays")
        self.assertIn("Mute", dialog.try_text.text())
        self.w.link.sent.clear()
        dialog.go(2)
        self.assertEqual(self.w.link.sent[-1]["on"], True, "keys are reported, not run, on the last page")
        dialog.on_key("7")
        self.assertIn("Try key 5", dialog.try_result.text())
        dialog.on_key("5")
        self.assertIn("It works", dialog.try_result.text())
        dialog.advance()
        self.assertIsNone(self.w.tour)
        self.assertTrue(json.loads(self.config_path.read_text())["welcomed"])
        self.assertEqual(self.w.link.sent[-1]["on"], False)

    def test_welcome_shows_only_on_a_new_install(self):
        self.assertFalse(self.w.first_run, "there was a config already")
        with mock.patch.object(window_module.welcome.WelcomeDialog, "exec") as run:
            self.w.open_welcome()
        run.assert_called_once()

    def test_the_key_map_overlay_settings_are_in_the_settings_dialog(self):
        dialog = dialogs.SettingsDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.values()["hud"], {"enabled": True, "opacity": 90, "trigger": "combo", "key": "Enter"})
        dialog.hud_enabled.setChecked(False)
        dialog.hud_opacity.setValue(55)
        dialog.hud_trigger.setCurrentIndex(len(dialog.hud_keys))   # the last choice: the old hold-to-show
        self.assertEqual(dialog.values()["hud"], {"enabled": False, "opacity": 55, "trigger": "hold", "key": "Enter"})

    def test_the_overlay_combo_says_what_it_costs(self):
        """Issue #12: Layer + a key opens the key map; the dialog explains when that combo is taken or impossible."""
        dialog = dialogs.SettingsDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        self.assertIn("Choose a layer key", dialog.hud_note.text())
        dialog.layer_key.setCurrentIndex(dialog.layer_choices.index("NumLock"))
        self.assertIn("Press Layer + ⏎ to open the key map", dialog.hud_note.text())
        dialog.hud_trigger.setCurrentIndex(dialog.hud_keys.index("NumLock"))
        self.assertIn("is the layer key itself", dialog.hud_note.text())
        self.w.cfg["profiles"][0]["layer_bindings"]["7"] = b("mic_mute")
        dialog.hud_trigger.setCurrentIndex(dialog.hud_keys.index("7"))
        self.assertIn("won't run", dialog.hud_note.text())
        self.assertEqual(dialog.values()["hud"]["key"], "7")

    def test_the_preview_button_needs_the_service_and_a_layer_key(self):
        dialog = dialogs.SettingsDialog(self.w)
        self.addCleanup(dialog.deleteLater)
        dialog.preview_hud()
        self.assertIn("isn't running", self.w.snackbar.text())
        self.w.link.connected = True
        self.addCleanup(lambda: setattr(self.w.link, "connected", False))
        dialog.preview_hud()
        self.assertIn("layer key", self.w.snackbar.text())
        self.assertEqual(self.w.link.sent, [])
        self.w.cfg["layer_key"] = "."
        dialog.preview_hud()
        self.assertEqual(self.w.link.sent[-1], {"cmd": "hud"})

    def test_turbo_is_a_checkbox_and_a_rate_saved_with_the_press_action(self):
        from PySide6.QtWidgets import QCheckBox
        from numpadctl_ui.buttons import SpinBox
        self.w.select("2")
        self.pick(0, "media_play_pause")
        turbo = [c for c in self.editor(QCheckBox) if c.text().startswith("Turbo")][0]
        rate = [s for s in self.editor(SpinBox) if s.accessibleName() == "Turbo rate"][0]
        self.assertFalse(turbo.isChecked())
        self.assertFalse(rate.isEnabled(), "the rate is only for when turbo is on")
        turbo.setChecked(True)
        rate.setValue(30)
        self.assertTrue(self.w.save())
        self.assertEqual(self.saved()["2"]["tap"]["turbo"], 30)
        turbo.setChecked(False)
        self.assertEqual(self.w.keymap()["2"]["tap"]["turbo"], 0)

    def test_turbo_is_not_offered_when_the_key_has_a_hold_action(self):
        from PySide6.QtWidgets import QCheckBox
        self.w.select("2")
        self.pick(0, "media_play_pause")
        self.pick(1, "mic_mute")  # the Hold slot
        turbo = [c for c in self.editor(QCheckBox) if c.text().startswith("Turbo")][0]
        self.assertFalse(turbo.isEnabled())

    def test_turbo_is_not_offered_for_actions_that_need_confirming(self):
        from PySide6.QtWidgets import QCheckBox
        self.w.select("2")
        self.pick(0, "shutdown")
        self.assertEqual([c for c in self.editor(QCheckBox) if c.text().startswith("Turbo")], [])

    def test_privacy_panic_settings_are_checkboxes(self):
        from PySide6.QtWidgets import QCheckBox
        self.w.select("2")
        self.pick(0, "privacy_panic")
        boxes = [c for c in self.editor(QCheckBox) if not c.text().startswith("Turbo")]  # (Turbo is on every Press action)
        self.assertEqual(len(boxes), 5)
        self.assertEqual([b.isChecked() for b in boxes], [True, True, True, True, False])
        boxes[0].setChecked(False)  # "Mute the microphone"
        self.assertTrue(self.w.dirty)
        self.assertIs(self.w.keymap()["2"]["tap"]["params"]["mic"], False)
        self.assertTrue(self.w.save())
        self.assertIs(self.saved()["2"]["tap"]["params"]["mic"], False)


if __name__ == "__main__":
    unittest.main()
