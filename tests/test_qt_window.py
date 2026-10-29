"""The Qt settings window, run invisibly (offscreen) against a temporary config."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
        return json.loads(self.config_path.read_text())["profiles"][0]["bindings"]

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
        self.assertIn("kept as they were", self.w.statusBar().currentMessage())
        self.assertTrue(self.w.save())
        keymap = self.saved()
        self.assertEqual(keymap["8"]["tap"]["action"], "if_mode", "key 8 already had a setup: kept")
        self.assertEqual(keymap["7"]["tap"]["action"], "media_previous")

    def test_learn_needs_the_service(self):
        self.w.learn.setChecked(True)
        self.assertFalse(self.w.learn.isChecked())
        self.assertIn("needs the background service", self.w.statusBar().currentMessage())

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

    def test_easter_egg_needs_the_whole_sequence(self):
        from numpadctl_ui import egg
        matcher = egg.Matcher()
        self.assertFalse(any(matcher.press(k) for k in egg.SEQUENCE[:-1]))
        self.assertTrue(matcher.press(egg.SEQUENCE[-1]))
        self.assertFalse(any(matcher.press(k) for k in egg.SEQUENCE[:-1]), "starts over after it fires")
        matcher.press("5")  # a stray key breaks it
        self.assertFalse(matcher.press(egg.SEQUENCE[-1]))

    def test_easter_egg_plays_from_the_window(self):
        from numpadctl_ui import egg
        self.w.resize(800, 600)
        for key in egg.SEQUENCE:
            self.w.on_service_message({"event": "key", "key": key})
        layers = self.w.centralWidget().findChildren(egg.Confetti)
        self.assertEqual(len(layers), 1)
        layers[0].repaint()  # draws a frame without errors


if __name__ == "__main__":
    unittest.main()
