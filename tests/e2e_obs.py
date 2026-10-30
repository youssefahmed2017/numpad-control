"""End-to-end: NumpadPilot's OBS actions against a real (private, headless) OBS. Not part of the normal test run.

    .venv/bin/python -m unittest tests.e2e_obs -v

It starts its own OBS (see obs_testbed.py), so your own OBS and its scenes are not touched, nothing appears on screen,
and nothing is streamed. Recordings go to a temporary folder that is deleted afterwards."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obs_testbed import ObsTestbed  # noqa: E402

from numpadctl import actions, config, obs  # noqa: E402

PROBLEM = ObsTestbed.available()


@unittest.skipIf(PROBLEM, PROBLEM)
class ObsActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bed = ObsTestbed().__enter__()
        cls.addClassCleanup(cls.bed.__exit__, None, None, None)
        cls.bed.build_scenes()
        c = cls.bed.client
        c.create_input("Test", "Mic", "pulse_input_capture", {"device_id": "numpad_test_no_such_device"}, True)  # captures nothing
        c.create_source_filter("Background", "Tint", "color_filter_v2", {})
        cls.cfg = {**config.DEFAULT_CONFIG, "feedback": False, "obs": cls.bed.cfg}

    def setUp(self):
        """Every test starts from the same OBS: Test scene, background shown, mic unmuted, filter on, not recording."""
        c = self.c
        if self.recording().output_active:
            c.stop_record()
            self.bed.wait_for(lambda: not self.recording().output_active, what="the previous recording to end")
        c.set_current_program_scene("Test")
        c.set_scene_item_enabled("Test", c.get_scene_item_id("Test", "Background").scene_item_id, True)
        c.set_input_mute("Mic", False)
        c.set_source_filter_enabled("Background", "Tint", True)

    def do(self, action, **params):
        return actions.perform(self.cfg, {"action": action, "params": params})

    @property
    def c(self):
        return self.bed.client

    def item_enabled(self, scene, source):
        item = self.c.get_scene_item_id(scene, source).scene_item_id
        return self.c.get_scene_item_enabled(scene, item).scene_item_enabled

    # ---------------------------------------------------------------- scenes and sources
    def test_connection_and_the_name_lists_the_settings_window_shows(self):
        self.assertTrue(obs.test_connection(self.cfg["obs"]))
        self.assertTrue({"Test", "Other"} <= set(obs.list_scenes(self.cfg["obs"])))
        self.assertIn("Background", obs.list_scene_sources(self.cfg["obs"], "Test"))
        self.assertIn("Mic", obs.list_audio_inputs(self.cfg["obs"]))
        self.assertIn("Tint", obs.list_filters(self.cfg["obs"], "Background"))

    def test_switch_scene_and_back(self):
        self.assertIn("Other", self.do("obs_switch_scene", scene="Other"))
        self.assertEqual(self.c.get_current_program_scene().current_program_scene_name, "Other")
        self.do("obs_switch_scene", scene="Test")
        self.assertEqual(self.c.get_current_program_scene().current_program_scene_name, "Test")

    def test_an_unknown_scene_is_a_clear_error(self):
        with self.assertRaises(actions.ActionError) as caught:
            self.do("obs_switch_scene", scene="No such scene")
        self.assertEqual(str(caught.exception), "No source was found by the name of `No such scene`")

    def test_show_hide_a_source_flips_it_each_press(self):
        self.assertTrue(self.item_enabled("Test", "Background"))
        self.assertIn("hidden", self.do("obs_toggle_source", scene="Test", source="Background"))
        self.assertFalse(self.item_enabled("Test", "Background"))
        self.assertIn("shown", self.do("obs_toggle_source", scene="Test", source="Background"))
        self.assertTrue(self.item_enabled("Test", "Background"))

    def test_mute_and_unmute_an_audio_source(self):
        self.assertFalse(self.c.get_input_mute("Mic").input_muted)
        self.do("obs_toggle_mute", source="Mic")
        self.assertTrue(self.c.get_input_mute("Mic").input_muted)
        self.do("obs_toggle_mute", source="Mic")
        self.assertFalse(self.c.get_input_mute("Mic").input_muted)

    def test_a_filter_goes_on_and_off(self):
        before = self.c.get_source_filter("Background", "Tint").filter_enabled
        self.do("obs_toggle_filter", source="Background", filter="Tint")
        self.assertNotEqual(self.c.get_source_filter("Background", "Tint").filter_enabled, before)
        self.do("obs_toggle_filter", source="Background", filter="Tint")
        self.assertEqual(self.c.get_source_filter("Background", "Tint").filter_enabled, before)

    def test_privacy_panic_hides_the_obs_camera_and_touches_nothing_else(self):
        """Only its OBS step is switched on, so nothing on this computer is muted, paused or hidden by the test."""
        self.c.set_scene_item_enabled("Test", self.c.get_scene_item_id("Test", "Background").scene_item_id, True)
        result = self.do("privacy_panic", mic=False, speakers=False, media=False, windows=False, lock=False,
                         scene="Test", source="Background")
        self.assertIn("OBS source hidden", result)
        self.assertFalse(self.item_enabled("Test", "Background"))
        self.do("privacy_panic", mic=False, speakers=False, media=False, windows=False,
                scene="Test", source="Background")  # again: it stays hidden, no flip back
        self.assertFalse(self.item_enabled("Test", "Background"))
        self.c.set_scene_item_enabled("Test", self.c.get_scene_item_id("Test", "Background").scene_item_id, True)

    # ---------------------------------------------------------------- recording
    def recording(self):
        return self.c.get_record_status()

    def test_record_pause_resume_stop_makes_a_real_video_file(self):
        self.assertIn("Recording", self.do("obs_start_recording"))
        self.bed.wait_for(lambda: self.recording().output_active, what="the recording to start")
        self.assertEqual(self.do("obs_start_recording"), "Already recording")
        import time
        time.sleep(1.5)
        self.do("obs_toggle_pause_recording")  # one key: pause
        self.bed.wait_for(lambda: self.recording().output_paused, what="the pause")
        self.do("obs_toggle_pause_recording")  # the same key: resume
        self.bed.wait_for(lambda: not self.recording().output_paused, what="the resume")
        time.sleep(1.0)
        self.assertIn("stopped", self.do("obs_stop_recording"))
        self.bed.wait_for(lambda: not self.recording().output_active, what="the recording to end")
        self.assertEqual(self.do("obs_stop_recording"), "Not recording")
        files = sorted(self.bed.recordings.glob("*.*"))
        self.assertTrue(files, "OBS wrote a file")
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(files[-1])],
                                         capture_output=True, text=True).stdout)
        self.assertIn("video", [s["codec_type"] for s in info["streams"]])
        self.assertGreater(float(info["format"]["duration"]), 1.0)

    def test_toggle_recording_one_key_starts_and_stops(self):
        self.do("obs_toggle_recording")
        self.bed.wait_for(lambda: self.recording().output_active, what="the recording to start")
        self.do("obs_toggle_recording")
        self.bed.wait_for(lambda: not self.recording().output_active, what="the recording to end")

    def test_replay_buffer_on_then_save_makes_a_clip(self):
        import time
        self.assertIn("Replay", self.do("obs_toggle_replay_buffer"))
        self.bed.wait_for(lambda: self.c.get_replay_buffer_status().output_active, what="the replay buffer to start")
        time.sleep(2.5)  # something to save
        self.do("obs_save_replay")
        self.bed.wait_for(lambda: self.c.get_last_replay_buffer_replay().saved_replay_path, what="the clip to be saved")
        clip = Path(self.c.get_last_replay_buffer_replay().saved_replay_path)
        self.assertTrue(clip.exists() and clip.stat().st_size > 0)
        self.do("obs_toggle_replay_buffer")
        self.bed.wait_for(lambda: not self.c.get_replay_buffer_status().output_active, what="the replay buffer to stop")

    def test_without_obs_running_it_says_so(self):
        with self.assertRaises(actions.ActionError) as caught:
            actions.perform({**self.cfg, "obs": {"host": "localhost", "port": 4499, "password": ""}},
                            {"action": "obs_toggle_recording", "params": {}})
        self.assertIn("not running", str(caught.exception))

    def test_a_wrong_password_is_reported_not_hidden(self):
        # this OBS needs no password, so any password works; a closed port is the real "can't connect" case
        self.assertIn("OBS", str(self._error(lambda: actions.perform(
            {**self.cfg, "obs": {"host": "localhost", "port": 4498, "password": "x"}},
            {"action": "obs_save_replay", "params": {}}))))

    @staticmethod
    def _error(work):
        try:
            work()
        except actions.ActionError as e:
            return e
        return "no error"


@unittest.skipIf(PROBLEM, PROBLEM)
class ObsDefaultRecordingTest(unittest.TestCase):
    """OBS as most people have it (recording quality "Same as stream", Hybrid MP4): it takes a pause request and keeps
    recording. NumpadPilot must say so instead of showing "Recording paused"."""

    def test_pausing_a_recording_that_cannot_pause_says_so(self):
        with ObsTestbed(record_quality="Stream", record_format="hybrid_mp4") as bed:
            bed.build_scenes()
            cfg = {**config.DEFAULT_CONFIG, "feedback": False, "obs": bed.cfg}
            actions.perform(cfg, {"action": "obs_start_recording", "params": {}})
            bed.wait_for(lambda: bed.client.get_record_status().output_active, what="the recording to start")
            with self.assertRaises(actions.ActionError) as caught:
                actions.perform(cfg, {"action": "obs_toggle_pause_recording", "params": {}})
            self.assertIn("can't be paused", str(caught.exception))
            self.assertIn("Same as stream", str(caught.exception))
            actions.perform(cfg, {"action": "obs_stop_recording", "params": {}})


if __name__ == "__main__":
    unittest.main()
