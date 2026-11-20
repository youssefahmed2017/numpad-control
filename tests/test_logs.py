"""The log: its file and levels (logs.py), the first clue for an error (hints.py), the daemon's result lines and its
detector for a numpad that keeps dropping off USB, Diagnostics reading the file, and Tools > Copy the log."""

import errno
import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import daemon, diagnostics, hints, logs  # noqa: E402


class FileAndLevelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(logs, "log_path", lambda: Path(self.tmp.name) / "numpad-control.log")
        patch.start()
        self.addCleanup(patch.stop)
        root, ours = logging.getLogger(), logging.getLogger("numpadctl")
        before = (root.level, ours.level, list(root.handlers))
        self.addCleanup(self.restore, root, ours, before)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NUMPADCTL_LOG", None)

    @staticmethod
    def restore(root, ours, before):
        for handler in list(root.handlers):
            if getattr(handler, "_numpadctl", False):
                root.removeHandler(handler)
                handler.close()
        root.setLevel(before[0])
        ours.setLevel(before[1])

    def lines(self):
        return logs.log_path().read_text().splitlines()

    def test_the_level_comes_from_the_environment_then_the_config_then_info(self):
        self.assertEqual(logs.level_name({}), "info")
        self.assertEqual(logs.level_name({"log_level": "DEBUG"}), "debug")
        self.assertEqual(logs.level_name({"log_level": "loud"}), "info", "a typo must not stop the logging")
        os.environ["NUMPADCTL_LOG"] = "warning"
        self.assertEqual(logs.level_name({"log_level": "debug"}), "warning", "the environment wins")

    def test_lines_go_to_the_file_with_the_level_in_them(self):
        logs.setup(console=False, cfg={})
        logging.getLogger("numpadctl").info("hello")
        logging.getLogger("numpadctl").warning("careful")
        text = "\n".join(self.lines())
        self.assertRegex(text, r"\d{4}-\d\d-\d\d .* INFO +hello")
        self.assertRegex(text, r"WARNING +careful")

    def test_debug_lines_only_appear_when_asked_for(self):
        logs.setup(console=False, cfg={})
        logging.getLogger("numpadctl").debug("raw: key 7 down")
        self.assertNotIn("raw: key 7 down", "\n".join(self.lines()))
        logs.setup(console=False, cfg={"log_level": "debug"})
        logging.getLogger("numpadctl").debug("raw: key 7 down")
        self.assertIn("raw: key 7 down", "\n".join(self.lines()))

    def test_setting_it_up_twice_adds_no_second_handler(self):
        logs.setup(console=False, cfg={})
        logs.setup(console=False, cfg={})
        self.assertEqual(sum(getattr(h, "_numpadctl", False) for h in logging.getLogger().handlers), 1)

    def test_tail_gives_the_last_lines_and_nothing_when_there_is_no_file(self):
        self.assertEqual(logs.tail(5), [])
        logs.log_path().write_text("\n".join(f"line {i}" for i in range(10)) + "\n")
        self.assertEqual(logs.tail(3), ["line 7", "line 8", "line 9"])

    def test_diagnostics_reads_the_file_first(self):
        logs.log_path().write_text("one\ntwo\n")
        self.assertEqual(diagnostics.log_tail(), ["one", "two"])


class HintsTest(unittest.TestCase):
    def test_the_usual_failures_get_a_clue(self):
        self.assertIn("did not answer in time", hints.first_clue(subprocess.TimeoutExpired("x", 5)))
        self.assertIn("did not answer in time", hints.first_clue(RuntimeError("the command timed out after 30 s")))
        self.assertIn("udev rule", hints.first_clue(PermissionError(errno.EACCES, "Permission denied")))
        self.assertIn("not found", hints.first_clue(FileNotFoundError(2, "No such file or directory")))
        self.assertIn("nothing is listening", hints.first_clue(ConnectionRefusedError()))

    def test_an_error_with_nothing_useful_to_add_gets_none(self):
        self.assertIsNone(hints.first_clue(ValueError("no URL set")))


