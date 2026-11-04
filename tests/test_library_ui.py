"""Profile ⋯ → Browse library…: the dialog, and the import it leads to (offscreen, no network)."""

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl import library  # noqa: E402
from numpadctl_ui.library_dialog import LibraryDialog  # noqa: E402
from tests.test_library import PROFILE, entry, index  # noqa: E402
from tests import test_qt_window  # noqa: E402  (module, so its tests are not collected twice)

APP = QApplication.instance() or QApplication([])


def at_once(work):
    work()


ENTRIES = library.parse_index(index(
    entry(),
    entry(path="profiles/community/ann/zoom.json", name="Zoom", author="ann", tags=["meetings"],
          match=["zoom"], risky_actions=["press_keys"]),
    entry(path="profiles/community/bob/future.json", name="Future", author="bob", min_app_version="99.0.0")))


class DialogTest(unittest.TestCase):
    def dialog(self, fetch_index=lambda: ENTRIES, fetch_profile=lambda e: json.dumps(PROFILE)):
        d = LibraryDialog(None, fetch_index=fetch_index, fetch_profile=fetch_profile, run=at_once)
        self.addCleanup(d.deleteLater)
        return d

    def test_lists_profiles_and_filters_them(self):
        d = self.dialog()
        self.assertEqual(d.list.count(), 3)
        self.assertIn("Official", d.list.item(0).text())
        d.tier.setCurrentIndex(2)   # Community
        self.assertEqual([e.name for e in d.shown], ["Zoom", "Future"])
        d.search.setText("meetings")
        self.assertEqual([e.name for e in d.shown], ["Zoom"])
        self.assertIn("⚠ 1", d.list.item(0).text())
        self.assertIn("Press keys", d.details.text())   # the action's name, not its id
        d.search.setText("nothing like this")
        self.assertEqual(d.status.text(), "No profile matches that.")
        self.assertFalse(d.import_button.isEnabled())

    def test_a_profile_for_a_newer_app_cannot_be_imported(self):
        d = self.dialog()
        d.search.setText("future")
        self.assertIn("needs NumpadControl 99.0.0", d.list.item(0).text())
        self.assertFalse(d.import_button.isEnabled())

    def test_import_fetches_the_chosen_profile(self):
        asked = []
        d = self.dialog(fetch_profile=lambda e: asked.append(e.path) or json.dumps(PROFILE))
        d.list.setCurrentRow(0)
        d.import_selected()
        self.assertEqual(asked, ["profiles/official/obs-streaming.json"])
        self.assertEqual(d.result_entry.name, "Streaming (OBS)")
        self.assertEqual(json.loads(d.result_text)["profile"]["name"], "Streaming")

    def test_errors_are_shown_with_a_retry(self):
        calls = []

        def fetch():
            calls.append(1)
            if len(calls) == 1:
                raise library.LibraryError("couldn't reach the library (no network). Are you online?")
            return ENTRIES

        d = self.dialog(fetch_index=fetch)
        self.assertIn("Are you online", d.status.text())
        self.assertFalse(d.retry.isHidden())
        d.retry.click()
        self.assertEqual(d.list.count(), 3)
        self.assertTrue(d.retry.isHidden())

    def test_a_failed_download_keeps_the_dialog_open(self):
        def broken(e):
            raise library.LibraryError("the library isn't available there yet (not found)")

        d = self.dialog(fetch_profile=broken)
        d.import_selected()
        self.assertIsNone(d.result_text)
        self.assertIn("not found", d.status.text())
        self.assertTrue(d.import_button.isEnabled())

    def test_a_bug_in_fetching_is_reported_not_raised(self):
        d = self.dialog(fetch_index=lambda: 1 / 0)
        self.assertIn("something went wrong", d.status.text())


class WindowTest(unittest.TestCase):
    def setUp(self):
        test_qt_window.QtWindowTest.setUp(self)   # a real settings window on a temporary config
        self.addCleanup(self.tmp.cleanup)

    def test_a_library_profile_goes_through_the_import_confirmation(self):
        before = len(self.w.cfg["profiles"])
        community = next(e for e in ENTRIES if e.author == "ann")
        seen = []
        with mock.patch.object(self.w, "confirm_import", lambda p, d, source=None: seen.append(source) or True):
            self.assertTrue(self.w.browse_library(ask=lambda parent: (community, json.dumps(PROFILE))))
        self.assertEqual(seen, ["From the profile library: community profile by @ann."])
        self.assertEqual(len(self.w.cfg["profiles"]), before + 1)
        self.assertEqual(self.w.cfg["profiles"][-1]["match"], "obs,obs64")

    def test_saying_no_adds_nothing(self):
        before = len(self.w.cfg["profiles"])
        with mock.patch.object(self.w, "confirm_import", lambda p, d, source=None: False):
            self.assertFalse(self.w.browse_library(ask=lambda parent: (ENTRIES[0], json.dumps(PROFILE))))
        self.assertEqual(len(self.w.cfg["profiles"]), before)

    def test_closing_the_library_adds_nothing(self):
        before = len(self.w.cfg["profiles"])
        self.assertFalse(self.w.browse_library(ask=lambda parent: None))
        self.assertEqual(len(self.w.cfg["profiles"]), before)

    def test_the_menu_has_it(self):
        from PySide6.QtWidgets import QToolButton
        found = [a for b in self.w.findChildren(QToolButton) if b.menu() for a in b.menu().actions()
                 if a.text() == "Browse library…"]
        self.assertEqual(len(found), 1)
        from numpadctl_ui import library_dialog
        with mock.patch.object(library_dialog.LibraryDialog, "ask", lambda parent: None) as _:
            found[0].trigger()   # opens the (patched) dialog; nothing is added when it is closed


class ThreadedTest(unittest.TestCase):
    """The real way it runs: fetching on a worker thread, results handed back to the window's thread."""

    def test_list_and_import_arrive_from_the_worker_thread(self):
        import time
        from tests.test_library import LibraryFolder
        lib = LibraryFolder(entry())
        self.addCleanup(lib.tmp.cleanup)
        with mock.patch.dict(os.environ, {"NUMPADCTL_LIBRARY": str(lib.root)}):
            d = LibraryDialog(None)
            self.addCleanup(d.deleteLater)

            def wait_for(check):
                end = time.monotonic() + 5
                while not check() and time.monotonic() < end:
                    APP.processEvents()
                    time.sleep(0.01)
                return check()

            self.assertTrue(wait_for(lambda: d.entries), d.status.text())
            d.import_selected()
            self.assertTrue(wait_for(lambda: d.result_text is not None), d.status.text())
        self.assertEqual(json.loads(d.result_text)["profile"]["name"], "Streaming")


if __name__ == "__main__":
    unittest.main()
