"""The voice changer: EasyEffects' command line, as measured on the real thing (8.3), with a stand-in for it."""

import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from numpadctl import actions, config, voice

CFG = {**config.DEFAULT_CONFIG, "feedback": False}


class FakeEasyEffects:
    """What `easyeffects ...` and `pgrep -x easyeffects` print, as the real program does."""

    def __init__(self, presets=("Deep", "Robot"), running=True, installed=True):
        self.presets, self.is_running, self.installed = list(presets), running, installed
        self.bypass, self.loaded, self.calls, self.started = "2", "", [], 0
        self.busy_probes = 0  # how many "are you ready?" questions it fails to answer in time, while starting up

    def which(self, name):
        return f"/usr/bin/{name}" if name != "easyeffects" or self.installed else None

    def run(self, argv, **kwargs):
        if argv[0] == "pgrep":
            return SimpleNamespace(returncode=0 if self.is_running else 1, stdout="")
        self.calls.append(argv[1:])
        args, out = argv[1:], ""
        if args == ["-p"]:
            out = "No output presets.\n" + ("Input presets:\n" + "".join(f"{i}\t{n}\n" for i, n in enumerate(self.presets, 1))
                                            if self.presets else "No input presets.\n")
        elif args == ["-b", "3"]:
            if self.busy_probes > 0:
                self.busy_probes -= 1
                raise subprocess.TimeoutExpired(argv, 3)
            out = self.bypass + "\n"
        elif args[0] == "-b":
            self.bypass = "1" if args[1] == "1" else "2"
        elif args[0] == "-l":
            if args[1] in self.presets:
                self.loaded = args[1]
            else:
                out = "Specified preset does not exist.\n"  # and it still exits 0
        elif args == ["-a", "input"]:
            out = self.loaded + "\n"
        return SimpleNamespace(returncode=0, stdout=out)

    def popen(self, argv, **kwargs):
        self.started += 1
        self.is_running = True
        return mock.Mock()


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.ee = FakeEasyEffects()
        for patch in (mock.patch.object(voice.shutil, "which", self.ee.which),
                      mock.patch.object(voice.subprocess, "run", self.ee.run),
                      mock.patch.object(voice.subprocess, "Popen", self.ee.popen),
                      mock.patch.object(voice.time, "sleep", lambda s: None)):
            patch.start()
            self.addCleanup(patch.stop)

    @unittest.skipIf(sys.platform == "win32", "Linux only: XDG folders are separated by a colon")
    def test_the_preset_list_is_read_from_the_preset_folders_even_before_easyeffects_runs(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            mine, system = Path(tmp) / "mine/easyeffects/input", Path(tmp) / "sys/easyeffects/input"
            for folder, names in ((mine, ["Robot", "Deep"]), (system, ["Deep", "Radio"])):
                folder.mkdir(parents=True)
                for name in names:
                    (folder / f"{name}.json").write_text("{}")
            (mine / "notes.txt").write_text("not a preset")
            self.ee.is_running = False
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(Path(tmp) / "mine"), "XDG_DATA_DIRS": str(Path(tmp) / "sys")}):
                self.assertEqual(voice.presets("input"), ["Deep", "Robot", "Radio"], "yours first, each once")
                self.assertEqual(voice.presets("output"), [])
        self.assertEqual(self.ee.started, 0, "listing them never starts anything")

    def test_loading_a_voice_switches_the_microphone_and_turns_the_effects_on(self):
        self.ee.bypass = "1"
        self.assertEqual(voice.load("Robot"), "Voice: Robot")
        self.assertEqual((self.ee.loaded, self.ee.bypass), ("Robot", "2"))

    def test_a_voice_that_does_not_exist_is_an_error_that_lists_the_real_ones(self):
        with self.assertRaises(voice.VoiceError) as caught, mock.patch.object(voice, "presets", lambda kind="input": self.ee.presets):
            voice.load("Chipmunk")
        self.assertIn("no preset called 'Chipmunk'", str(caught.exception))
        self.assertIn("Deep, Robot", str(caught.exception))

    def test_no_preset_at_all_says_to_make_one(self):
        self.ee.presets = []
        with self.assertRaises(voice.VoiceError) as caught, mock.patch.object(voice, "presets", lambda kind="input": []):
            voice.load("Deep")
        self.assertIn("make one in EasyEffects", str(caught.exception))
        with self.assertRaises(voice.VoiceError):
            voice.load("   ")

    def test_back_to_normal_switches_the_effects_off_or_loads_the_normal_preset(self):
        voice.load("Deep")
        self.assertEqual(voice.off(), "Voice: normal")
        self.assertEqual(self.ee.bypass, "1")
        self.ee.presets.append("Clean")
        self.assertEqual(voice.off("Clean"), "Voice (normal): Clean")
        self.assertEqual((self.ee.loaded, self.ee.bypass), ("Clean", "2"))

    def test_the_toggle_goes_on_then_off_then_on(self):
        self.assertEqual(voice.toggle("Deep"), "Voice: Deep")
        self.assertEqual(self.ee.bypass, "2")
        self.assertEqual(voice.toggle("Deep"), "Voice: normal")
        self.assertEqual(self.ee.bypass, "1")
        self.assertEqual(voice.toggle("Deep"), "Voice: Deep")

    def test_the_toggle_of_another_voice_switches_to_it_instead_of_switching_off(self):
        voice.toggle("Deep")
        self.assertEqual(voice.toggle("Robot"), "Voice: Robot")
        self.assertEqual(self.ee.loaded, "Robot")

    def test_a_toggle_with_a_normal_preset_goes_between_the_two(self):
        self.ee.presets.append("Clean")
        voice.toggle("Deep", "Clean")
        self.assertEqual(self.ee.loaded, "Deep")
        self.assertEqual(voice.toggle("Deep", "Clean"), "Voice (normal): Clean")
        self.assertEqual((self.ee.loaded, self.ee.bypass), ("Clean", "2"), "effects stay on, with the clean preset")

    def test_easyeffects_is_started_hidden_when_it_is_not_running(self):
        self.ee.is_running = False
        voice.load("Deep")
        self.assertEqual(self.ee.started, 1)
        self.assertEqual(self.ee.loaded, "Deep")

    def test_easyeffects_still_loading_its_plugins_is_waited_for_not_given_up_on(self):
        """The first press after boot found it starting, asked "ready?", got no answer in 3 s and failed."""
        self.ee.is_running = False
        self.ee.busy_probes = 4
        self.assertEqual(voice.load("Deep"), "Voice: Deep")
        self.assertEqual(self.ee.started, 1, "started once, not once per question")

    def test_one_that_never_answers_is_an_error_after_the_wait(self):
        self.ee.is_running = False
        self.ee.busy_probes = 10 ** 6
        with mock.patch.object(voice, "READY_SECONDS", 0.05), self.assertRaises(voice.VoiceError) as caught:
            voice.load("Deep")
        self.assertIn("didn't start", str(caught.exception))

    def test_a_running_easyeffects_is_left_alone(self):
        voice.load("Deep")
        self.assertEqual(self.ee.started, 0)

    def test_without_easyeffects_it_says_how_to_get_it(self):
        self.ee.installed = False
        for work in (lambda: voice.load("Deep"), voice.off, lambda: voice.toggle("Deep")):
            with self.assertRaises(voice.VoiceError) as caught:
                work()
            self.assertIn("pacman -S easyeffects", str(caught.exception))
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_DATA_HOME": tmp, "XDG_DATA_DIRS": tmp}), \
                mock.patch.object(voice.Path, "home", return_value=Path(tmp)):  # (not your real preset folders)
            self.assertEqual(voice.presets(), [], "the pick list is just empty")


