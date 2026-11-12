"""Built-in key icons: every action has one, they are drawn (logos too), a sticker wins, and the setting hides
them (run invisibly, offscreen)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl import actions, config  # noqa: E402
from numpadctl_ui import action_icons, icons, theme, tokens  # noqa: E402

APP = QApplication.instance() or QApplication([])
theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")


class IconSetTest(unittest.TestCase):
    def test_every_action_has_an_icon_from_the_bundled_font_or_a_logo(self):
        """A new action without an icon fails here: give it one in action_icons.ICONS."""
        missing = [a.id for a in actions.ACTIONS if a.id != "none" and a.id not in action_icons.ICONS]
        self.assertEqual(missing, [])
        self.assertEqual(set(action_icons.ICONS) - set(actions.BY_ID), set(), "no icons for actions that don't exist")
        for action, (base, badge, _) in action_icons.ICONS.items():
            for name in (base, badge):
                if name and not name.startswith("brand:"):
                    self.assertIn(name, icons.CODEPOINTS, f"{action}: {name} isn't in the icon font")
                elif name:
                    self.assertTrue((action_icons.BRANDS / f"{name[6:]}.png").is_file(), name)

    def test_they_draw_including_the_logos_with_badges(self):
        for action in ("obs_start_recording", "run_python", "volume_up", "suspend"):
            picture = action_icons.pixmap(action, "#ffffff", 28, behind="#202020")
            self.assertFalse(picture.isNull())
            image = picture.toImage()
            self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(0, image.width(), 3)
                                for y in range(0, image.height(), 3)), f"{action} drew nothing")
        self.assertIsNone(action_icons.pixmap("none", "#ffffff"))

    def test_the_icon_is_the_press_action_else_hold_else_double(self):
        b = lambda a: {"action": a, "params": {}}   # noqa: E731
        self.assertEqual(action_icons.action_of({"tap": b("none"), "hold": b("lock_screen")}), "lock_screen")
        self.assertEqual(action_icons.action_of({"tap": b("mic_mute"), "hold": b("lock_screen")}), "mic_mute")
        self.assertIsNone(action_icons.action_of({}))


class KeyTest(unittest.TestCase):
    def tearDown(self):
        theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")

    def key(self):
        from numpadctl_ui import window
        button = window.KeyButton("7")
        button.resize(110, 70)
        button.show()
        self.addCleanup(button.deleteLater)
        return button

    def settle(self, button):
        for _ in range(3):
            button.repaint()
            APP.processEvents()

    def test_an_icon_under_a_small_name_and_a_sticker_wins(self):
        button = self.key()
        button.set_icon("volume_up")
        self.settle(button)
        self.assertEqual(button._mode, "icon")
        self.assertTrue(button.name.property("small"))
        self.assertFalse(button.picture.pixmap().isNull())
        button.sticker, button._sticker_pix = "cat.png", button.picture.pixmap()   # as set_sticker leaves it
        button._show()
        self.assertEqual(button._mode, "sticker")
        self.assertFalse(button.name.isVisible())

    def test_the_setting_turns_them_off_and_back_on(self):
        button = self.key()
        button.set_icon("volume_up")
        self.settle(button)
        theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard", config.look_settings({"look": {"action_icons": False}}))
        self.settle(button)
        self.assertIsNone(button._mode)
        self.assertFalse(button.name.property("small"))
        theme.apply(APP, "dark", tokens.DEFAULT_ACCENT, "standard")
        self.settle(button)
        self.assertEqual(button._mode, "icon")


if __name__ == "__main__":
    unittest.main()
