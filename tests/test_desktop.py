import unittest
from types import SimpleNamespace
from unittest import mock

from numpadctl import actions, desktop
from numpadctl.platform import linux_system

HYPR_ENV = {"XDG_CURRENT_DESKTOP": "Hyprland", "HYPRLAND_INSTANCE_SIGNATURE": "abc"}
KDE_ENV = {"XDG_CURRENT_DESKTOP": "KDE"}


class FakeTools:
    """Records hyprctl / kdotool calls and answers like the real tools."""

    def __init__(self, desktops=4, current_desktop=1):
        self.calls = []
        self.desktops, self.current_desktop = desktops, current_desktop

    def __call__(self, argv, timeout=5):
        self.calls.append(argv)
        out = ""
        if argv[:2] == ["hyprctl", "dispatch"]:
            out = "ok"
        elif argv[:3] == ["hyprctl", "activewindow", "-j"]:
            out = '{"class": "firefox"}'
        elif argv[0] == "kdotool":
            args = argv[1:]
            if args == ["get_num_desktops"]:
                out = str(self.desktops)
            elif args == ["get_desktop"]:
                out = str(self.current_desktop)
            elif args[:1] == ["search"]:
                out = "{win-1}" if "kitty" in args[-1] else ""
            elif args == ["getactivewindow", "getwindowclassname"]:
                out = "org.kde.dolphin"
        return SimpleNamespace(returncode=0, stdout=out + "\n", stderr="")


class DesktopTest(unittest.TestCase):
    def setUp(self):
        self.tools = FakeTools()
        self.patch = mock.patch.object(desktop, "_run", self.tools)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def on(self, env):
        return mock.patch.dict(desktop.os.environ, env, clear=True)

    def run_action(self, action, **params):
        return actions.run({"feedback": False}, {"action": action, "params": params})

    def test_detection(self):
        for env, expected in ((HYPR_ENV, "hyprland"), (KDE_ENV, "kde"),
                              ({"XDG_CURRENT_DESKTOP": "GNOME"}, "other"),
                              ({"HYPRLAND_INSTANCE_SIGNATURE": "x"}, "hyprland")):
            with self.subTest(env), self.on(env):
                self.assertEqual(desktop.current(), expected)

    def test_hyprland_keeps_using_hyprctl(self):
        with self.on(HYPR_ENV):
            self.run_action("hypr_workspace", workspace="3")
            self.run_action("hypr_next_workspace")
            self.run_action("hypr_close")
            self.run_action("focus_window", window="kitty")
            self.assertEqual(actions.active_window_class(), "firefox")
        self.assertEqual([c[2] for c in self.tools.calls if c[:2] == ["hyprctl", "dispatch"]], [
            "hl.dsp.focus({ workspace = 3 })", 'hl.dsp.focus({ workspace = "e+1" })',
            "hl.dsp.window.close()", 'hl.dsp.focus({ window = "class:kitty" })'])

    def test_kde_uses_kdotool(self):
        with self.on(KDE_ENV):
            self.run_action("hypr_workspace", workspace="2")
            self.run_action("hypr_move_to_workspace", workspace="3")
            self.run_action("hypr_close")
            self.run_action("hypr_fullscreen")
            self.run_action("focus_window", window="kitty")
            self.assertEqual(actions.active_window_class(), "org.kde.dolphin")
        kdotool = [c[1:] for c in self.tools.calls if c[0] == "kdotool"]
        self.assertIn(["set_desktop", "2"], kdotool)
        self.assertIn(["getactivewindow", "set_desktop_for_window", "3"], kdotool)
        self.assertIn(["getactivewindow", "windowclose"], kdotool)
        self.assertIn(["getactivewindow", "windowstate", "--toggle", "FULLSCREEN"], kdotool)
        self.assertIn(["search", "--class", "^kitty$"], kdotool)
        self.assertIn(["windowactivate", "{win-1}"], kdotool)

    def test_kde_desktop_steps_wrap_around(self):
        self.tools.current_desktop = 4
        with self.on(KDE_ENV):
            self.run_action("hypr_next_workspace")
        self.assertIn(["kdotool", "set_desktop", "1"], self.tools.calls)

    def test_kde_errors_are_clear(self):
        with self.on(KDE_ENV):
            for action, params, message in (
                    ("hypr_workspace", {"workspace": "7"}, "you have 4 virtual desktops"),
                    ("hypr_float", {}, "only works on Hyprland"),
                    ("hypr_scratchpad", {}, "only works on Hyprland"),
                    ("focus_window", {"window": "obs"}, "no obs window is open")):
                with self.subTest(action), self.assertRaisesRegex(actions.ActionError, message):
                    self.run_action(action, **params)

    def test_class_with_dots_is_matched_exactly(self):
        with self.on(KDE_ENV):
            with self.assertRaises(actions.ActionError):  # fake has no dolphin window
                self.run_action("focus_window", window="org.kde.dolphin")
        self.assertIn(["kdotool", "search", "--class", r"^org\.kde\.dolphin$"], self.tools.calls)

    def test_other_desktops_get_a_clear_message(self):
        with self.on({"XDG_CURRENT_DESKTOP": "GNOME"}):
            with self.assertRaisesRegex(actions.ActionError, "only works on Hyprland or KDE Plasma"):
                self.run_action("hypr_close")


class SessionSwitchTest(unittest.TestCase):
    def test_previous_sessions_variables_are_dropped(self):
        """After logging out of Hyprland and into KDE, the old Hyprland ID must go."""
        systemd = mock.Mock(stdout="WAYLAND_DISPLAY=wayland-0\nXDG_CURRENT_DESKTOP=KDE\nHOME=/h\n")
        stale = {"WAYLAND_DISPLAY": "wayland-1", "XDG_CURRENT_DESKTOP": "Hyprland",
                 "HYPRLAND_INSTANCE_SIGNATURE": "old", "PATH": "/bin"}
        with mock.patch.dict(linux_system.os.environ, stale, clear=True), \
                mock.patch.object(linux_system.subprocess, "run", return_value=systemd):
            actions.refresh_session_env()
            self.assertEqual(linux_system.os.environ["XDG_CURRENT_DESKTOP"], "KDE")
            self.assertEqual(linux_system.os.environ["WAYLAND_DISPLAY"], "wayland-0")
            self.assertNotIn("HYPRLAND_INSTANCE_SIGNATURE", linux_system.os.environ)
            self.assertEqual(linux_system.os.environ["PATH"], "/bin", "unrelated variables are kept")
            self.assertEqual(desktop.current(), "kde")

    def test_nothing_dropped_if_systemd_cannot_be_asked(self):
        with mock.patch.dict(linux_system.os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=True), \
                mock.patch.object(linux_system.subprocess, "run", side_effect=OSError):
            self.assertTrue(actions.refresh_session_env())


if __name__ == "__main__":
    unittest.main()
