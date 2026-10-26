"""Crash reports: saved without personal paths, asked about once per crash, sent only on Yes,
and every failure along the way falls back instead of hiding the crash."""

import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from numpadctl import crash


def exc_info(message="boom"):
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


class CrashTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.spawned = []
        for patch in [mock.patch.object(crash, "crashes_dir", lambda: self.folder),
                      mock.patch.object(crash, "_spawn_dialog", self.spawned.append),
                      mock.patch.object(crash.webbrowser, "open")]:
            patch.start()
            self.addCleanup(patch.stop)
        self.browser = crash.webbrowser.open

    def reports(self):
        return [r for _, r in crash._reports()]

    def test_a_crash_is_saved_and_asked_about_in_its_own_process(self):
        crash.report("service", exc_info())
        (report,) = self.reports()
        self.assertEqual((report["component"], report["state"]), ("service", "pending"))
        self.assertEqual(report["error"], "ValueError: boom")
        self.assertIn("raise ValueError", report["traceback"])
        self.assertEqual(len(self.spawned), 1)

    def test_home_folder_and_user_name_are_taken_out(self):
        with mock.patch.object(crash.Path, "home", lambda: Path("/home/alice")), \
                mock.patch.object(crash.getpass, "getuser", lambda: "alice"):
            text = crash._sanitize('File "/home/alice/numpad-control/x.py" (user alice, not malice)')
        self.assertEqual(text, 'File "~/numpad-control/x.py" (user <user>, not malice)')

    def test_the_same_crash_again_is_saved_but_not_asked_again(self):
        for _ in range(3):  # e.g. a service restarted again and again, crashing the same way
            crash.report("service", exc_info())
        self.assertEqual([r["state"] for r in self.reports()], ["pending", "repeat", "repeat"])
        self.assertEqual(len(self.spawned), 1)

    def test_yes_opens_a_prefilled_issue(self):
        crash.report("service", exc_info())
        with mock.patch.object(crash, "_dialog", return_value=True):
            crash.ask(self.spawned[0])
        self.assertEqual(self.reports()[0]["state"], "reported")
        url = self.browser.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertTrue(url.startswith(crash.ISSUE_URL))
        self.assertEqual(query["title"], ["Crash: ValueError: boom"])
        self.assertIn("raise ValueError", query["body"][0])

    def test_no_sends_nothing(self):
        crash.report("service", exc_info())
        with mock.patch.object(crash, "_dialog", return_value=False):
            crash.ask(self.spawned[0])
        self.assertEqual(self.reports()[0]["state"], "declined")
        self.browser.assert_not_called()

    def test_without_a_desktop_it_asks_at_the_next_start(self):
        crash.report("service", exc_info())
        with mock.patch.object(crash, "_dialog", return_value=None):
            crash.ask(self.spawned[0])
        self.assertEqual(self.reports()[0]["state"], "pending")
        self.spawned.clear()
        crash.ask_pending()
        self.assertEqual(len(self.spawned), 1)

    def test_a_dialog_that_is_still_open_is_not_asked_again(self):
        """The crashed service restarts within seconds while its crash dialog is still up."""
        crash.report("service", exc_info())
        path = self.spawned.pop()
        report = crash._load(path)
        report.update(state="asking", asking_since=time.time())
        crash._store(path, report)
        crash.ask_pending()
        self.assertEqual(self.spawned, [])
        report["asking_since"] = time.time() - crash.ASKING_TIMEOUT - 1  # its process died long ago
        crash._store(path, report)
        crash.ask_pending()
        self.assertEqual(self.spawned, [path])

    def test_gives_up_after_a_few_attempts(self):
        crash.report("service", exc_info())
        with mock.patch.object(crash, "_dialog", return_value=None) as dialog:
            for _ in range(crash.MAX_ATTEMPTS + 2):
                crash.ask(self.spawned[0])
        self.assertEqual(dialog.call_count, crash.MAX_ATTEMPTS)
        self.assertEqual(self.reports()[0]["state"], "gave up")

    def test_only_the_latest_waiting_crash_is_asked_about(self):
        with mock.patch.object(crash, "REPEAT_WINDOW", 0):  # two different crashes
            for message in ("one", "two"):
                crash.report("service", exc_info(message))
        self.spawned.clear()
        crash.ask_pending()
        self.assertEqual([r["state"] for r in self.reports()], ["skipped", "pending"])
        self.assertEqual(len(self.spawned), 1)

    def test_if_no_process_can_start_it_asks_from_the_crashing_one(self):
        with mock.patch.object(crash, "_spawn_dialog", side_effect=OSError("no processes left")), \
                mock.patch.object(crash, "_dialog", return_value=False) as dialog:
            crash.report("service", exc_info())
        dialog.assert_called_once()
        self.assertEqual(self.reports()[0]["state"], "declined")

    def test_a_failing_crash_handler_never_raises(self):
        with mock.patch.object(crash, "save", side_effect=PermissionError("disk full")), \
                mock.patch.object(crash.sys, "__stderr__") as stderr:
            crash.report("service", exc_info())  # must not raise
        self.assertIn("crash handler failed", stderr.write.call_args.args[0])

    def test_ctrl_c_is_not_a_crash(self):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            crash.report("service")
        self.assertEqual(self.reports(), [])

    def test_long_tracebacks_keep_their_end(self):
        report = {"error": "ValueError: x", "traceback": "start\n" + "x" * 20000 + "\nValueError: the end\n"}
        body = urllib.parse.parse_qs(urllib.parse.urlparse(crash.issue_url(report)).query)["body"][0]
        self.assertIn("ValueError: the end", body)
        self.assertNotIn("start", body)
        self.assertLess(len(body), crash.MAX_TRACEBACK + 1000)

    def test_old_reports_are_cleaned_up(self):
        with mock.patch.object(crash, "REPEAT_WINDOW", 0):
            for n in range(crash.KEEP_REPORTS + 5):
                crash.report("service", exc_info(str(n)))
        self.assertEqual(len(self.reports()), crash.KEEP_REPORTS)

    def test_install_reports_uncaught_exceptions_in_threads_and_keeps_the_old_hooks(self):
        old_hook, old_thread_hook = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_hook)
        self.addCleanup(setattr, threading, "excepthook", old_thread_hook)
        self.addCleanup(crash._installed.clear)
        previous = mock.Mock()
        threading.excepthook = previous
        crash.install("tray")
        thread = threading.Thread(target=lambda: 1 / 0)
        thread.start()
        thread.join()
        self.assertEqual(self.reports()[0]["component"], "tray")
        self.assertIn("ZeroDivisionError", self.reports()[0]["error"])
        previous.assert_called_once()


