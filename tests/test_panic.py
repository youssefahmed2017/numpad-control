"""Privacy panic and force-quit: what they do, what they never do, and what happens when a step fails."""

import json
import os
import signal
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import actions, config, desktop  # noqa: E402
from numpadctl.platform import linux_system  # noqa: E402

CFG = {**config.DEFAULT_CONFIG, "feedback": False}


def panic(**params):
    return actions.perform(CFG, {"action": "privacy_panic", "params": params})


class PrivacyPanicTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        patches = [
            mock.patch.object(actions.system, "set_mute", lambda mic, muted: self.calls.append(("mute", mic, muted))),
            mock.patch.object(actions.system, "media", lambda command: self.calls.append(("media", command))),
            mock.patch.object(actions.desktop, "hide_windows", lambda: self.calls.append(("hide",))),
            mock.patch.object(actions.desktop, "lock_screen", lambda: self.calls.append(("lock",))),
            mock.patch.object(actions.obs, "hide_source", lambda s, scene, source: self.calls.append(("obs", scene, source))),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_defaults_mute_pause_and_hide_but_do_not_lock(self):
        result = panic()
        self.assertEqual(self.calls, [("mute", True, True), ("mute", False, True), ("media", "pause"), ("hide",)])
        self.assertIn("Microphone muted", result)
        self.assertIn("windows hidden", result)

    def test_each_checkbox_switches_its_step_off(self):
        panic(mic=False, speakers=False, media=False, windows=False, lock=True)
        self.assertEqual(self.calls, [("lock",)])

    def test_text_from_a_hand_edited_file_counts_as_a_checkbox(self):
        panic(mic="false", speakers="no", media="0", windows="off", lock="yes")
        self.assertEqual(self.calls, [("lock",)])

    def test_obs_only_when_both_the_scene_and_the_source_are_named(self):
        panic(scene="Cam")
        self.assertNotIn("obs", [c[0] for c in self.calls])
        panic(scene="Cam", source="Webcam")
        self.assertEqual(self.calls[-1], ("obs", "Cam", "Webcam"), "and after the instant steps")

    def test_one_step_failing_does_not_stop_the_others(self):
        def boom(mic, muted):
            if mic:
                raise OSError("no microphone")
            self.calls.append(("mute", mic, muted))
        with mock.patch.object(actions.system, "set_mute", boom):
            result = panic()
        self.assertEqual(self.calls, [("mute", False, True), ("media", "pause"), ("hide",)])
        self.assertIn("Failed: microphone muted (no microphone)", result)

    def test_when_everything_fails_it_says_why(self):
        with mock.patch.object(actions.system, "set_mute", side_effect=OSError("no audio")), \
                mock.patch.object(actions.system, "media", side_effect=OSError("no player")), \
                mock.patch.object(actions.desktop, "hide_windows", side_effect=OSError("no desktop")):
            with self.assertRaises(actions.ActionError) as caught:
                panic()
        self.assertIn("no audio", str(caught.exception))
        self.assertIn("no desktop", str(caught.exception))

    def test_it_is_a_normal_one_press_action_with_checkbox_settings(self):
        action = actions.BY_ID["privacy_panic"]
        self.assertFalse(action.confirm, "a panic button cannot ask twice")
        self.assertIn("privacy_panic", actions.STEP_IDS, "it can be a step in a macro")
        self.assertEqual([p.kind for p in action.params].count("bool"), 5)


class ForceQuitTest(unittest.TestCase):
    def setUp(self):
        actions._armed.clear()
        self.killed, self.opened = [], []
        self.clock = [100.0]
        patches = [
            mock.patch.object(actions.desktop, "force_close_window", lambda: self.killed.append("x") or "firefox"),
            mock.patch.object(actions, "_open_browser", lambda cfg, url="": self.opened.append(url)),
            mock.patch.object(actions.time, "monotonic", lambda: self.clock[0]),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def press(self, **params):
        return actions.perform(CFG, {"action": "force_quit", "params": params})

    def test_the_first_press_only_asks(self):
        self.assertIsNone(self.press(url="https://example.com"))
        self.assertEqual((self.killed, self.opened), ([], []))

    def test_the_second_press_kills_and_then_opens_the_page(self):
        self.press(url="https://example.com")
        self.clock[0] += 1.0
        self.assertEqual(self.press(url="https://example.com"), "Force-quit firefox")
        self.assertEqual((self.killed, self.opened), (["x"], ["https://example.com"]))

    def test_a_bounce_or_a_slow_second_press_does_not_count(self):
        self.press()
        self.clock[0] += 0.1  # a bounce
        self.press()
        self.assertEqual(self.killed, [])
        self.clock[0] += 30  # much later: it only asks again
        self.press()
        self.assertEqual(self.killed, [])

    def test_no_page_means_no_browser(self):
        self.press()
        self.clock[0] += 1.0
        self.press()
        self.assertEqual(self.opened, [])

    def test_it_is_never_part_of_a_macro_or_a_test_run(self):
        self.assertTrue(actions.BY_ID["force_quit"].confirm)
        self.assertNotIn("force_quit", actions.STEP_IDS)


class ForceCloseWindowTest(unittest.TestCase):
    def window(self, cls, pid):
        reply = mock.Mock(stdout=json.dumps({"class": cls, "pid": pid}))
        return mock.patch.multiple(desktop, current=lambda: desktop.HYPRLAND, _run=lambda argv, timeout=5: reply)

    def test_it_kills_the_program_of_the_focused_window(self):
        with self.window("firefox", 4242), mock.patch.object(desktop.os, "kill") as kill:
            self.assertEqual(desktop.force_close_window(), "firefox")
        kill.assert_called_once_with(4242, signal.SIGKILL)

    def test_the_desktop_and_numpadpilot_itself_are_protected(self):
        for cls in ("Hyprland", "plasmashell", "dev.numpadctl.NumpadControl", "waybar"):
            with self.window(cls, 4242), mock.patch.object(desktop.os, "kill") as kill:
                with self.assertRaises(desktop.DesktopError):
                    desktop.force_close_window()
            kill.assert_not_called()

    def test_this_process_and_pid_1_and_no_window_are_refused(self):
        for pid in (os.getpid(), 1, 0):
            with self.window("firefox", pid), mock.patch.object(desktop.os, "kill") as kill:
                with self.assertRaises(desktop.DesktopError):
                    desktop.force_close_window()
            kill.assert_not_called()


class HideWindowsTest(unittest.TestCase):
    def test_hyprland_goes_to_an_empty_workspace(self):
        with mock.patch.multiple(desktop, current=lambda: desktop.HYPRLAND), \
                mock.patch.object(desktop, "_hyprctl") as hyprctl:
            desktop.hide_windows()
        hyprctl.assert_called_once_with('hl.dsp.focus({ workspace = "empty" })')

    def test_kde_minimises_every_window(self):
        calls = []

        def kdotool(*args):
            calls.append(args)
            return "w1 w2" if args[0] == "search" else ""
        with mock.patch.multiple(desktop, current=lambda: desktop.KDE), mock.patch.object(desktop, "_kdotool", kdotool):
            desktop.hide_windows()
        self.assertEqual(calls[1:], [("windowminimize", "w1"), ("windowminimize", "w2")])


class MuteAndPauseTest(unittest.TestCase):
    def test_set_mute_is_explicit_not_a_toggle(self):
        with mock.patch.object(linux_system, "_run") as run:
            linux_system.set_mute(True, True)
            linux_system.set_mute(False, False)
        self.assertEqual(run.call_args_list, [mock.call("wpctl", "set-mute", linux_system.SOURCE, "1"),
                                              mock.call("wpctl", "set-mute", linux_system.SINK, "0")])

    def test_pause_asks_playerctl_for_pause_not_play_pause(self):
        with mock.patch.object(linux_system, "_run") as run, mock.patch.object(linux_system, "_swayosd") as osd:
            linux_system.media("pause")
        run.assert_called_once_with("playerctl", "pause")
        osd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
