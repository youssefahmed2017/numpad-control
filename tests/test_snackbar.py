"""The Material 3 snackbar: it arrives, waits, leaves, and is placed and sized the way the spec says."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QImage
try:
    from PySide6.QtTest import QTest
except ImportError:   # the pruned venv from setup.sh has no QtTest
    raise unittest.SkipTest("PySide6.QtTest is not installed")
from PySide6.QtWidgets import QApplication, QWidget

from numpadctl_ui import motion, snackbar, theme, tokens

APP = QApplication.instance() or QApplication([])


class SnackbarTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(theme, "current", tokens.colors("Orchid", True))
        patch.start()
        self.addCleanup(patch.stop)
        self.window = QWidget()
        self.window.resize(900, 600)
        self.window.show()
        self.bar = snackbar.Snackbar(self.window)
        self.addCleanup(self.window.deleteLater)

    def test_it_is_hidden_until_there_is_something_to_say(self):
        self.assertFalse(self.bar.isVisible())
        self.assertEqual(self.bar.text(), "")

    def test_it_arrives_fading_in_and_rising_and_ends_at_rest(self):
        self.bar.show_message("Saved")
        self.assertTrue(self.bar.isVisible())
        self.assertEqual(self.bar.text(), "Saved")
        start_y = self.bar.y()
        QTest.qWait(motion.MEDIUM1 + 80)
        self.assertAlmostEqual(self.bar._alpha, 1.0, places=2)
        self.assertLess(self.bar.y(), start_y, "it rose into place")
        self.assertEqual(self.bar.y(), self.window.height() - self.bar.height() + snackbar.SHADOW - snackbar.BOTTOM_GAP)

    def test_it_sits_in_the_bottom_centre_16_px_up_and_is_48_px_tall_for_one_line(self):
        self.bar.show_message("Saved")
        QTest.qWait(motion.MEDIUM1 + 80)
        body_h = self.bar.height() - 2 * snackbar.SHADOW
        body_w = self.bar.width() - 2 * snackbar.SHADOW
        self.assertEqual(body_h, 48)
        self.assertGreaterEqual(body_w, snackbar.MIN_WIDTH)
        self.assertEqual(self.bar.x() + self.bar.width() // 2, self.window.width() // 2)
        bottom_of_body = self.bar.y() + snackbar.SHADOW + body_h
        self.assertEqual(self.window.height() - bottom_of_body, snackbar.BOTTOM_GAP)

    def test_a_long_message_wraps_and_grows_but_never_gets_wider_than_the_limit(self):
        self.bar.show_message("Key 5 failed because the service isn't running, so nothing was sent to OBS. " * 3)
        body_w = self.bar.width() - 2 * snackbar.SHADOW
        body_h = self.bar.height() - 2 * snackbar.SHADOW
        self.assertLessEqual(body_w, snackbar.MAX_WIDTH)
        self.assertGreater(body_h, 48)

    def test_it_leaves_by_itself_after_its_time(self):
        self.bar.show_message("Saved", ms=120)
        QTest.qWait(120 + motion.SHORT3 + 150)
        self.assertFalse(self.bar.isVisible())
        self.assertEqual(self.bar.text(), "")

    def test_a_new_message_replaces_the_old_one_in_place_without_arriving_again(self):
        self.bar.show_message("First", ms=2000)
        QTest.qWait(motion.MEDIUM1 + 80)
        y = self.bar.y()
        self.bar.show_message("Second, and a little longer", ms=2000)
        self.assertEqual(self.bar.text(), "Second, and a little longer")
        self.assertAlmostEqual(self.bar._alpha, 1.0, places=2, msg="no fade out and in again")
        self.assertEqual(self.bar.y() + self.bar.height(), y + self.bar.height())

    def test_a_message_that_arrives_while_leaving_comes_back(self):
        self.bar.show_message("First", ms=2000)
        QTest.qWait(motion.MEDIUM1 + 60)
        self.bar.dismiss()
        QTest.qWait(40)
        self.bar.show_message("Again", ms=2000)
        QTest.qWait(motion.MEDIUM1 + 100)
        self.assertTrue(self.bar.isVisible())
        self.assertEqual(self.bar.text(), "Again")

    def test_clear_removes_it_at_once(self):
        self.bar.show_message("Saved")
        self.bar.clear()
        self.assertFalse(self.bar.isVisible())

    def test_it_follows_the_window_when_it_is_resized(self):
        self.bar.show_message("Saved")
        QTest.qWait(motion.MEDIUM1 + 80)
        self.window.resize(1200, 800)
        self.bar.reposition()
        self.assertEqual(self.bar.x() + self.bar.width() // 2, 600)
        self.assertEqual(self.window.height() - (self.bar.y() + snackbar.SHADOW + 48), snackbar.BOTTOM_GAP)

    def test_it_paints_the_inverse_surface_with_inverse_text(self):
        self.bar.show_message("Saved")
        QTest.qWait(motion.MEDIUM1 + 80)
        image = QImage(self.bar.size(), QImage.Format_ARGB32)
        image.fill(0)
        self.bar.render(image)
        centre = image.pixelColor(snackbar.SHADOW + 6, self.bar.height() // 2)
        self.assertEqual(centre.name(), tokens.colors("Orchid", True)["inverseSurface"])


if __name__ == "__main__":
    unittest.main()
