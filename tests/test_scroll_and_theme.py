"""Scrolling over a dropdown scrolls the page (it doesn't change the choice), and the
window follows the system's light / dark switch without being reopened."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from numpadctl_ui import buttons, theme  # noqa: E402

APP = QApplication.instance() or QApplication([])


def wheel_over(widget):
    """A real mouse-wheel notch delivered to `widget`, the way Qt sends it (it can bubble up)."""
    centre = QPointF(widget.width() / 2, widget.height() / 2)
    event = QWheelEvent(centre, widget.mapToGlobal(centre), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                        Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


class WheelTest(unittest.TestCase):
    def page_with(self, field):
        area = buttons.SmoothScrollArea()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(field)
        for _ in range(30):
            layout.addWidget(buttons.PushButton("filler"))
        area.setWidget(page)
        area.setWidgetResizable(True)
        area.resize(300, 200)
        area.show()
        self.addCleanup(area.close)
        QTest.qWait(30)
        return area

    def test_wheel_over_a_dropdown_scrolls_the_page_instead(self):
        combo = buttons.ComboBox()
        combo.addItems(["one", "two", "three"])
        area = self.page_with(combo)
        wheel_over(combo)
        QTest.qWait(400)
        self.assertEqual(combo.currentIndex(), 0, "the choice didn't change")
        self.assertGreater(area.verticalScrollBar().value(), 0, "the page scrolled")

    def test_wheel_over_a_number_field_doesnt_change_it(self):
        spin = buttons.SpinBox()
        spin.setRange(0, 100)
        spin.setValue(50)
        self.page_with(spin)
        wheel_over(spin)
        self.assertEqual(spin.value(), 50)

    def test_wheel_doesnt_take_focus(self):
        self.assertEqual(buttons.ComboBox().focusPolicy(), Qt.StrongFocus)


class FollowSystemTest(unittest.TestCase):
    def setUp(self):
        theme.apply(APP, "light", "Orchid", "standard")
        self.addCleanup(theme.listeners.clear)

    def test_switches_when_the_system_does(self):
        system = {"dark": False}
        with mock.patch.object(theme, "system_prefers_dark", lambda app: system["dark"]):
            check, timer = theme.follow_system(APP, lambda: {"appearance": "auto", "accent": "Orchid"})
            light_surface = theme.current["surface"]
            system["dark"] = True
            check()
            self.assertNotEqual(theme.current["surface"], light_surface)
            self.assertLess(theme.current["surface"], "#808080", "now dark")
        if timer:
            timer.stop()

    def test_a_chosen_light_or_dark_ignores_the_system(self):
        system = {"dark": False}
        with mock.patch.object(theme, "system_prefers_dark", lambda app: system["dark"]):
            check, timer = theme.follow_system(APP, lambda: {"appearance": "light"})
            before = dict(theme.current)
            system["dark"] = True
            check()
            self.assertEqual(theme.current, before)
        if timer:
            timer.stop()

    def test_apply_repaints_and_tells_listeners(self):
        seen = []
        theme.listeners.append(seen.append)
        theme.apply(APP, "dark", "Orchid", "standard")
        self.assertEqual(seen[-1]["surface"], theme.current["surface"])


if __name__ == "__main__":
    unittest.main()
