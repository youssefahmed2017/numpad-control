"""The checkbox draws its tick over time instead of showing it in one frame (run invisibly, offscreen)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl_ui import checkbox, theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")


def tick_pixels(box, progress):
    """How many pixels of the box are the tick's colour at `progress`."""
    box.resize(200, 30)
    box._set_progress(progress)
    image = QImage(box.size(), QImage.Format_ARGB32)
    image.fill(0)
    box.render(image)
    tick = int(theme.current["onPrimary"].lstrip("#"), 16)
    return sum(1 for x in range(image.width()) for y in range(image.height())
               if image.pixel(x, y) & 0xFFFFFF == tick)


class CheckBoxTest(unittest.TestCase):
    def test_a_box_filled_in_before_it_is_shown_is_already_ticked(self):
        box = checkbox.CheckBox("x")
        box.setChecked(True)
        self.assertEqual(box.progress(), 1.0)
        box.setChecked(False)
        self.assertEqual(box.progress(), 0.0)

    def test_ticking_a_visible_box_runs_over_time_and_ends_ticked(self):
        box = checkbox.CheckBox("x")
        box.show()
        box.setChecked(True)
        self.assertTrue(box._draw.running())
        self.assertEqual(box.progress(), 0.0)
        box._draw.set_time(box._draw.duration // 3)
        self.assertTrue(0.0 < box.progress() < 1.0)
        box._draw.set_time(box._draw.duration)
        self.assertEqual(box.progress(), 1.0)

    def test_unticking_runs_back_faster(self):
        box = checkbox.CheckBox("x")
        box.setChecked(True)
        box.show()
        box.setChecked(False)
        self.assertTrue(box._erase.running())
        self.assertLess(box._erase.duration, box._draw.duration)
        box._erase.set_time(box._erase.duration)
        self.assertEqual(box.progress(), 0.0)

    def test_changing_mind_midway_starts_from_where_it_is(self):
        box = checkbox.CheckBox("x")
        box.show()
        box.setChecked(True)
        box._draw.set_time(box._draw.duration // 2)
        middle = box.progress()
        box.setChecked(False)
        self.assertAlmostEqual(box.progress(), middle, places=2)

    def test_the_tick_is_drawn_a_bit_more_at_each_step(self):
        box = checkbox.CheckBox("x")
        counts = [tick_pixels(box, p) for p in (0.3, 0.5, 0.7, 1.0)]
        self.assertEqual(counts[0], 0)   # still just filling the box
        self.assertTrue(counts[1] < counts[2] < counts[3], counts)

    def test_the_tick_path_grows_with_its_share(self):
        box = QRectF(0, 0, 16, 16)
        lengths = [checkbox.tick_path(share, box).length() for share in (0.25, 0.5, 1.0)]
        self.assertTrue(lengths[0] < lengths[1] < lengths[2])
        self.assertAlmostEqual(lengths[2], 4.243 + 9.220, places=2)


if __name__ == "__main__":
    unittest.main()


class SwitchTest(unittest.TestCase):
    """The M3 switch: nothing on it changes in one frame (thumb, halo and colours all move over time)."""

    def frames(self, move, setter_value, count=12):
        """Values of `setter_value()` at `count` evenly spread moments of the spring `move`."""
        values = []
        for i in range(count + 1):
            move.set_time(move.duration * i // count)
            values.append(round(setter_value(), 3))
        return values

    def test_pressing_swells_the_thumb_and_halo_over_many_frames(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        switch = checkbox.Switch("x")
        switch.resize(200, 40)
        switch.show()
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(20, 20), QPointF(20, 20), Qt.LeftButton,
                            Qt.LeftButton, Qt.NoModifier)
        switch.mousePressEvent(press)
        self.assertTrue(switch._squeeze.running(), "a press starts a move, not a jump")
        values = self.frames(switch._squeeze, lambda: switch._press)
        self.assertEqual(values[0], 0.0)
        self.assertGreater(len(set(values)), 8, "the swell spans many frames")
        self.assertAlmostEqual(values[-1], 1.0, delta=0.01)
        switch.render(QImage(switch.size(), QImage.Format_ARGB32))   # drawing mid-press works

    def test_hover_fades_the_halo_in(self):
        switch = checkbox.Switch("x")
        switch.show()
        switch._glow.go(0.0, 1.0)
        values = self.frames(switch._glow, lambda: switch._hover)
        self.assertGreater(len(set(values)), 8)

    def test_set_before_it_is_shown_it_is_already_on(self):
        switch = checkbox.Switch("x")
        switch.setChecked(True)
        self.assertEqual(switch.position(), 1.0)

    def test_flipping_it_slides_the_thumb(self):
        switch = checkbox.Switch("x")
        switch.show()
        switch.setChecked(True)
        values = self.frames(switch._slide, switch.position)
        self.assertGreater(len(set(values)), 8)
        self.assertAlmostEqual(values[-1], 1.0, delta=0.01)
