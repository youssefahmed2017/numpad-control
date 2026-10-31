"""Privacy panic and force-quit: what they do, what they never do, and what happens when a step fails."""

import json
import os
import signal
import sys
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
        import tempfile
        from pathlib import Path
        self.state = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.state, ignore_errors=True))
        self.muted = {True: False, False: False}  # {microphone?: muted now}
        self.playing = True

        def set_mute(mic, muted):
            self.calls.append(("mute", mic, muted))
            self.muted[mic] = muted

        def media(command):
            self.calls.append(("media", command))
            self.playing = command == "play"

        def hide():
            self.calls.append(("hide",))
            return {"workspace": 3}
        patches = [
            mock.patch.object(actions.paths, "state_dir", lambda: self.state),
            mock.patch.object(actions.system, "set_mute", set_mute),
            mock.patch.object(actions.system, "is_muted", lambda mic: self.muted[mic]),
            mock.patch.object(actions.system, "media", media),
            mock.patch.object(actions.system, "media_playing", lambda: self.playing),
            mock.patch.object(actions.desktop, "hide_windows", hide),
            mock.patch.object(actions.desktop, "restore_windows", lambda token: self.calls.append(("restore", token))),
            mock.patch.object(actions.desktop, "lock_screen", lambda: self.calls.append(("lock",))),
            mock.patch.object(actions.obs, "source_visible", lambda s, scene, source: True),
            mock.patch.object(actions.obs, "hide_source", lambda s, scene, source: self.calls.append(("obs", scene, source))),
            mock.patch.object(actions.obs, "show_source", lambda s, scene, source: self.calls.append(("obs-show", scene, source))),
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

    def undo(self):
        return actions.perform(CFG, {"action": "privacy_restore", "params": {}})

    def test_undo_puts_back_exactly_what_the_panic_changed(self):
        panic(scene="Cam", source="Webcam")
        self.calls.clear()
        result = self.undo()
        self.assertEqual(self.calls, [("mute", True, False), ("mute", False, False), ("restore", {"workspace": 3}),
                                      ("obs-show", "Cam", "Webcam"), ("media", "play")])
        for part in ("Microphone unmuted", "speakers unmuted", "windows back", "OBS source shown", "media playing"):
            self.assertIn(part, result)

    def test_something_that_was_already_off_is_left_off(self):
        self.muted[True] = True    # the microphone was already muted
        self.playing = False       # nothing was playing
        panic()
        self.calls.clear()
        self.undo()
        self.assertEqual(self.calls, [("mute", False, False), ("restore", {"workspace": 3})],
                         "no un-muting a microphone you had muted yourself, no starting music")

    def test_a_second_panic_does_not_forget_what_the_first_one_changed(self):
        panic()
        panic()  # everything is already off now: it would "remember" that nothing needs undoing
        self.calls.clear()
        self.undo()
        self.assertIn(("mute", True, False), self.calls)
        self.assertIn(("mute", False, False), self.calls)

    def test_undo_twice_or_without_a_panic_does_nothing(self):
        self.assertEqual(self.undo(), "Nothing to undo")
        panic()
        self.undo()
        self.calls.clear()
        self.assertEqual(self.undo(), "Nothing to undo")
        self.assertEqual(self.calls, [])

    def test_undo_survives_the_service_restarting(self):
        panic()
        self.assertTrue((self.state / "privacy-panic.json").exists(), "it is remembered on disk, not just in memory")
        self.assertIn("unmuted", self.undo())

    def test_if_it_cannot_tell_what_it_was_before_it_still_panics_and_just_does_not_undo_that(self):
        with mock.patch.object(actions.system, "is_muted", side_effect=OSError("no wpctl")):
            panic(media=False, windows=False)
        self.calls.clear()
        self.assertEqual(self.undo(), "Nothing to undo")  # nothing was recorded, so there is nothing to put back
        self.assertEqual(self.calls, [])

    def test_a_failed_undo_step_does_not_stop_the_others(self):
        panic()
        self.calls.clear()
        with mock.patch.object(actions.system, "set_mute", side_effect=OSError("no audio")):
            result = self.undo()
        self.assertIn("indows back", result)
        self.assertIn("Failed: microphone unmuted (no audio)", result)

    def test_it_is_a_one_press_action_that_can_be_a_macro_step(self):
        self.assertFalse(actions.BY_ID["privacy_restore"].confirm)
        self.assertIn("privacy_restore", actions.STEP_IDS)

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


@unittest.skipIf(sys.platform == "win32", "Linux only: Hyprland and KDE")
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


@unittest.skipIf(sys.platform == "win32", "Linux only: Hyprland and KDE")
class HideWindowsTest(unittest.TestCase):
    def test_hyprland_goes_to_an_empty_workspace_and_comes_back_to_the_one_it_left(self):
        reply = mock.Mock(stdout='{"id": 3}')
        with mock.patch.multiple(desktop, current=lambda: desktop.HYPRLAND, _run=lambda argv, timeout=5: reply), \
                mock.patch.object(desktop, "_hyprctl") as hyprctl:
            token = desktop.hide_windows()
            self.assertEqual(token, {"workspace": 3})
            hyprctl.assert_called_once_with('hl.dsp.focus({ workspace = "empty" })')
            hyprctl.reset_mock()
            desktop.restore_windows(json.loads(json.dumps(token)))  # the token goes through a file in between
            hyprctl.assert_called_once_with("hl.dsp.focus({ workspace = 3 })")

    def test_kde_minimises_every_window_and_activates_them_again(self):
        calls = []

        def kdotool(*args):
            calls.append(args)
            return "w1 w2" if args[0] == "search" else ""
        with mock.patch.multiple(desktop, current=lambda: desktop.KDE), mock.patch.object(desktop, "_kdotool", kdotool):
            token = desktop.hide_windows()
            self.assertEqual(token, {"windows": ["w1", "w2"]})
            self.assertEqual(calls[1:], [("windowminimize", "w1"), ("windowminimize", "w2")])
            calls.clear()
            desktop.restore_windows(token)
        self.assertEqual(calls, [("windowactivate", "w1"), ("windowactivate", "w2")])


class MuteAndPauseTest(unittest.TestCase):
    def test_set_mute_is_explicit_not_a_toggle(self):
        with mock.patch.object(linux_system, "_run") as run:
            linux_system.set_mute(True, True)
            linux_system.set_mute(False, False)
        self.assertEqual(run.call_args_list, [mock.call("wpctl", "set-mute", linux_system.SOURCE, "1"),
                                              mock.call("wpctl", "set-mute", linux_system.SINK, "0")])

    def test_it_can_tell_whether_something_is_muted_or_playing(self):
        with mock.patch.object(linux_system, "_run", return_value=mock.Mock(stdout="Volume: 0.60 [MUTED]\n")):
            self.assertTrue(linux_system.is_muted(False))
        with mock.patch.object(linux_system, "_run", return_value=mock.Mock(stdout="Volume: 1.00\n")):
            self.assertFalse(linux_system.is_muted(True))
        with mock.patch.object(linux_system.shutil, "which", lambda n: "/usr/bin/playerctl"), \
                mock.patch.object(linux_system.subprocess, "run", return_value=mock.Mock(stdout="Playing\n")):
            self.assertTrue(linux_system.media_playing())
        with mock.patch.object(linux_system.shutil, "which", lambda n: "/usr/bin/playerctl"), \
                mock.patch.object(linux_system.subprocess, "run", return_value=mock.Mock(stdout="Paused\n")):
            self.assertFalse(linux_system.media_playing())
        with mock.patch.object(linux_system.shutil, "which", lambda n: None):
            self.assertFalse(linux_system.media_playing(), "no player program: nothing is playing as far as we can tell")

    def test_play_resumes_with_playerctl(self):
        with mock.patch.object(linux_system, "_run") as run, mock.patch.object(linux_system, "_swayosd") as osd:
            linux_system.media("play")
        run.assert_called_once_with("playerctl", "play")
        osd.assert_not_called()

    def test_pause_asks_playerctl_for_pause_not_play_pause(self):
        with mock.patch.object(linux_system, "_run") as run, mock.patch.object(linux_system, "_swayosd") as osd:
            linux_system.media("pause")
        run.assert_called_once_with("playerctl", "pause")
        osd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
