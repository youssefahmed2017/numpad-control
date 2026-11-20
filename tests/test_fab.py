"""The FAB (buttons.Fab, like Gmail's Compose), the Save-changes dialog built from it, and the top bar that now
holds only Settings and Save."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QToolButton  # noqa: E402

from numpadctl_ui import buttons, dialogs, theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")


def settle(seconds=0.7):
    """Let the FAB's animation run to its end."""
    import time
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)


class FabTest(unittest.TestCase):
    def test_it_is_56_tall_with_its_label_and_a_tonal_look(self):
        fab = buttons.Fab("Compose", "edit")
        self.assertEqual(fab.height(), buttons.FAB_HEIGHT)
        self.assertEqual(fab.text(), "Compose")
        container, content = fab._look()
        colours = theme.current
        self.assertEqual((container, content), (colours["primaryContainer"], colours["onPrimaryContainer"]))
        self.assertEqual(buttons.Fab("x", None, "fab_secondary")._look()[0], colours["secondaryContainer"])

    def test_collapsing_leaves_an_icon_only_square_and_expanding_brings_the_label_back(self):
        fab = buttons.Fab("Compose", "edit")
        full = fab.extended_width()
        self.assertGreater(full, buttons.FAB_HEIGHT)
        fab.set_collapsed(True, animate=False)
        self.assertTrue(fab.is_collapsed())
        self.assertEqual((fab.width(), fab.text()), (buttons.FAB_HEIGHT, ""))
        self.assertEqual(fab.toolTip(), "Compose", "a collapsed FAB names itself on hover")
        fab.set_collapsed(False, animate=False)
        self.assertEqual((fab.width(), fab.text()), (full, "Compose"))
        self.assertEqual(fab.toolTip(), "")

    def test_no_shadow_at_rest_and_one_that_grows_in_while_hovered(self):
        fab = buttons.Fab("Compose", "edit")
        shadow = fab._shadow
        self.assertEqual(shadow.color().alpha(), 0, "flat when nobody hovers it")
        fab._apply_shadow(0.5)
        half = (shadow.color().alpha(), shadow.blurRadius(), shadow.yOffset())
        fab._apply_shadow(1.0)
        full = (shadow.color().alpha(), shadow.blurRadius(), shadow.yOffset())
        self.assertGreater(half[0], 0)
        self.assertTrue(all(b > a for a, b in zip(half, full)), "deeper, wider and lower the more it is hovered")
        fab._apply_shadow(0.0)
        self.assertEqual(shadow.color().alpha(), 0, "and flat again when the pointer leaves")

    def test_the_corner_follows_the_shape_setting(self):
        fab = buttons.Fab("Save", "save")
        self.assertEqual(fab.current_radius(), buttons.FAB_RADIUS * theme.shape_factor())


class SaveChangesDialogTest(unittest.TestCase):
    def answer(self, which):
        dialog, result = dialogs.build_save_changes(None)
        dialog.buttons[which].click()
        return result[0]

    def test_each_button_gives_its_answer(self):
        for which in ("save", "discard", "cancel"):
            self.assertEqual(self.answer(which), which)

    def test_closing_it_without_a_choice_cancels(self):
        dialog, result = dialogs.build_save_changes(None)
        dialog.reject()
        self.assertEqual(result[0], "cancel")

    def test_save_and_dont_save_are_fabs_and_cancel_is_a_text_button(self):
        dialog, _ = dialogs.build_save_changes(None)
        self.assertIsInstance(dialog.buttons["save"], buttons.Fab)
        self.assertIsInstance(dialog.buttons["discard"], buttons.Fab)
        self.assertNotIsInstance(dialog.buttons["cancel"], buttons.Fab)
        self.assertEqual(dialog.buttons["save"].text(), "Save")
        self.assertEqual(dialog.buttons["discard"].text(), "Don't save")


class TopBarTest(unittest.TestCase):
    def test_settings_and_save_are_fabs_and_learn_and_tools_stay_ordinary(self):
        from tests.test_qt_window import QtWindowTest
        case = QtWindowTest("test_choose_action_edit_and_save")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        w, bar = case.w, case.w.appbar
        texts = sorted(b.text() for b in bar.findChildren(QPushButton) + bar.findChildren(QToolButton))
        self.assertEqual(texts, ["Learn", "Save", "Settings", "Tools"])
        fabs = [b for b in bar.findChildren(buttons.Fab)]
        self.assertEqual(sorted(f.text() for f in fabs), ["Save", "Settings"], "only these two are FABs")
        self.assertEqual(w.save_button._look()[0], theme.current["primaryContainer"])
        self.assertIsNone(w.learn.graphicsEffect(), "no shadow on Learn")
        self.assertIsNotNone(w.save_button.graphicsEffect())
        self.assertIsNotNone(w.settings_button.graphicsEffect())
        self.assertTrue(w.follow.isCheckable())

    def test_the_top_bar_fabs_collapse_in_a_narrow_window_and_come_back(self):
        from tests.test_qt_window import QtWindowTest
        case = QtWindowTest("test_choose_action_edit_and_save")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        w = case.w
        w.show()
        w.resize(700, 600)
        settle()
        self.assertTrue(w.save_button.is_collapsed() and w.settings_button.is_collapsed())
        self.assertEqual((w.save_button.text(), w.save_button.width()), ("", buttons.FAB_HEIGHT))
        w.resize(1180, 700)
        settle()
        self.assertFalse(w.save_button.is_collapsed())
        self.assertEqual(w.save_button.text(), "Save")
        self.assertGreater(w.save_button.width(), buttons.FAB_HEIGHT)


if __name__ == "__main__":
    unittest.main()
