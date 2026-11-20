"""With the settings window in front a numpad key selects its key there; pressing the same key again quickly runs it
(so a demo from that window works). Learn mode never runs keys, paused never runs keys, and the top bar says what is going on."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import daemon  # noqa: E402


class SelectThenRunTest(unittest.TestCase):
    def daemon(self, following=True, paused=False):
        d = daemon.Daemon.__new__(daemon.Daemon)
        window = object()
        d.cfg, d.unknown_logged, d.detect_future, d.paused = {}, set(), None, paused
        d.selected_key, d.selected_at, d.pass_through = None, 0.0, set()
        d.capturing, d.following = {window}, ({window} if following else set())
        d.broadcast = lambda message: None
        d.hud_combo = lambda key: False
        d.press, d.release = mock.Mock(), mock.Mock()
        return d

    def keys(self, d, *events, start=100.0):
        """events: (seconds after start, key, down)"""
        with mock.patch.object(daemon.keys, "known", return_value=True):
            for at, key, down in events:
                with mock.patch.object(daemon.time, "monotonic", return_value=start + at):
                    d.key_event(key, down)

    def test_the_first_press_only_selects_and_says_so_in_the_log(self):
        d = self.daemon()
        with self.assertLogs("numpadctl", "INFO") as seen:
            self.keys(d, (0.0, "1", True), (0.1, "1", False))
        d.press.assert_not_called()
        d.release.assert_not_called()
        self.assertEqual(len(seen.output), 1, "the release is not logged")
        self.assertIn("key 1: selected in the settings window, not run: press it again within 1.5 s", seen.output[0])

    def test_a_quick_second_press_runs_it_and_its_release_goes_through(self):
        d = self.daemon()
        self.keys(d, (0.0, "1", True), (0.1, "1", False), (0.6, "1", True), (0.7, "1", False))
        d.press.assert_called_once_with("1")
        d.release.assert_called_once_with("1")
        self.assertEqual(d.pass_through, set())

    def test_a_slow_second_press_only_selects_again(self):
        d = self.daemon()
        self.keys(d, (0.0, "1", True), (0.1, "1", False), (2.0, "1", True), (2.1, "1", False))
        d.press.assert_not_called()
        d.release.assert_not_called()

    def test_another_key_in_between_starts_over(self):
        d = self.daemon()
        self.keys(d, (0.0, "1", True), (0.1, "1", False), (0.3, "2", True), (0.4, "2", False), (0.6, "1", True), (0.7, "1", False))
        d.press.assert_not_called()

    def test_after_a_run_the_next_press_selects_again(self):
        d = self.daemon()
        self.keys(d, (0.0, "1", True), (0.1, "1", False), (0.4, "1", True), (0.5, "1", False), (0.8, "1", True), (0.9, "1", False))
        self.assertEqual(d.press.call_count, 1, "three presses in a row: select, run, select")

    def test_learn_mode_never_runs_keys_however_often_they_are_pressed(self):
        d = self.daemon(following=False)
        with self.assertLogs("numpadctl", "INFO") as seen:
            self.keys(d, (0.0, "1", True), (0.1, "1", False), (0.4, "1", True), (0.5, "1", False))
        d.press.assert_not_called()
        self.assertIn("Learn mode is on", seen.output[0])

    def test_paused_never_runs_keys_and_says_so(self):
        d = self.daemon(following=False, paused=True)
        d.capturing = set()
        with self.assertLogs("numpadctl", "INFO") as seen:
            self.keys(d, (0.0, "1", True), (0.4, "1", True))
        d.press.assert_not_called()
        self.assertIn("NumpadControl is paused", seen.output[0])

    def test_with_no_window_in_front_a_press_runs_at_once(self):
        d = self.daemon()
        d.capturing, d.following = set(), set()
        self.keys(d, (0.0, "1", True), (0.1, "1", False))
        d.press.assert_called_once_with("1")
        d.release.assert_called_once_with("1")


class TopBarHintTest(unittest.TestCase):
    def window(self):
        from tests.test_qt_window import QtWindowTest
        case = QtWindowTest("test_choose_action_edit_and_save")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        case.w.resize(1180, 700)
        return case.w

    def test_the_hint_shows_only_while_keys_select_here(self):
        w = self.window()
        with mock.patch.object(w, "following_keys", return_value=True):
            w.refresh_keys_chip()
            self.assertTrue(w.keys_chip.isVisibleTo(w))
            w.learn.blockSignals(True)          # (without the service connection that Learn mode needs to switch on)
            w.learn.setChecked(True)            # Learn mode has its own switch and says so itself
            w.learn.blockSignals(False)
            w.refresh_keys_chip()
            self.assertFalse(w.keys_chip.isVisibleTo(w))
        w.learn.blockSignals(True)
        w.learn.setChecked(False)
        w.learn.blockSignals(False)
        with mock.patch.object(w, "following_keys", return_value=False):
            w.refresh_keys_chip()
            self.assertFalse(w.keys_chip.isVisibleTo(w))

    def test_clicking_it_makes_keys_run_at_once(self):
        w = self.window()
        w.follow.setChecked(True)
        w.keys_chip.click()
        self.assertFalse(w.follow.isChecked())
        self.assertIn("run at once", w.snackbar.text())


if __name__ == "__main__":
    unittest.main()
