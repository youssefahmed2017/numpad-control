"""The soundboard: Play a sound / Stop all sounds."""

import os
import tempfile
import unittest
from unittest import mock

from numpadctl import actions, config
from numpadctl.platform import linux_system as system

CFG = {**config.DEFAULT_CONFIG, "feedback": False}


class FakeProcess:
    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs, self.ended = argv, kwargs, False

    def poll(self):
        return 0 if self.ended else None

    def terminate(self):
        self.ended = True


class PlaySoundTest(unittest.TestCase):
    def setUp(self):
        system._sounds.clear()
        self.addCleanup(system._sounds.clear)
        handle, self.path = tempfile.mkstemp(suffix=".mp3")
        os.close(handle)
        self.addCleanup(os.unlink, self.path)
        self.started = []

        def popen(argv, **kwargs):
            process = FakeProcess(argv, **kwargs)
            self.started.append(process)
            return process
        patch = mock.patch.object(system.subprocess, "Popen", popen)
        patch.start()
        self.addCleanup(patch.stop)

    def installed(self, *names):
        return mock.patch.object(system.shutil, "which", lambda name: f"/usr/bin/{name}" if name in names else None)

    def test_pipewire_first_with_the_volume_as_a_fraction(self):
        with self.installed("pw-play", "paplay", "ffplay"):
            system.play_sound(self.path, 40)
        self.assertEqual(self.started[0].argv, ["pw-play", "--volume", "0.40", self.path])

    def test_paplay_then_ffplay_when_that_is_all_there_is(self):
        with self.installed("paplay", "ffplay"):
            system.play_sound(self.path, 50)
        self.assertEqual(self.started[0].argv, ["paplay", "--volume=32768", self.path])
        with self.installed("ffplay"):
            system.play_sound(self.path, 100)
        self.assertEqual(self.started[1].argv[:2], ["ffplay", "-nodisp"])
        self.assertIn("-autoexit", self.started[1].argv)

    def test_no_player_says_what_to_install(self):
        with self.installed():
            with self.assertRaises(system.SystemActionError) as caught:
                system.play_sound(self.path)
        self.assertIn("pw-play", str(caught.exception))

    def test_a_missing_file_is_an_error_not_silence(self):
        with self.installed("pw-play"):
            with self.assertRaises(system.SystemActionError) as caught:
                system.play_sound("/nonexistent/airhorn.mp3")
        self.assertIn("not found", str(caught.exception))
        self.assertEqual(self.started, [])

    def test_it_returns_at_once_and_sounds_can_overlap(self):
        with self.installed("pw-play"):
            system.play_sound(self.path)
            system.play_sound(self.path)
        self.assertEqual(len(self.started), 2)
        self.assertTrue(self.started[0].kwargs["start_new_session"])

    def test_a_tilde_is_the_home_folder(self):
        with self.installed("pw-play"), mock.patch.object(system.os.path, "isfile", lambda p: True):
            system.play_sound("~/Sounds/a.mp3")
        self.assertEqual(self.started[0].argv[-1], os.path.expanduser("~/Sounds/a.mp3"))

    def test_stop_ends_what_is_playing_and_counts_it(self):
        with self.installed("pw-play"):
            system.play_sound(self.path)
            system.play_sound(self.path)
            self.started[0].ended = True  # one has already finished
        self.assertEqual(system.stop_sounds(), 1)
        self.assertTrue(self.started[1].ended)
        self.assertEqual(system.stop_sounds(), 0)


class SoundActionsTest(unittest.TestCase):
    def test_play_sound_passes_the_path_and_volume(self):
        with mock.patch.object(actions.system, "play_sound") as play:
            actions.perform(CFG, {"action": "play_sound", "params": {"path": " ~/a.wav ", "volume": "30%"}})
        play.assert_called_once_with("~/a.wav", 30)

    def test_an_empty_path_or_a_bad_volume_is_found_before_it_runs(self):
        problems = actions.binding_problems({"action": "play_sound", "params": {"path": "", "volume": "100"}})
        self.assertTrue(problems)
        problems = actions.binding_problems({"action": "play_sound", "params": {"path": "a.wav", "volume": "loud"}})
        self.assertTrue(problems)
        self.assertEqual(actions.binding_problems({"action": "play_sound", "params": {"path": "a.wav", "volume": "80"}}), [])

    def test_stop_says_what_happened(self):
        with mock.patch.object(actions.system, "stop_sounds", return_value=2):
            self.assertEqual(actions.perform(CFG, {"action": "stop_sounds"}), "Sounds stopped")
        with mock.patch.object(actions.system, "stop_sounds", return_value=0):
            self.assertEqual(actions.perform(CFG, {"action": "stop_sounds"}), "Nothing was playing")

    def test_both_can_be_macro_steps(self):
        self.assertIn("play_sound", actions.STEP_IDS)
        self.assertIn("stop_sounds", actions.STEP_IDS)


if __name__ == "__main__":
    unittest.main()