class DialogTest(unittest.TestCase):
    @unittest.skipIf(crash.IS_WINDOWS, "Linux dialogs")
    def test_linux_uses_the_first_dialog_program_it_finds(self):
        import shutil
        with mock.patch.dict(crash.os.environ, {"DISPLAY": ":0"}), \
                mock.patch.object(shutil, "which", lambda name: name == "kdialog"), \
                mock.patch.object(crash.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertTrue(crash._dialog("crashed"))
        self.assertEqual(run.call_args.args[0][:3], ["kdialog", "--title", crash.TITLE])

    @unittest.skipIf(crash.IS_WINDOWS, "Linux dialogs")
    def test_linux_without_a_display_cant_ask(self):
        env = {k: v for k, v in crash.os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        with mock.patch.dict(crash.os.environ, env, clear=True), \
                mock.patch.object(crash.subprocess, "run", return_value=mock.Mock(stdout="")):
            self.assertIsNone(crash._dialog("crashed"))

    @unittest.skipUnless(crash.IS_WINDOWS, "Windows message box")
    def test_windows_uses_a_plain_message_box(self):
        import ctypes
        with mock.patch.object(ctypes.windll.user32, "MessageBoxW", return_value=7) as box:  # IDNO
            self.assertFalse(crash._dialog("crashed"))
        self.assertEqual(box.call_args.args[2], crash.TITLE)


if __name__ == "__main__":
    unittest.main()
