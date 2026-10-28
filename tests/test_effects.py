"""Ripples, elevation and fade-in run, draw something, and clean up after themselves."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QWidget  # noqa: E402

from numpadctl_ui import effects, theme  # noqa: E402

APP = QApplication.instance() or QApplication([])
FILTER = effects.RippleFilter(APP)
APP.installEventFilter(FILTER)
theme.apply(APP, "dark", "Orchid", "standard")


def pixels(widget):
    image = widget.grab().toImage().convertToFormat(QImage.Format_RGB32)
    return {image.pixel(x, y) for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)}


class EffectsTest(unittest.TestCase):
    def test_press_starts_a_ripple_that_draws_then_ends(self):
        button = QPushButton("Save")
        button.resize(160, 40)
        button.show()
        before = pixels(button)
        QTest.mousePress(button, Qt.LeftButton, Qt.NoModifier, QPoint(20, 20))
        QTest.qWait(120)
        ripple = button.findChild(effects.Ripple)
        self.assertIsNotNone(ripple, "a ripple layer was added on first press")
        self.assertEqual(ripple.animation.state().name, "Running")
        self.assertNotEqual(pixels(button), before, "the ripple is visible mid-animation")
        QTest.mouseRelease(button, Qt.LeftButton, Qt.NoModifier, QPoint(20, 20))
        QTest.qWait(effects.RIPPLE_MS + 80)
        self.assertEqual(ripple.animation.state().name, "Stopped")
        self.assertEqual(pixels(button), before, "nothing is left drawn after it ends")
        button.deleteLater()

    def test_checkboxes_and_disabled_buttons_do_not_ripple(self):
        box, off = QCheckBox("x"), QPushButton("y")
        off.setEnabled(False)
        for widget in (box, off):
            widget.show()
            QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
            self.assertIsNone(widget.findChild(effects.Ripple))
            widget.deleteLater()

    def test_fade_in_removes_its_effect_when_done(self):
        page = QWidget()
        page.show()
        effects.fade_in(page, ms=40)
        self.assertIsNotNone(page.graphicsEffect())
        QTest.qWait(150)
        self.assertIsNone(page.graphicsEffect(), "no graphics effect left to cost anything")
        page.deleteLater()

    def test_elevation_adds_a_shadow(self):
        widget = QWidget()
        effects.elevate(widget, 2)
        self.assertGreater(widget.graphicsEffect().blurRadius(), 0)
        widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
