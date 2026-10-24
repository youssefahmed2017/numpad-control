import unittest
from unittest import mock

from evdev import ecodes

from numpadctl import actions


def step(action, **params):
    return {"action": action, "params": params}


class KeyboardTest(unittest.TestCase):
    def test_parse_combos_and_sequences(self):
        self.assertEqual(actions.parse_keys("ctrl+shift+t"),
                         [[ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT, ecodes.KEY_T]])
        self.assertEqual(actions.parse_keys("Down down, Enter"),
                         [[ecodes.KEY_DOWN], [ecodes.KEY_DOWN], [ecodes.KEY_ENTER]])
        self.assertEqual(actions.parse_keys("super+Return F5"),
                         [[ecodes.KEY_LEFTMETA, ecodes.KEY_ENTER], [ecodes.KEY_F5]])

    def test_spaces_around_plus_still_mean_together(self):
        together = [[ecodes.KEY_LEFTMETA, ecodes.KEY_Q]]
        for text in ("super+q", "Super + Q", "SUPER +q", "  super+ Q "):
            with self.subTest(text):
                self.assertEqual(actions.parse_keys(text), together)
        self.assertEqual(actions.parse_keys("Super + Q Enter"), together + [[ecodes.KEY_ENTER]])

    def test_bad_keys(self):
        for text in ("", "ctrl+", "notakey", "ctrl++c"):
            with self.subTest(text):
                with self.assertRaises(actions.ActionError):
                    actions.parse_keys(text)

    def test_press_keys_holds_then_releases_in_reverse(self):
        with mock.patch.object(actions, "_ydotool") as ydotool:
            actions.run({}, step("press_keys", keys="ctrl+c Enter"))
        c, ctrl, enter = ecodes.KEY_C, ecodes.KEY_LEFTCTRL, ecodes.KEY_ENTER
        ydotool.assert_called_once_with(
            "key", f"{ctrl}:1", f"{c}:1", f"{c}:0", f"{ctrl}:0", f"{enter}:1", f"{enter}:0")

    def test_type_text_goes_through_stdin_literally(self):
        with mock.patch.object(actions, "_ydotool") as ydotool:
            actions.run({}, step("type_text", text="-r claude \\n $HOME"))
        ydotool.assert_called_once_with("type", "--escape", "0", "--file", "-",
                                        stdin="-r claude \\n $HOME")

    def test_window_class_cannot_inject_lua(self):
        for bad in ('kitty" }) hl.dsp.exit() --', "", "a b"):
            with self.subTest(bad):
                with self.assertRaises(actions.ActionError):
                    actions._window_class(bad)
        self.assertEqual(actions._window_class(" org.kde.dolphin "), "org.kde.dolphin")

    def test_wait_for_window(self):
        classes = iter(["firefox", "firefox", "kitty"])
        with mock.patch.object(actions, "active_window_class", lambda: next(classes)), \
                mock.patch.object(actions.time, "sleep"):
            actions.run({}, step("wait_for_window", window="Kitty", seconds="5"))

    def test_wait_for_window_gives_up(self):
        with mock.patch.object(actions, "active_window_class", return_value="firefox"):
            with self.assertRaisesRegex(actions.ActionError, "no kitty window"):
                actions.run({}, step("wait_for_window", window="kitty", seconds="0.2"))

    def test_problems_are_found_before_running(self):
        self.assertEqual(actions.binding_problems(step("press_keys", keys="ctrl+c")), [])
        self.assertTrue(actions.binding_problems(step("press_keys", keys="ctrl+banana")))
        self.assertTrue(actions.binding_problems(step("type_text", text="")))
        self.assertTrue(actions.binding_problems(step("focus_window", window="a; b")))
        macro = step("macro", steps=[step("launch_app", app="kitty.desktop"),
                                     step("wait_for_window", window="kitty", seconds="10"),
                                     step("press_keys", keys="Dwn")])
        self.assertEqual(len(actions.binding_problems(macro)), 1)
        self.assertIn("step 3", actions.binding_problems(macro)[0])


if __name__ == "__main__":
    unittest.main()


class SessionEnvTest(unittest.TestCase):
    def test_display_vars_are_picked_up_from_systemd(self):
        out = mock.Mock(stdout="HOME=/home/x\nWAYLAND_DISPLAY=wayland-9\nHYPRLAND_INSTANCE_SIGNATURE=abc\nPATH=/bin\n")
        with mock.patch.dict(actions.os.environ, {}, clear=True), \
                mock.patch.object(actions.subprocess, "run", return_value=out):
            self.assertTrue(actions.refresh_session_env())
            self.assertEqual(actions.os.environ["WAYLAND_DISPLAY"], "wayland-9")
            self.assertEqual(actions.os.environ["HYPRLAND_INSTANCE_SIGNATURE"], "abc")
            self.assertNotIn("PATH", actions.os.environ, "only display variables are copied")

    def test_no_session_yet(self):
        with mock.patch.dict(actions.os.environ, {}, clear=True), \
                mock.patch.object(actions.subprocess, "run", return_value=mock.Mock(stdout="HOME=/x\n")):
            self.assertFalse(actions.refresh_session_env())
