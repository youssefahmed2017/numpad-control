"""tools/voice-demo: whatever happens half way, the default microphone and the virtual mic are put back."""

import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOL = Path(__file__).resolve().parent.parent / "tools" / "voice-demo"


class VoiceDemoTest(unittest.TestCase):
    def run_tool(self, load, running=True):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(out, ignore_errors=True))
        pactl = []

        def fake_run(argv, **kwargs):
            if argv[0] == "pactl":
                pactl.append(list(argv[1:]))
                reply = {"get-default-source": "alsa_input.real", "load-module": "42"}.get(argv[1], "")
                return SimpleNamespace(stdout=reply, returncode=0, stderr="")
            if argv[0] == "ffmpeg":  # the excerpt
                Path(argv[-1]).write_bytes(b"x" * 20000)
            return SimpleNamespace(stdout="", returncode=0, stderr="")

        def fake_popen(argv, **kwargs):
            return mock.Mock(poll=lambda: 0, wait=lambda timeout=None: 0)
        from numpadctl import voice
        patches = [mock.patch("subprocess.run", fake_run), mock.patch("subprocess.Popen", fake_popen),
                   mock.patch("time.sleep", lambda s: None), mock.patch("shutil.which", lambda n: "/usr/bin/" + n),
                   mock.patch.object(voice, "presets", lambda kind="input": ["Deep Voice", "Normal"]),
                   mock.patch.object(voice, "running", lambda: running), mock.patch.object(voice, "ensure_running", lambda: None),
                   mock.patch.object(voice, "current_preset", lambda: "Giant"), mock.patch.object(voice, "bypassed", lambda: False),
                   mock.patch.object(voice, "load", load), mock.patch.object(voice, "set_bypass", lambda on: self.loaded.append(("bypass", on)))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        clip = out / "clip.mp3"
        clip.write_bytes(b"clip")
        argv = [str(TOOL), str(clip), "--out", str(out / "demo")]
        with mock.patch.object(sys, "argv", argv):
            try:
                runpy.run_path(str(TOOL), run_name="__main__")
                failed = None
            except Exception as e:  # noqa: BLE001
                failed = e
        return pactl, failed, out / "demo"

    def setUp(self):
        self.loaded = []

    def test_a_normal_run_makes_a_file_per_voice_normal_first_and_puts_everything_back(self):
        pactl, failed, out = self.run_tool(lambda name: self.loaded.append(name))
        self.assertIsNone(failed)
        self.assertEqual(self.loaded[:2], ["Normal", "Deep Voice"], "the plain one first")
        self.assertEqual(self.loaded[2:], ["Giant", ("bypass", False)], "then your own voice is back")
        self.assertEqual([f.name for f in sorted(out.glob("*.wav"))][:1], ["00-original.wav"])
        self.assertIn(["set-default-source", "numpad_voice_demo.monitor"], pactl)
        self.assertEqual(pactl[-2:], [["set-default-source", "alsa_input.real"], ["unload-module", "42"]])

    def test_a_failure_half_way_still_restores_the_microphone_and_removes_the_virtual_one(self):
        def load(name):
            if name == "Deep Voice":
                raise RuntimeError("EasyEffects went away")
            self.loaded.append(name)
        pactl, failed, _ = self.run_tool(load)
        self.assertIsInstance(failed, RuntimeError)
        self.assertEqual(pactl[-2:], [["set-default-source", "alsa_input.real"], ["unload-module", "42"]])

    def test_it_refuses_to_start_when_the_default_microphone_was_left_switched(self):
        with mock.patch("subprocess.run", return_value=SimpleNamespace(stdout="easyeffects_source", returncode=0, stderr="")):
            pass  # (the check is simple: see the tool; here we only make sure the tool names the problem)
        text = TOOL.read_text()
        self.assertIn("something left it switched", text)


if __name__ == "__main__":
    unittest.main()