class VoiceActionsTest(unittest.TestCase):
    def setUp(self):
        self.ee = FakeEasyEffects()
        for patch in (mock.patch.object(voice.shutil, "which", self.ee.which),
                      mock.patch.object(voice.subprocess, "run", self.ee.run),
                      mock.patch.object(voice.subprocess, "Popen", self.ee.popen),
                      mock.patch.object(voice.time, "sleep", lambda s: None),
                      mock.patch.object(actions, "IS_WINDOWS", False)):
            patch.start()
            self.addCleanup(patch.stop)

    def perform(self, action, **params):
        return actions.perform(CFG, {"action": action, "params": params})

    def test_the_three_actions(self):
        self.assertEqual(self.perform("voice_on", preset="Robot"), "Voice: Robot")
        self.assertEqual(self.perform("voice_off"), "Voice: normal")
        self.assertEqual(self.perform("voice_toggle", preset="Deep", normal=""), "Voice: Deep")
        self.assertEqual(self.perform("voice_toggle", preset="Deep", normal=""), "Voice: normal")

    def test_a_voicechanger_problem_is_a_normal_action_error(self):
        with self.assertRaises(actions.ActionError) as caught:
            self.perform("voice_on", preset="Nope")
        self.assertIn("no preset called", str(caught.exception))

    def test_a_missing_preset_name_is_found_before_it_runs(self):
        for action in ("voice_toggle", "voice_on"):
            self.assertTrue(actions.binding_problems({"action": action, "params": {"preset": " "}}), action)
        self.assertEqual(actions.binding_problems({"action": "voice_on", "params": {"preset": "Deep"}}), [])

    def test_the_pick_list_offers_the_microphone_presets(self):
        with mock.patch.object(voice, "presets", lambda kind="input": ["Deep", "Robot"]):
            self.assertEqual(actions.SUGGESTIONS["voice_presets"](CFG, {}), ["Deep", "Robot"])

    def test_windows_says_it_is_linux_only(self):
        with mock.patch.object(actions, "IS_WINDOWS", True):
            with self.assertRaises(actions.ActionError) as caught:
                self.perform("voice_on", preset="Deep")
        self.assertIn("Linux", str(caught.exception))

    def test_they_form_their_own_group_and_can_be_macro_steps(self):
        self.assertEqual({a.group for a in actions.ACTIONS if a.id.startswith("voice_")}, {"Voice"})
        for action in ("voice_toggle", "voice_on", "voice_off"):
            self.assertIn(action, actions.STEP_IDS)


if __name__ == "__main__":
    unittest.main()
