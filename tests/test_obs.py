import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from numpadctl import actions, obs


class FakeOBS:
    """Shaped like obsws-python responses: top-level fields snake_case,
    nested lists keep OBS's camelCase keys."""

    def __init__(self):
        self.filters = {("Webcam", "Blur"): False}

    def get_scene_list(self):
        # OBS lists scenes bottom-to-top
        return SimpleNamespace(scenes=[{"sceneName": "Ending"}, {"sceneName": "Gaming"}])

    def get_scene_item_list(self, name):
        if name != "Gaming":
            raise RuntimeError("No source was found by the name of " + name)
        return SimpleNamespace(scene_items=[{"sourceName": "Webcam"}, {"sourceName": "Game"}])

    def get_input_list(self):
        return SimpleNamespace(inputs=[{"inputName": "Mic/Aux"}, {"inputName": "Webcam"},
                                       {"inputName": "Desktop Audio"}])

    def get_input_mute(self, name):
        if name == "Webcam":
            raise RuntimeError("The specified input does not support audio")
        return SimpleNamespace(input_muted=False)

    def get_source_filter_list(self, name):
        return SimpleNamespace(filters=[{"filterName": f} for (s, f) in self.filters if s == name])

    def get_source_filter(self, source_name, filter_name):
        return SimpleNamespace(filter_enabled=self.filters[(source_name, filter_name)])

    def set_source_filter_enabled(self, source_name, filter_name, enabled):
        self.filters[(source_name, filter_name)] = enabled


class OBSTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOBS()
        self.patch = mock.patch.object(obs, "_client", return_value=self.fake)
        self.patch.start()
        self.cfg = {"obs": {}, "feedback": False}

    def tearDown(self):
        self.patch.stop()

    def suggest(self, kind, **params):
        return actions.SUGGESTIONS[kind](self.cfg, params)

    def test_scene_list_is_in_obs_display_order(self):
        self.assertEqual(self.suggest("obs_scenes"), ["Gaming", "Ending"])

    def test_sources_follow_the_chosen_scene(self):
        self.assertEqual(self.suggest("obs_scene_sources", scene=" Gaming "), ["Webcam", "Game"])
        with self.assertRaisesRegex(obs.OBSError, "scene name first"):
            self.suggest("obs_scene_sources", scene="")

    def test_audio_inputs_skip_video_only_sources(self):
        self.assertEqual(self.suggest("obs_audio_inputs"), ["Mic/Aux", "Desktop Audio"])

    def test_filter_sources_include_video_inputs_and_scenes(self):
        names = self.suggest("obs_filter_sources")
        self.assertIn("Webcam", names)
        self.assertIn("Gaming", names)

    def test_filters_follow_the_chosen_source(self):
        self.assertEqual(self.suggest("obs_filters", source="Webcam"), ["Blur"])
        with self.assertRaisesRegex(obs.OBSError, "source name first"):
            self.suggest("obs_filters", source="")

    def test_toggle_filter(self):
        binding = {"action": "obs_toggle_filter", "params": {"source": "Webcam", "filter": "Blur"}}
        self.assertEqual(actions.run(self.cfg, binding), "Blur on")
        self.assertTrue(self.fake.filters[("Webcam", "Blur")])
        self.assertEqual(actions.run(self.cfg, binding), "Blur off")

    def test_pause_resume_is_one_key_that_flips_each_press(self):
        state = {"active": True, "paused": False}
        c = mock.Mock()
        c.get_record_status.side_effect = lambda: SimpleNamespace(output_active=state["active"], output_paused=state["paused"])
        c.pause_record.side_effect = lambda: state.update(paused=True)
        c.resume_record.side_effect = lambda: state.update(paused=False)
        binding = {"action": "obs_toggle_pause_recording", "params": {}}
        with mock.patch.object(obs, "_client", return_value=c):
            said = [actions.run(self.cfg, binding) for _ in range(4)]
            state["active"] = False
            said.append(actions.run(self.cfg, binding))
        self.assertEqual(said, ["Recording paused", "Recording resumed", "Recording paused", "Recording resumed",
                                "Not recording"])


class PlaceholderTest(unittest.TestCase):
    def test_time_date_and_clipboard(self):
        clip = mock.Mock(stdout="copied words")
        with mock.patch.object(actions.time, "strftime", side_effect=lambda f: {"%H:%M": "14:05", "%Y-%m-%d": "2026-10-24"}[f]), \
                mock.patch.object(actions.system, "clipboard_text", return_value=clip.stdout):
            self.assertEqual(actions.fill_placeholders("at {time} on {date}: {clipboard}"),
                             "at 14:05 on 2026-10-24: copied words")

    def test_other_braces_are_left_alone(self):
        self.assertEqual(actions.fill_placeholders("{name} {} {{time}} function() { }"),
                         "{name} {} {" + actions.fill_placeholders("{time}") + "} function() { }")

    def test_clipboard_not_read_unless_used(self):
        with mock.patch.object(actions.system, "clipboard_text") as clipboard:
            actions.fill_placeholders("plain text {time}")
        clipboard.assert_not_called()

    @unittest.skipIf(sys.platform == "win32", "checks the Linux typing tool")
    def test_type_text_fills_placeholders(self):
        from numpadctl.platform import linux_system
        with mock.patch.object(linux_system, "_ydotool") as ydotool, \
                mock.patch.object(actions.time, "strftime", return_value="14:05"):
            actions.run({}, {"action": "type_text", "params": {"text": "Live since {time}"}})
        self.assertEqual(ydotool.call_args.kwargs["stdin"], "Live since 14:05")


class PauseAndErrorsTest(unittest.TestCase):
    def test_a_pause_that_did_not_happen_is_an_error_not_a_lie(self):
        """Hybrid MP4 accepts PauseRecord and keeps recording."""
        c = mock.Mock()
        c.get_record_status.return_value = SimpleNamespace(output_active=True, output_paused=False)
        with mock.patch.object(obs, "_client", return_value=c), mock.patch.object(obs.time, "sleep", lambda s: None):
            for work in (obs.pause_recording, obs.toggle_pause_recording):
                with self.assertRaises(obs.OBSError) as caught:
                    work({})
                self.assertIn("Same as stream", str(caught.exception))
                self.assertIn("MKV", str(caught.exception))

    def test_obs_wording_is_kept_and_its_technical_wrapping_dropped(self):
        wrapped = ("Request SetCurrentProgramScene returned code 600. With message: No source was found by the name of "
                   "`Gaming` within the canvas `Main`.")
        self.assertEqual(obs.friendly(Exception(wrapped)), "No source was found by the name of `Gaming`")
        self.assertEqual(obs.friendly(Exception("plain text")), "plain text")

    def test_a_refusal_from_obs_becomes_a_normal_action_error(self):
        class OBSSDKRequestError(Exception):
            __module__ = "obsws_python.error"

        def refuse(settings, scene):
            raise OBSSDKRequestError("Request X returned code 600. With message: No source was found by the name of `Z`.")
        run = actions._obs(refuse)
        with self.assertRaises(obs.OBSError) as caught:
            run({"obs": {}}, scene="Z")
        self.assertEqual(str(caught.exception), "No source was found by the name of `Z`")
        with self.assertRaises(ZeroDivisionError):  # an ordinary bug is not hidden as an OBS message
            actions._obs(lambda settings: 1 / 0)({"obs": {}})


if __name__ == "__main__":
    unittest.main()
