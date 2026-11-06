"""The GNOME (Wayland) backend: GNOME's own shortcuts, read from gsettings and pressed with ydotool."""

import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("tests the Linux code (Windows has its own tests)")
from pathlib import Path
from unittest import mock

from numpadctl import actions, desktop
from numpadctl.platform import gnome_desktop, linux_system

GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":1"}
SHORTCUTS = {"switch-to-workspace-left": ["<Super>Page_Up", "<Super><Alt>Left"],
             "switch-to-workspace-right": ["<Super>KP_Next", "<Super>Page_Down"],   # first one can't be pressed
             "switch-to-workspace-1": ["<Super>Home"], "close": ["<Alt>F4"], "toggle-fullscreen": [],
             "move-to-workspace-1": ["<Super><Shift>Home"], "show-desktop": ["<Super>d"], "weird": ["<Super>KP_Next"]}


class KeysTest(unittest.TestCase):
    def test_accelerators_become_key_names(self):
        for accelerator, expected in (("<Super>Page_Up", ["LEFTMETA", "PAGEUP"]), ("<Alt>F4", ["LEFTALT", "F4"]),
                                      ("<Control><Alt>Left", ["LEFTCTRL", "LEFTALT", "LEFT"]),
                                      ("<Primary><Shift>t", ["LEFTCTRL", "LEFTSHIFT", "T"]),
                                      ("<Super>Home", ["LEFTMETA", "HOME"]), ("<Super>1", ["LEFTMETA", "1"]),
                                      ("<Mod4>space", ["LEFTMETA", "SPACE"])):
            with self.subTest(accelerator):
                self.assertEqual(gnome_desktop.keys_for(accelerator), expected)

    def test_what_cannot_be_pressed_is_none(self):
        for accelerator in ("<Super>KP_Next", "<Hyper>x", "<Super", "XF86AudioPlay", "<Super>"):
            with self.subTest(accelerator):
                self.assertIsNone(gnome_desktop.keys_for(accelerator))


class GnomeTest(unittest.TestCase):
    def setUp(self):
        self.pressed = []
        patches = [mock.patch.dict(desktop.os.environ, GNOME_ENV, clear=True),
                   mock.patch.object(gnome_desktop, "_gsettings", lambda key: SHORTCUTS.get(key, [])),
                   mock.patch.object(linux_system, "press_keys", lambda combos: self.pressed.extend(combos))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def act(self, action, **params):
        return actions.run({"feedback": False}, {"action": action, "params": params})

    def test_detection(self):
        self.assertEqual(desktop.current(), "gnome")
        with mock.patch.dict(desktop.os.environ, {"XDG_CURRENT_DESKTOP": "GNOME", "DISPLAY": ":0"}, clear=True):
            self.assertEqual(desktop.current(), "x11", "GNOME on Xorg uses the X11 calls")
        with mock.patch.dict(desktop.os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "WAYLAND_DISPLAY": "w"}, clear=True):
            self.assertEqual(desktop.current(), "gnome")

    def test_next_and_previous_workspace_press_the_users_shortcuts(self):
        self.act("hypr_next_workspace")
        self.act("hypr_prev_workspace")
        self.assertEqual(self.pressed, [["LEFTMETA", "PAGEDOWN"], ["LEFTMETA", "PAGEUP"]],
                         "the first shortcut that can be pressed (not the keypad one)")

    def test_close_and_workspace_n_use_their_shortcuts(self):
        self.act("hypr_close")
        self.act("hypr_workspace", workspace="1")
        self.act("hypr_move_to_workspace", workspace="1")
        self.assertEqual(self.pressed, [["LEFTALT", "F4"], ["LEFTMETA", "HOME"], ["LEFTMETA", "LEFTSHIFT", "HOME"]])

    def test_a_shortcut_that_is_not_set_says_where_to_set_it(self):
        for action, params, words in (("hypr_fullscreen", {}, "Toggle fullscreen"),
                                      ("hypr_workspace", {"workspace": "3"}, "workspace 3")):
            with self.subTest(action), self.assertRaisesRegex(actions.ActionError, f"no shortcut set.*{words}"):
                self.act(action, **params)
        self.assertEqual(self.pressed, [])

    def test_a_shortcut_that_cannot_be_pressed_says_so(self):
        with mock.patch.dict(SHORTCUTS, {"close": ["<Super>KP_Next"]}):
            with self.assertRaisesRegex(actions.ActionError, "can be pressed from here"):
                self.act("hypr_close")

    def test_show_desktop_is_pressed_again_to_bring_the_windows_back(self):
        token = desktop.hide_windows()
        desktop.restore_windows(token)
        self.assertEqual(self.pressed, [["LEFTMETA", "D"], ["LEFTMETA", "D"]])

    def test_what_gnome_does_not_allow_says_so(self):
        self.assertEqual(actions.active_window_class(), "")
        self.assertEqual(desktop.open_windows(), [])
        for action, params, words in (("focus_window", {"window": "firefox"}, "focus a window by name"),
                                      ("hypr_float", {}, "only works? on Hyprland")):
            with self.subTest(action), self.assertRaisesRegex(actions.ActionError, words):
                self.act(action, **params)
        with self.assertRaisesRegex(desktop.DesktopError, "can't be force-quit"):
            desktop.force_close_window()


class GnomeToolsTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(desktop.os.environ, GNOME_ENV, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.calls = []

    def fake_run(self, answers=None):
        def run(argv, timeout=5):
            self.calls.append(argv)
            return mock.Mock(returncode=0, stdout=(answers or {}).get(argv[1], ""), stderr="")
        return mock.patch.object(desktop, "_run", run)

    def test_do_not_disturb_flips_gnomes_show_banners(self):
        with self.fake_run({"get": "true"}):
            self.assertTrue(desktop.toggle_dnd(), "banners were on: do-not-disturb is on now")
        self.assertEqual(self.calls[-1][-2:], ["show-banners", "false"])
        with self.fake_run({"get": "false"}):
            self.assertFalse(desktop.toggle_dnd())
        self.assertEqual(self.calls[-1][-2:], ["show-banners", "true"])

    def test_screenshots_only_use_tools_that_work_on_gnome(self):
        path = mock.MagicMock(spec=Path)
        path.exists.return_value = True
        path.__str__ = lambda self: "/tmp/shot.png"
        which = lambda name: f"/usr/bin/{name}" if name in ("maim", "gnome-screenshot") else None   # noqa: E731
        with mock.patch.object(desktop.shutil, "which", which), self.fake_run():
            desktop.screenshot(path, region=True)
        self.assertEqual(self.calls, [["gnome-screenshot", "-a", "-f", "/tmp/shot.png"]], "not maim: that is X11 only")
        with mock.patch.object(desktop.shutil, "which", lambda name: None), \
                self.assertRaisesRegex(desktop.DesktopError, "install gnome-screenshot"):
            desktop.screenshot(path)


if __name__ == "__main__":
    unittest.main()
