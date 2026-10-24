import json
import unittest
from unittest import mock

from numpadctl import actions, audio


def stream(index, name, binary, percent, mute=False):
    level = {"value_percent": f"{percent}%"}
    return {"index": index, "mute": mute, "volume": {"front-left": level, "front-right": level},
            "properties": {"application.name": name, "application.process.binary": binary}}


class FakePactl:
    def __init__(self):
        self.streams = [stream(1, "Firefox", "firefox", 60), stream(2, "Firefox", "firefox", 40),
                        stream(3, "spotify", "spotify", 98)]
        self.sinks = [{"index": 5, "name": "alsa_speakers", "description": "Built-in Speakers"},
                      {"index": 9, "name": "bluez_headphones", "description": "WH-1000XM4 Headphones"}]
        self.default = "alsa_speakers"
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:3] == ("-f", "json", "list"):
            return json.dumps({"sink-inputs": self.streams, "sinks": self.sinks}[args[3]])
        if args[0] == "get-default-sink":
            return self.default + "\n"
        if args[0] == "set-default-sink":
            self.default = args[1]
        return ""


class AudioTest(unittest.TestCase):
    def setUp(self):
        self.pactl = FakePactl()
        self.patch = mock.patch.object(audio, "_pactl", self.pactl)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def run_action(self, action, **params):
        return actions.run({"feedback": False}, {"action": action, "params": params})

    def sets(self, verb):
        return [c[1:] for c in self.pactl.calls if c[0] == verb]

    def test_playing_apps_are_listed_once(self):
        self.assertEqual(audio.playing_apps(), ["Firefox", "spotify"])

    def test_volume_up_changes_every_stream_of_the_app(self):
        self.assertEqual(self.run_action("app_volume_up", app="firefox"), "Firefox 65%")
        self.assertEqual(self.sets("set-sink-input-volume"), [("1", "65%"), ("2", "45%")])

    def test_volume_is_capped_at_100(self):
        self.run_action("app_volume_up", app="Spotify")
        self.assertEqual(self.sets("set-sink-input-volume"), [("3", "100%")])

    def test_set_and_mute(self):
        self.run_action("app_volume_set", app="spotify", percent="30%")
        self.assertEqual(self.sets("set-sink-input-volume"), [("3", "30%")])
        self.assertEqual(self.run_action("app_mute", app="firefox"), "Firefox muted")
        self.assertEqual(self.sets("set-sink-input-mute"), [("1", "1"), ("2", "1")])

    def test_quiet_app_says_so(self):
        with self.assertRaisesRegex(actions.ActionError, "Discord isn't playing any sound"):
            self.run_action("app_mute", app="Discord")

    def test_switch_output_by_readable_name_moves_playing_streams(self):
        self.assertEqual(self.run_action("output_switch", output="wh-1000xm4"), "WH-1000XM4 Headphones")
        self.assertEqual(self.pactl.default, "bluez_headphones")
        self.assertEqual(self.sets("move-sink-input"),
                         [("1", "bluez_headphones"), ("2", "bluez_headphones"), ("3", "bluez_headphones")])

    def test_unknown_output(self):
        with self.assertRaisesRegex(actions.ActionError, "no output device called 'HDMI'"):
            self.run_action("output_switch", output="HDMI")

    def test_next_output_cycles(self):
        self.assertEqual(self.run_action("output_next"), "WH-1000XM4 Headphones")
        self.assertEqual(self.run_action("output_next"), "Built-in Speakers")

    def test_bad_percent_is_caught_on_save(self):
        self.assertTrue(actions.binding_problems(
            {"action": "app_volume_set", "params": {"app": "x", "percent": "loud"}}))
        self.assertTrue(actions.binding_problems({"action": "volume_set", "params": {"percent": "150"}}))


if __name__ == "__main__":
    unittest.main()


class OutputNameTest(unittest.TestCase):
    def test_underscores_and_spaces_match(self):
        sinks = [{"index": 1, "name": "x", "description": "Test_Speakers"}]
        self.assertIs(audio._find_output(sinks, "test speakers"), sinks[0])