class DaemonLogTest(unittest.TestCase):
    def setUp(self):
        # the USB-drop warning is Linux-only, so these tests must behave the same on the Windows runner
        patch = mock.patch.object(daemon, "IS_WINDOWS", False)
        patch.start()
        self.addCleanup(patch.stop)

    def bare(self):
        d = daemon.Daemon.__new__(daemon.Daemon)
        d.cfg, d.drops, d.flap_warned, d.unknown_logged = {}, [], None, set()
        return d

    def test_a_press_logs_its_result_and_how_long_it_took(self):
        with mock.patch.object(daemon.actions, "run", return_value=None), self.assertLogs("numpadctl", "INFO") as seen:
            self.bare()._run("1", {"action": "mic_mute"}, "tap")
        self.assertRegex(seen.output[0], r"key 1 tap: mic_mute -> ok \(\d+ ms\)")

    def test_a_failure_logs_the_error_and_a_clue_and_tells_the_user(self):
        with mock.patch.object(daemon.actions, "run", side_effect=PermissionError(errno.EACCES, "Permission denied")), \
                mock.patch.object(daemon.actions, "notify") as notify, self.assertLogs("numpadctl", "WARNING") as seen:
            self.bare()._run("2", {"action": "open_url"}, "hold")
        self.assertRegex(seen.output[0], r"key 2 hold: open_url -> FAILED \(\d+ ms\): .*Permission denied")
        self.assertIn("clue: permission denied", seen.output[0])
        notify.assert_called_once()

    def test_a_failure_with_no_clue_has_no_clue_line(self):
        with mock.patch.object(daemon.actions, "run", side_effect=ValueError("no URL set")), \
                mock.patch.object(daemon.actions, "notify"), self.assertLogs("numpadctl", "WARNING") as seen:
            self.bare()._run("2", {"action": "open_url"}, "tap")
        self.assertNotIn("clue:", seen.output[0])

    def test_a_numpad_that_keeps_vanishing_is_explained_once_per_window(self):
        d, gone = self.bare(), OSError(errno.ENODEV, "No such device")
        with self.assertNoLogs("numpadctl", "WARNING"):
            d.note_drop(gone, now=100.0)
            d.note_drop(gone, now=200.0)
        with self.assertLogs("numpadctl", "WARNING") as seen:
            d.note_drop(gone, now=300.0)
        self.assertIn("dropped off USB 3 times in 10 minutes", seen.output[0])
        self.assertIn("back of the computer", seen.output[0])
        with self.assertNoLogs("numpadctl", "WARNING"):
            d.note_drop(gone, now=400.0)          # already said: not again inside the window
        with self.assertLogs("numpadctl", "WARNING"):
            d.note_drop(gone, now=1000.0)         # the window has passed and it is still happening: say it again
            d.note_drop(gone, now=1010.0)
            d.note_drop(gone, now=1020.0)

    def test_drops_spread_over_a_long_time_are_not_flapping(self):
        d, gone = self.bare(), OSError(errno.ENODEV, "No such device")
        with self.assertNoLogs("numpadctl", "WARNING"):
            for now in (0.0, 700.0, 1400.0, 2100.0):
                d.note_drop(gone, now=now)

    def test_other_errors_and_windows_are_not_taken_for_usb_trouble(self):
        d = self.bare()
        with self.assertNoLogs("numpadctl", "WARNING"):
            for now in (1.0, 2.0, 3.0, 4.0):
                d.note_drop(RuntimeError("the keyboard hook failed"), now=now)
        with mock.patch.object(daemon, "IS_WINDOWS", True), self.assertNoLogs("numpadctl", "WARNING"):
            for now in (5.0, 6.0, 7.0):
                d.note_drop(OSError(errno.ENODEV, "x"), now=now)

    def test_a_key_that_is_not_on_the_pad_is_explained_once(self):
        d = self.bare()
        d.broadcast = lambda message: None
        d.detect_future, d.capturing, d.paused = None, {object()}, False   # stops right after the log line
        with mock.patch.object(daemon.keys, "known", return_value=False), self.assertLogs("numpadctl", "INFO") as seen:
            d.key_event("KEY_PROG1", True)
            d.key_event("KEY_PROG1", True)
        explained = [line for line in seen.output if "isn't on the pad yet" in line]
        self.assertEqual(len(explained), 1, "once, however often the key is pressed")
        self.assertIn("turn on Learn", explained[0])


class SwallowedKeyTest(unittest.TestCase):
    def daemon(self):
        d = daemon.Daemon.__new__(daemon.Daemon)
        d.cfg, d.unknown_logged, d.detect_future, d.paused = {}, set(), None, False
        d.broadcast = lambda message: None
        return d

    def test_a_key_the_settings_window_takes_says_so_in_the_log(self):
        d = self.daemon()
        d.capturing = {object()}
        with mock.patch.object(daemon.keys, "known", return_value=True), self.assertLogs("numpadctl", "INFO") as seen:
            d.key_event("1", True)
            d.key_event("1", False)             # the release is not logged again
        self.assertEqual(len(seen.output), 1)
        self.assertIn("key 1: not run, the settings window is taking the keys", seen.output[0])
        self.assertIn("Select a key when I press it", seen.output[0])

    def test_a_key_while_paused_says_it_is_paused(self):
        d = self.daemon()
        d.capturing, d.paused = set(), True
        with mock.patch.object(daemon.keys, "known", return_value=True), self.assertLogs("numpadctl", "INFO") as seen:
            d.key_event("1", True)
        self.assertIn("NumpadControl is paused", seen.output[0])


class CopyLogTest(unittest.TestCase):
    def window(self):
        from tests.test_qt_window import QtWindowTest
        case = QtWindowTest("test_choose_action_edit_and_save")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        return case.w

    def test_tools_menu_copies_the_end_of_the_log(self):
        from PySide6.QtWidgets import QApplication
        w = self.window()
        with mock.patch.object(logs, "tail", return_value=["a", "b", "c"]) as tail:
            w.copy_log()
        tail.assert_called_once_with(w.COPY_LOG_LINES)
        self.assertEqual(QApplication.clipboard().text(), "a\nb\nc")

    def test_with_no_log_yet_it_says_so_and_copies_nothing(self):
        from PySide6.QtWidgets import QApplication
        w = self.window()
        QApplication.clipboard().setText("untouched")
        with mock.patch.object(logs, "tail", return_value=[]), mock.patch.object(w, "toast") as toast:
            w.copy_log()
        self.assertEqual(QApplication.clipboard().text(), "untouched")
        self.assertIn("No log yet", toast.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
