"""The X11 desktop backend (XFCE, Cinnamon, MATE, i3...): window and workspace actions through EWMH.

The X server is replaced by a fake that records the client messages the window manager would get."""

import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("tests the Linux code (Windows has its own tests)")
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from numpadctl import actions, desktop
from numpadctl.platform import x11_desktop

X11_ENV = {"XDG_CURRENT_DESKTOP": "XFCE", "DISPLAY": ":0"}
SUPPORTED = {"_NET_ACTIVE_WINDOW", "_NET_CLOSE_WINDOW", "_NET_CURRENT_DESKTOP", "_NET_WM_DESKTOP",
             "_NET_WM_STATE_FULLSCREEN", "_NET_SHOWING_DESKTOP"}


class Win:
    def __init__(self, instance, cls, title="", pid=0, kind="normal"):
        self.instance, self.cls, self.title, self.pid, self.kind = instance, cls, title, pid, kind


class FakeX:
    """What _Session offers, over a few made-up windows."""

    def __init__(self, windows, active=None, desktops=4, current=0, supported=SUPPORTED, showing=0):
        self.windows, self.active_window, self.sent = windows, active, []
        self.root = Win("", "", kind="root")
        self.values = {"_NET_NUMBER_OF_DESKTOPS": [desktops], "_NET_CURRENT_DESKTOP": [current],
                       "_NET_SHOWING_DESKTOP": [showing]}
        self.supported = set(supported)

    def prop(self, window, name):
        return self.values.get(name, [])

    def atom(self, name):
        return name

    def supports(self, name):
        return name in self.supported

    def need(self, name, what):
        if name not in self.supported:
            raise desktop.DesktopError(f"{what} isn't supported by this window manager")

    def send(self, window, name, data):
        self.sent.append((window, name, list(data)))

    def active(self):
        return self.active_window

    def clients(self):
        return self.windows

    def is_app_window(self, window):
        return window.kind == "normal"

    def wm_class(self, window):
        return (window.instance, window.cls)

    def title(self, window):
        return window.title

    def pid(self, window):
        return window.pid


