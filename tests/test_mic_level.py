"""tools/mic-level: the live microphone meter. pw-record is replaced by a stand-in that writes what the real one does
(a ".snd" header and BIG-endian 16-bit samples), because reading that as little-endian once made it show loud noise."""

import math
import os
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "mic-level"


def fake_pw_record(folder, amplitude):
    header = b".snd" + struct.pack(">IIIII", 24, 0xFFFFFFFF, 3, 16000, 1)
    samples = b"".join(struct.pack(">h", int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000 * 3))
    script = Path(folder) / "pw-record"
    script.write_text("#!/bin/sh\nexec python3 -c \"import sys; sys.stdout.buffer.write(open(sys.argv[1], 'rb').read())\" " + str(Path(folder) / "stream.snd") + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (Path(folder) / "stream.snd").write_bytes(header + samples)


def meter(amplitude):
    with tempfile.TemporaryDirectory() as folder:
        fake_pw_record(folder, amplitude)
        done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=20,
                              env={**os.environ, "PATH": folder + os.pathsep + os.environ["PATH"]})
    lines = [part for part in done.stdout.replace("\r", "\n").splitlines() if " dB |" in part]
    return float(lines[-1].split(" dB")[0]), done.returncode


class MicLevelTest(unittest.TestCase):
    def test_a_known_loudness_is_read_correctly(self):
        for amplitude, expected in ((0.5, -9.0), (0.05, -29.0), (0.005, -49.0)):  # a sine's RMS is 3 dB under its peak
            level, code = meter(amplitude)
            self.assertEqual(code, 0)
            self.assertAlmostEqual(level, expected, delta=1.0, msg=f"amplitude {amplitude}")

    def test_it_says_what_it_is_when_pipewire_is_missing(self):
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=20,
                                  env={"PATH": empty})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("pw-record", done.stderr + done.stdout)


if __name__ == "__main__":
    unittest.main()
