"""The morphing buttons animate over many frames (never a one-frame jump), and scrolling glides."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from numpadctl.qt import buttons, effects, theme, window  # noqa: E402

APP = QApplication.instance() or QApplication([])
APP.installEventFilter(effects.RippleFilter(APP))
theme.apply(APP, "dark", "Orchid", "standard")


def sample(button, ms=700, every=16):
    """current_radius() every `every` ms."""
    values = []
    for _ in range(ms // every):
        values.append(button.current_radius())
        QTest.qWait(every)
    return values


class MorphTest(unittest.TestCase):
    def check_quick_click(self, button, hovered_radius):
        button.show()
        QTest.qWait(50)
        rest = button.current_radius()
        QTest.mouseMove(button, QPoint(10, 10))
        QTest.mousePress(button, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
        QTest.qWait(30)  # a fast click: released 30 ms after the press
        QTest.mouseRelease(button, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
        values = sample(button)
        self.assertGreater(len({round(v, 1) for v in values}), 12, "the squeeze and the spring back span many frames")
        self.assertLess(min(values), rest - 3, "it squeezes visibly smaller")
        frames_squeezed = sum(v < rest - 2 for v in values)
        self.assertGreaterEqual(frames_squeezed * 16, 100, "and stays squeezed for a perceptible time")
        self.assertAlmostEqual(values[-1], hovered_radius, delta=1.5,
                               msg="then springs back to the hovered shape (the pointer is still over it)")
        button.deleteLater()

    def test_push_button(self):
        button = buttons.PushButton("Save")
        button.resize(140, 40)
        self.check_quick_click(button, 20)

    def test_tool_button(self):
        button = buttons.ToolButton(text="Learn")
        button.resize(100, 36)
        self.check_quick_click(button, 18)

    def test_numpad_key(self):
        key = window.KeyButton("5")
        key.resize(110, 70)
        self.check_quick_click(key, window.KEY_HOVER_RADIUS)

    def test_hover_makes_it_rounder_gradually(self):
        button = buttons.PushButton("Settings")
        button.resize(140, 40)
        button.show()
        QTest.qWait(30)
        rest = button.current_radius()
        button._go(button._hover_anim, 0, 1)
        values = sample(button, 400)
        self.assertGreater(max(values), rest + 5)
        self.assertGreater(len({round(v, 1) for v in values}), 5)
        self.assertAlmostEqual(max(values), 20, delta=0.6, msg="fully round at the end: half the height")
        button.deleteLater()


class StuckTest(unittest.TestCase):
    def test_released_button_returns_even_if_nothing_repaints_it(self):
        """Regression: after a click the button stayed squeezed (the release only ran inside paintEvent)."""
        button = buttons.PushButton("Tools")
        button.resize(140, 40)
        button.show()
        QTest.qWait(30)
        button.setDown(True)
        button.update()
        QTest.qWait(60)
        self.assertGreater(button._press, 0.3, "squeezed while down")
        button.setDown(False)
        button.paintEvent = lambda event: None  # nothing repaints it from here on
        QTest.qWait(700)
        self.assertLess(abs(button._press), 0.02, "it let go on its own")
        button.deleteLater()

    def test_press_that_never_gets_a_release_still_ends(self):
        """A tool button whose menu opened never sees the mouse release."""
        button = buttons.ToolButton(text="Tools")
        button.resize(100, 36)
        button.show()
        QTest.qWait(30)
        button.setDown(True)
        button.update()
        QTest.qWait(80)
        button.setDown(False)  # what Qt does once the menu closes
        QTest.qWait(700)
        self.assertLess(abs(button._press), 0.02)
        button.deleteLater()


class ScrollTest(unittest.TestCase):
    def test_wheel_glides_to_the_target(self):
        area = buttons.SmoothScrollArea()
        page = QWidget()
        layout = QVBoxLayout(page)
        for i in range(60):
            layout.addWidget(QLabel(f"row {i}"))
        area.setWidget(page)
        area.setWidgetResizable(True)
        area.resize(300, 200)
        area.show()
        QTest.qWait(30)
        bar = area.verticalScrollBar()
        event = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                            Qt.NoModifier, Qt.NoScrollPhase, False)
        area.wheelEvent(event)
        seen = set()
        for _ in range(25):
            QTest.qWait(16)
            seen.add(bar.value())
        self.assertEqual(bar.value(), buttons.SCROLL_PX_PER_NOTCH, "one notch = a fixed distance")
        self.assertGreater(len(seen), 6, "it passed through many positions on the way")
        area.deleteLater()


class PopupTest(unittest.TestCase):
    def test_combo_rows_use_the_stylesheet_and_popup_reveals(self):
        combo = buttons.ComboBox()
        combo.addItems(["one", "two", "three"])
        combo.show()
        self.assertEqual(type(combo.itemDelegate()).__name__, "QStyledItemDelegate")
        combo.showPopup()
        QTest.qWait(250)
        combo.hidePopup()
        combo.deleteLater()

    def test_menu_opens(self):
        menu = buttons.Menu()
        menu.addAction("a")
        menu.addAction("b")
        menu.popup(QPoint(10, 10))
        QTest.qWait(250)
        menu.close()


if __name__ == "__main__":
    unittest.main()
