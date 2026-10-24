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


class PlaceholderTest(unittest.TestCase):
    def test_time_date_and_clipboard(self):
        clip = mock.Mock(stdout="copied words")
        with mock.patch.object(actions.time, "strftime", side_effect=lambda f: {"%H:%M": "14:05", "%Y-%m-%d": "2026-10-24"}[f]), \
                mock.patch.object(actions.subprocess, "run", return_value=clip), \
                mock.patch.object(actions.shutil, "which", return_value="/usr/bin/wl-paste"):
            self.assertEqual(actions.fill_placeholders("at {time} on {date}: {clipboard}"),
                             "at 14:05 on 2026-10-24: copied words")

    def test_other_braces_are_left_alone(self):
        self.assertEqual(actions.fill_placeholders("{name} {} {{time}} function() { }"),
                         "{name} {} {" + actions.fill_placeholders("{time}") + "} function() { }")

    def test_clipboard_not_read_unless_used(self):
        with mock.patch.object(actions.subprocess, "run") as run:
            actions.fill_placeholders("plain text {time}")
        run.assert_not_called()

    def test_type_text_fills_placeholders(self):
        with mock.patch.object(actions, "_ydotool") as ydotool, \
                mock.patch.object(actions.time, "strftime", return_value="14:05"):
            actions.run({}, {"action": "type_text", "params": {"text": "Live since {time}"}})
        self.assertEqual(ydotool.call_args.kwargs["stdin"], "Live since 14:05")


if __name__ == "__main__":
    unittest.main()


class PlaceholderButtonTest(unittest.TestCase):
    def test_inserts_at_the_cursor(self):
        import gi
        gi.require_version("Adw", "1")
        gi.require_version("Gtk", "4.0")
        from gi.repository import Adw
        Adw.init()
        from numpadctl import gui
        entry = Adw.EntryRow(text="Live since  today")
        entry.set_position(11)
        button = gui.Window.placeholder_button(mock.Mock(popover_list=gui.Window.popover_list,
                                                         list_row=gui.Window.list_row), entry)
        listbox = button.get_popover().get_child().get_last_child().get_child().get_child()
        listbox.emit("row-activated", listbox.get_row_at_index(0))  # {time}
        self.assertEqual(entry.get_text(), "Live since {time} today")
        self.assertEqual(entry.get_position(), 17)
