"""The Qt settings window, run invisibly (offscreen) against a temporary config."""

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

    def test_secret_combo_needs_pad_then_keyboard_in_order_at_any_speed(self):
        from numpadctl_ui import egg
        combo = egg.Combo()
        steps = list(egg.COMBO)
        self.assertFalse(any(combo.press(*step) for step in steps[:-1]))
        self.assertTrue(combo.press(*steps[-1]))
        self.assertFalse(any(combo.press(*step) for step in steps[:4]))
        self.assertFalse(combo.press("key", "x"), "a wrong step starts over")
        self.assertFalse(any(combo.press(*step) for step in steps[4:]))
        self.assertFalse(combo.press("pad", "m"), "the numpad's m is not the keyboard's m")
        self.assertTrue(any([combo.press(*step) for step in steps]), "and it can be started again")

    def test_secret_panel_has_25_options_and_out_puts_everything_back(self):
        from PySide6.QtWidgets import QPushButton, QTabWidget
        from numpadctl_ui import secret, theme
        self.w.cfg["appearance"] = "light"
        theme.apply(APP, "light", "Orchid", "standard")
        accent_before = dict(theme.current)
        with mock.patch.object(secret, "LEAVE_MS", 30):
            panel = secret.SecretPanel(self.w)
            self.addCleanup(lambda: shiboken6.isValid(panel) and panel.deleteLater())
            self.assertIs(self.w.secret, panel)
            self.assertEqual(self.w.link.sent[-1]["on"], True, "keys are reported, not run, while it is open")
            tabs = panel.findChild(QTabWidget)
            self.assertEqual(tabs.count(), 6, "five tabs and the locked one")
            for index in range(5):
                self.assertEqual(len(tabs.widget(index).findChildren(QPushButton)), 5)
            buttons = {b.text().split("   -")[0]: b for b in panel.findChildren(QPushButton)}
            buttons["Disco"].setChecked(True)
            buttons["Matrix rain"].setChecked(True)
            buttons["Key rain"].setChecked(True)
            panel.on_pad_key("5")  # throws a burst of confetti
            self.assertTrue(panel.overlays)
            panel.reject()  # Esc alone doesn't leave
            self.assertIs(self.w.secret, panel)
            self.w.show()
            self.w.activateWindow()
            APP.processEvents()
            from PySide6.QtCore import QEvent, Qt
            from PySide6.QtGui import QKeyEvent
            for number, (key, scan) in enumerate(((Qt.Key_O, 32), (Qt.Key_U, 30), (Qt.Key_T, 28))):  # typing "out" in the main window
                event = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, scan, 0, 0, chr(key).lower())
                self.w.eventFilter(self.w, event)
            self.assertTrue(panel.leaving)
            from PySide6.QtTest import QTest
            QTest.qWait(300)
        self.assertIsNone(self.w.secret)
        self.assertFalse(panel.overlays)
        self.assertEqual(self.w.link.sent[-1]["on"], False)
        self.assertEqual(theme.current.get("primary"), accent_before.get("primary"), "the look is restored")

    def test_the_console_is_never_a_trap(self):
        from numpadctl_ui import secret
        with mock.patch.object(secret, "LEAVE_MS", 30):
            panel = secret.SecretPanel(self.w)
            self.addCleanup(lambda: shiboken6.isValid(panel) and panel.deleteLater())
            self.assertFalse(panel.isModal(), "other windows can sit above it")
            panel.reject()
            panel.reject()
            self.assertFalse(panel.leaving)
            panel.reject()  # the third Esc or close leaves anyway
            self.assertTrue(panel.leaving)
            from PySide6.QtTest import QTest
            QTest.qWait(300)
        self.assertIsNone(self.w.secret)

    def test_leaving_works_after_the_blue_screen_removed_itself(self):
        """Issue #10: the cleanup hit the already deleted blue screen, raised, and the console never closed."""
        from PySide6.QtTest import QTest
        from numpadctl_ui import secret
        with mock.patch.object(secret, "LEAVE_MS", 30):
            panel = secret.SecretPanel(self.w)
            self.addCleanup(lambda: shiboken6.isValid(panel) and panel.deleteLater())
            panel.crash()
            blue = panel.overlays[0]
            blue.mousePressEvent(None)  # click: it deletes itself
            QTest.qWait(50)
            panel.overlays.append(blue)  # even if it was still on the list
            panel.leave()
            QTest.qWait(300)
        self.assertIsNone(self.w.secret)

    def make_panel(self):
        from numpadctl_ui import secret
        panel = secret.SecretPanel(self.w)
        self.addCleanup(lambda: shiboken6.isValid(panel) and panel.deleteLater())
        return panel

    def test_superroot_password_is_the_seven_fragments_in_order(self):
        import hashlib
        from numpadctl_ui import secret
        password = "".join(secret.FRAGMENTS)
        self.assertEqual(password, "123AdminSuperSoda@444cannotsee")
        self.assertEqual(hashlib.sha256(secret.SALT + password.encode()).hexdigest(), secret.PASSWORD_HASH)
        with open(secret.__file__) as source:
            code = source.read()
        for piece in ("Admin", "Super", "Soda", "cannotsee"):
            self.assertNotIn(piece, code.replace("Super" + "Root", "").replace("SUPER", ""), "the pieces are not written out in the code")
        self.assertNotIn(password, code)

    def test_superroot_wrong_passwords_escalate_then_kick_you_out(self):
        from PySide6.QtTest import QTest
        from numpadctl_ui import secret
        with mock.patch.object(secret, "KICK_MS", 30):
            panel = self.make_panel()
            panel.tabs_widget.setCurrentIndex(panel.lock_index)
            self.assertFalse(panel.unlocked)
            for number in range(1, 4):
                panel.password.setText("nope")
                panel.check_password()
                self.assertTrue(panel.lock_status.text().startswith("ACCESS DENIED"))
                self.assertFalse(panel.leaving, f"wrong guess {number} only warns")
            panel.password.setText("nope")
            panel.check_password()  # the fourth wrong one
            self.assertTrue(panel.leaving)
            self.assertIn("Enough Evidence", panel.kick_label.text())
            self.assertIn("GET OUT", panel.kick_label.text())
            QTest.qWait(300)
        self.assertIsNone(self.w.secret)

    def test_superroot_right_password_opens_the_tab_with_five_options(self):
        from PySide6.QtWidgets import QPushButton
        from numpadctl_ui import secret
        panel = self.make_panel()
        panel.password.setText("123AdminSuperSoda@444cannotsee")
        panel.check_password()
        self.assertTrue(panel.unlocked)
        self.assertEqual(panel.lock_stack.currentIndex(), 1)
        self.assertEqual(len(panel.lock_stack.widget(1).findChildren(QPushButton)), 5)
        self.assertIn("🔓", panel.tabs_widget.tabText(panel.lock_index))
        self.assertEqual(panel.wrong, 0)

    def test_the_fragments_turn_up_and_are_listed_on_the_lock_page(self):
        from numpadctl_ui import secret
        panel = self.make_panel()
        self.assertNotIn("Admin", panel.fragment_label.text())
        panel.found(2)
        panel.say_line("FRAGMENT:1")
        self.assertIn("Admin", panel.fragment_label.text())
        self.assertIn("123", panel.fragment_label.text())
        self.assertNotIn("Soda", panel.fragment_label.text())
        self.assertIn("(shell)", panel.fragment_label.text(), "number 4 says where it is")
        for number in (1, 2, 3, 5, 6, 7):
            panel.found(number)
        self.assertIn("ask soda", panel.log.toPlainText())
        self.assertIn("cannotsee", panel.fragment_label.text())
        panel.fortune_index = 0  # the fortunes come round in order; none hands out fragment 4, one points at the shell
        panel.fragments.clear()
        for _ in range(len(secret.FORTUNES)):
            panel.fortune()
        self.assertNotIn(secret.OUTSIDE, panel.fragments)
        self.assertIn("soda --help", panel.log.toPlainText())

    def test_secret_words_work_except_in_the_password_box(self):
        panel = self.make_panel()
        for letter in "sudo":
            panel.on_letter(letter)
        self.assertIn("sudoers", panel.log.toPlainText())
        panel.password.setFocus()
        panel.show()
        APP.processEvents()
        if panel.password.hasFocus():  # (a window can refuse focus when run invisibly)
            for letter in "out":
                panel.on_letter(letter)
            self.assertFalse(panel.leaving, "typing a password containing a word does not run the word")
        for letter in "hint":
            panel.on_letter(letter)
        self.assertIn("hint 1/5", panel.log.toPlainText())

    def test_the_console_effects_only_use_the_numpads_own_keys(self):
        from PySide6.QtWidgets import QPushButton
        self.w.key_buttons["hp:KEY_A"] = QPushButton()  # a key of a keyboard picture
        panel = self.make_panel()
        self.assertNotIn("hp:KEY_A", panel.pad_keys())
        self.assertIn("5", panel.pad_keys())

    def test_gravity_brings_the_keys_back(self):
        self.w.resize(1000, 700)
        self.w.show()
        APP.processEvents()
        panel = self.make_panel()
        panel.gravity()
        self.assertIsNotNone(panel.job)
        panel.stop_gravity()
        self.assertTrue(all(b.isVisible() for b in self.w.key_buttons.values()))

    def test_secret_wipe_backs_up_and_can_be_discarded(self):
        from numpadctl_ui import secret
        panel = secret.SecretPanel(self.w)
        self.addCleanup(lambda: shiboken6.isValid(panel) and panel.deleteLater())
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            panel.wipe()
        self.assertTrue((self.config_path.parent / "config.before-panic.json").exists())
        self.assertEqual(self.w.keymap(), {})
        self.assertTrue(self.w.dirty)
        self.assertEqual(json.loads(self.config_path.read_text())["profiles"][0]["bindings"]["1"]["tap"]["action"],
                         "open_browser", "nothing was written over the saved keys")
        self.w.discard_changes()
        self.assertIn("1", self.w.keymap())

    def test_secret_letters_work_on_any_keyboard_layout(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from numpadctl_ui import egg

        def press(key, scan, text):
            return QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, scan, 0, 0, text)
        self.assertEqual(egg.letter_of(press(Qt.Key_U, 30, "u"), "linux"), "u")
        # an Arabic layout: the key's letter is not latin, its place on the keyboard is (U = evdev 22, +8 on Linux)
        self.assertEqual(egg.letter_of(press(0x0647, 30, "ه"), "linux"), "u")
        self.assertEqual(egg.letter_of(press(0x0647, 22, "ه"), "win32"), "u")
        self.assertEqual(egg.letter_of(press(Qt.Key_Space, 65, " "), "linux"), "")

    def test_a_key_press_seen_several_times_counts_once(self):
        """Qt filters one key press for the window and again for each widget it passes through."""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from numpadctl_ui import egg
        self.w.show()
        self.w.activateWindow()
        APP.processEvents()
        for source, key in egg.COMBO[:3]:
            self.w.combo.press(source, key)
        with mock.patch.object(window_module.MainWindow, "open_secret") as opened:
            for letter, scan in (("u", 30), ("l", 46), ("c", 54), ("s", 39), ("m", 58)):
                event = QKeyEvent(QEvent.KeyPress, ord(letter.upper()), Qt.NoModifier, scan, 0, 0, letter)
                for receiver in (self.w.windowHandle(), self.w, self.w.centralWidget()):  # the same press, three times
                    self.w.eventFilter(receiver, event)
            APP.processEvents()
        opened.assert_called_once()


if __name__ == "__main__":
    unittest.main()