class X11Test(unittest.TestCase):
    def setUp(self):
        self.term = Win("kitty", "kitty", "shell", pid=4001)
        self.fox = Win("Navigator", "Firefox", "Mozilla Firefox", pid=4002)
        self.panel = Win("xfce4-panel", "Xfce4-panel", "panel", pid=4003, kind="dock")
        self.desk = Win("xfdesktop", "Xfdesktop", "Desktop", pid=4004, kind="desktop")
        self.x = FakeX([self.panel, self.desk, self.term, self.fox], active=self.term)
        self.env = mock.patch.dict(desktop.os.environ, X11_ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

        @contextmanager
        def session():
            yield self.x
        patch = mock.patch.object(x11_desktop, "_x", session)
        patch.start()
        self.addCleanup(patch.stop)

    def act(self, action, **params):
        return actions.run({"feedback": False}, {"action": action, "params": params})

    # ---------------------------------------------------------------- detection
    def test_detection(self):
        cases = ((X11_ENV, "x11"), ({"XDG_CURRENT_DESKTOP": "GNOME", "DISPLAY": ":0"}, "x11"),
                 ({"XDG_CURRENT_DESKTOP": "GNOME", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}, "other"),
                 ({"XDG_CURRENT_DESKTOP": "Hyprland", "DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-1"}, "hyprland"),
                 ({"XDG_CURRENT_DESKTOP": "KDE", "DISPLAY": ":0"}, "kde"),
                 ({"XDG_CURRENT_DESKTOP": "XFCE"}, "other"))
        for env, expected in cases:
            with self.subTest(env), mock.patch.dict(desktop.os.environ, env, clear=True):
                self.assertEqual(desktop.current(), expected)

    # ---------------------------------------------------------------- windows
    def test_the_focused_windows_class_is_what_profiles_match(self):
        self.assertEqual(actions.active_window_class(), "kitty")
        self.x.active_window = self.fox
        self.assertEqual(actions.active_window_class(), "Firefox")
        self.x.active_window = None
        self.assertEqual(actions.active_window_class(), "")

    def test_the_window_list_leaves_out_the_panel_and_the_desktop(self):
        self.assertEqual(desktop.open_windows(), [("kitty", "shell"), ("Firefox", "Mozilla Firefox")])

    def test_focus_a_window_ignores_case_and_says_when_it_is_not_open(self):
        self.act("focus_window", window="firefox")
        self.assertEqual(self.x.sent, [(self.fox, "_NET_ACTIVE_WINDOW", [2, 0, 0])])
        with self.assertRaisesRegex(actions.ActionError, "no obs window is open"):
            self.act("focus_window", window="obs")
        with self.assertRaisesRegex(actions.ActionError, "no xfce4-panel window is open"):
            self.act("focus_window", window="xfce4-panel")   # the panel is not a program to focus

    def test_close_and_fullscreen_go_to_the_focused_window(self):
        self.act("hypr_close")
        self.act("hypr_fullscreen")
        self.assertEqual(self.x.sent, [(self.term, "_NET_CLOSE_WINDOW", [0, 2]),
                                       (self.term, "_NET_WM_STATE", [2, "_NET_WM_STATE_FULLSCREEN", 0, 2])])

    def test_the_desktop_itself_is_not_closed(self):
        self.x.active_window = self.desk
        for action in ("hypr_close", "hypr_fullscreen"):
            with self.subTest(action), self.assertRaisesRegex(actions.ActionError, "desktop itself"):
                self.act(action)
        self.assertEqual(self.x.sent, [])

    def test_floating_and_scratchpad_are_hyprland_only(self):
        for action in ("hypr_float", "hypr_scratchpad"):
            with self.subTest(action), self.assertRaisesRegex(actions.ActionError, "only works? on Hyprland"):
                self.act(action)

    # ---------------------------------------------------------------- workspaces
    def test_workspaces_count_from_one(self):
        self.act("hypr_workspace", workspace="3")
        self.act("hypr_move_to_workspace", workspace="2")
        self.assertEqual(self.x.sent, [(self.x.root, "_NET_CURRENT_DESKTOP", [2, 0]),
                                       (self.term, "_NET_WM_DESKTOP", [1, 2])])

    def test_a_workspace_that_does_not_exist_says_how_many_there_are(self):
        with self.assertRaisesRegex(actions.ActionError, "you have 4 workspaces"):
            self.act("hypr_workspace", workspace="5")
        self.assertEqual(self.x.sent, [])

    def test_next_and_previous_wrap_around(self):
        self.x.values["_NET_CURRENT_DESKTOP"] = [3]
        self.act("hypr_next_workspace")
        self.x.values["_NET_CURRENT_DESKTOP"] = [0]
        self.act("hypr_prev_workspace")
        self.assertEqual([m[2][0] for m in self.x.sent], [0, 3])

    def test_a_window_manager_without_support_says_so(self):
        self.x.supported = set()
        for action, params in (("hypr_workspace", {"workspace": "2"}), ("hypr_close", {}), ("hypr_fullscreen", {})):
            with self.subTest(action), self.assertRaisesRegex(actions.ActionError, "isn't supported by this window manager"):
                self.act(action, **params)

    # ---------------------------------------------------------------- hide windows, force quit
    def test_hiding_shows_the_desktop_and_restoring_brings_the_windows_back(self):
        token = desktop.hide_windows()
        self.assertEqual(self.x.sent[-1][1:], ("_NET_SHOWING_DESKTOP", [1]))
        desktop.restore_windows(token)
        self.assertEqual(self.x.sent[-1][1:], ("_NET_SHOWING_DESKTOP", [0]))

    def test_restoring_leaves_a_desktop_that_was_already_showing_alone(self):
        self.x.values["_NET_SHOWING_DESKTOP"] = [1]
        token = desktop.hide_windows()
        before = len(self.x.sent)
        desktop.restore_windows(token)
        self.assertEqual(len(self.x.sent), before)

    def test_force_quit_kills_the_focused_programs_process(self):
        self.x.active_window = self.fox
        with mock.patch.object(x11_desktop.os, "kill") as kill:
            self.assertEqual(desktop.force_close_window(), "Firefox")
        kill.assert_called_once_with(4002, x11_desktop.signal.SIGKILL)

    def test_the_desktop_and_numpadcontrol_itself_are_never_force_quit(self):
        with mock.patch.object(x11_desktop.os, "kill") as kill:
            for window in (self.panel, self.desk):
                self.x.active_window = window
                with self.subTest(window.cls), self.assertRaisesRegex(desktop.DesktopError, "protected"):
                    desktop.force_close_window()
            self.x.active_window = Win("x", "x", pid=x11_desktop.os.getpid())
            with self.assertRaisesRegex(desktop.DesktopError, "protected"):
                desktop.force_close_window()
            self.x.active_window = Win("x", "x", pid=0)
            with self.assertRaises(desktop.DesktopError):
                desktop.force_close_window()
        kill.assert_not_called()


class X11ToolsTest(unittest.TestCase):
    """Screenshots, do-not-disturb and locking on X11 (the programs are faked)."""

    def setUp(self):
        env = mock.patch.dict(desktop.os.environ, X11_ENV, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.calls = []

    def fake_run(self, answers=None):
        def run(argv, timeout=5):
            self.calls.append(argv)
            return mock.Mock(returncode=0, stdout=(answers or {}).get(argv[0], ""), stderr="")
        return mock.patch.object(desktop, "_run", run)

    def installed(self, *programs):
        return mock.patch.object(desktop.shutil, "which", lambda name: f"/usr/bin/{name}" if name in programs else None)

    def test_a_screenshot_uses_the_first_tool_that_is_installed(self):
        path = mock.MagicMock(spec=Path)
        path.exists.return_value = True
        path.__str__ = lambda self: "/tmp/shot.png"
        with self.installed("scrot", "xfce4-screenshooter"), self.fake_run():
            self.assertTrue(desktop.screenshot(path))
            desktop.screenshot(path, region=True)
        self.assertEqual(self.calls, [["scrot", "/tmp/shot.png"], ["scrot", "-s", "/tmp/shot.png"]])

    def test_xfce_screenshooter_and_the_missing_tool_message(self):
        path = mock.MagicMock(spec=Path)
        path.exists.return_value = True
        path.__str__ = lambda self: "/tmp/shot.png"
        with self.installed("xfce4-screenshooter"), self.fake_run():
            desktop.screenshot(path, region=True)
        self.assertEqual(self.calls, [["xfce4-screenshooter", "-r", "-s", "/tmp/shot.png"]])
        with self.installed(), self.assertRaisesRegex(desktop.DesktopError, "no screenshot tool found"):
            desktop.screenshot(path)

    def test_do_not_disturb_on_xfce_flips_the_notification_daemons_setting(self):
        answers = {"xfconf-query": "false"}
        with self.installed("xfconf-query"), self.fake_run(answers), \
                mock.patch.object(desktop, "_running", lambda program: False):
            self.assertTrue(desktop.toggle_dnd())
        self.assertEqual(self.calls[-1][-2:], ["-s", "true"])
        with self.installed("xfconf-query"), self.fake_run({"xfconf-query": "true"}), \
                mock.patch.object(desktop, "_running", lambda program: False):
            self.assertFalse(desktop.toggle_dnd())

    def test_a_running_dunst_is_used_even_on_xfce(self):
        with self.installed("xfconf-query", "dunstctl"), self.fake_run({"dunstctl": "true"}), \
                mock.patch.object(desktop, "_running", lambda program: program == "dunst"):
            self.assertTrue(desktop.toggle_dnd())
        self.assertEqual(self.calls[0], ["dunstctl", "set-paused", "toggle"])

    def test_lock_uses_xflock4_when_it_is_there(self):
        with self.installed("xflock4"), mock.patch.object(desktop.subprocess, "Popen") as popen:
            desktop.lock_screen()
        self.assertEqual(popen.call_args.args[0], ["xflock4"])
        with self.installed(), self.fake_run():
            desktop.lock_screen()
        self.assertEqual(self.calls, [["loginctl", "lock-session"]])


class SameFunctionsTest(unittest.TestCase):
    def test_the_x11_backend_offers_what_the_windows_one_does(self):
        if sys.platform == "win32":
            self.skipTest("Linux only")
        wanted = {"active_window_class", "open_windows", "focus_window", "close_window", "toggle_fullscreen",
                  "toggle_floating", "toggle_scratchpad", "go_to_workspace", "move_window_to_workspace",
                  "step_workspace", "focus_app_window", "hide_windows", "restore_windows", "force_close_window"}
        self.assertEqual({name for name in wanted if hasattr(x11_desktop, name)}, wanted)


if __name__ == "__main__":
    unittest.main()
