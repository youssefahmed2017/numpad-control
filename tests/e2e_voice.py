"""End-to-end: the voice changer, through EasyEffects and OBS, measured. Not part of the normal test run.

    .venv/bin/python -m unittest tests.e2e_voice -v

A silent virtual microphone plays a 440 Hz tone; EasyEffects (started by the test) runs NumpadPilot's voice actions on it; a
private headless OBS records the result; the pitch of the recording is measured. Your real microphone is never used, nothing
is audible, and the test puts back what it changed (your default microphone, EasyEffects, its preset file) even if it fails.
It refuses to run while EasyEffects is already running (it would disturb your session)."""

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obs_testbed import ObsTestbed  # noqa: E402

from numpadctl import actions, config, voice  # noqa: E402

TONE_HZ, SEMITONES = 440.0, -4.0
SINK = "numpad_voice_test"


def problem():
    if sys.platform != "linux":
        return "Linux only"
    for tool in ("easyeffects", "pactl", "pw-play", "ffmpeg"):
        if not shutil.which(tool):
            return f"{tool} is not installed"
    try:
        import numpy  # noqa: F401
    except ImportError:
        return "numpy is missing"
    if subprocess.run(["pgrep", "-x", "easyeffects"], capture_output=True).returncode == 0:
        return "EasyEffects is already running (it would be disturbed)"
    return ObsTestbed.available()


def sh(*argv, timeout=15):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout.strip()


def stop(process):
    """End a process this test started (EasyEffects' own -q can hang, so it is never used)."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def peak_hz(path):
    """The loudest frequency in the audio of a recording, and how loud (0..1)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    samples = samples[len(samples) // 4:]  # leave out the start
    if len(samples) < 4800:
        return None, 0.0
    level = float(np.abs(samples).max())
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.argmax(spectrum) * 48000 / len(samples)), level


@unittest.skipIf(problem(), problem())
class VoiceChangerEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="numpad-voice-"))
        cls.old_source = sh("pactl", "get-default-source")
        cls.module = cls.ee = cls.player = cls.bed = None
        cls.addClassCleanup(cls.tear_down)
        tone = cls.tmp / "tone.wav"
        with wave.open(str(tone), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * TONE_HZ * i / 48000))) for i in range(48000 * 90)))
        folder = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "easyeffects/input"
        folder.mkdir(parents=True, exist_ok=True)
        cls.preset_file = folder / "NumpadPilotE2E.json"
        cls.preset_file.write_text(json.dumps({"input": {"blocklist": [], "plugins_order": ["pitch#0"], "pitch#0": {
            "bypass": False, "input-gain": 0.0, "output-gain": 0.0, "semitones": SEMITONES, "cents": 0.0, "octaves": 0}}}))
        cls.module = sh("pactl", "load-module", "module-null-sink", f"sink_name={SINK}",
                        "sink_properties=device.description=NumpadVoiceTest")  # a silent virtual microphone
        sh("pactl", "set-default-source", f"{SINK}.monitor")
        cls.ee = subprocess.Popen(["easyeffects", "--service-mode"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        voice.ensure_running()
        cls.player = subprocess.Popen(["pw-play", "--target", SINK, "--volume", "0.5", str(tone)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.bed = ObsTestbed().__enter__()
        cls.bed.build_scenes()
        cls.bed.client.create_input("Test", "Voice", "pulse_input_capture", {"device_id": "easyeffects_source"}, True)
        cls.cfg = {**config.DEFAULT_CONFIG, "feedback": False, "obs": cls.bed.cfg}
        time.sleep(2)

    @classmethod
    def tear_down(cls):
        if cls.bed is not None:
            cls.bed.__exit__(None, None, None)
        stop(cls.player)
        stop(cls.ee)  # EasyEffects sets itself as the default microphone: only after it is gone is it safe to put yours back
        time.sleep(1)
        if cls.old_source:
            sh("pactl", "set-default-source", cls.old_source)
        if cls.module:
            sh("pactl", "unload-module", cls.module)
        if getattr(cls, "preset_file", None):
            cls.preset_file.unlink(missing_ok=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def do(self, action, **params):
        return actions.perform(self.cfg, {"action": action, "params": params})

    def record_pitch(self):
        """Record about 3 s in OBS from the voice changer's microphone and measure it."""
        before = set(self.bed.recordings.glob("*"))
        self.do("obs_start_recording")
        self.bed.wait_for(lambda: self.bed.client.get_record_status().output_active, what="the recording to start")
        time.sleep(3.5)
        self.do("obs_stop_recording")
        self.bed.wait_for(lambda: not self.bed.client.get_record_status().output_active, what="the recording to end")
        time.sleep(1)
        files = sorted(set(self.bed.recordings.glob("*")) - before)
        self.assertTrue(files, "OBS wrote a recording")
        return peak_hz(files[-1])

    def test_the_voice_key_changes_the_pitch_of_what_obs_records(self):
        self.assertEqual(self.do("voice_off"), "Voice: normal")
        time.sleep(1.5)
        hz, level = self.record_pitch()
        self.assertGreater(level, 0.01, "the tone reached OBS")
        self.assertAlmostEqual(hz, TONE_HZ, delta=6, msg="normal voice: the tone as it was")

        self.assertEqual(self.do("voice_on", preset="NumpadPilotE2E"), "Voice: NumpadPilotE2E")
        time.sleep(1.5)
        hz, level = self.record_pitch()
        self.assertGreater(level, 0.01)
        self.assertAlmostEqual(hz, TONE_HZ * 2 ** (SEMITONES / 12), delta=6, msg="the voice: four semitones lower")

        self.assertEqual(self.do("voice_off"), "Voice: normal")  # and back again
        time.sleep(1.5)
        hz, _ = self.record_pitch()
        self.assertAlmostEqual(hz, TONE_HZ, delta=6)

    def test_the_toggle_key_goes_on_and_off(self):
        self.do("voice_off")
        self.assertEqual(self.do("voice_toggle", preset="NumpadPilotE2E", normal=""), "Voice: NumpadPilotE2E")
        time.sleep(1.5)
        on, _ = self.record_pitch()
        self.assertEqual(self.do("voice_toggle", preset="NumpadPilotE2E", normal=""), "Voice: normal")
        time.sleep(1.5)
        off, _ = self.record_pitch()
        self.assertLess(on, off - 50, "on is lower than off")

    def test_the_pick_list_offers_the_preset_before_anything_runs(self):
        self.assertIn("NumpadPilotE2E", voice.presets("input"))

    def test_a_voice_that_does_not_exist_says_what_does(self):
        with self.assertRaises(actions.ActionError) as caught:
            self.do("voice_on", preset="Chipmunk")
        self.assertIn("NumpadPilotE2E", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
