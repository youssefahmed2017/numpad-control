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


def fake_pw_record(folder, quiet, loud):
    """A stream that is `quiet` for 2.5 s (the room), then `loud`, as amplitudes (0 to 1) of a 440 Hz sine."""
    header = b".snd" + struct.pack(">IIIII", 24, 0xFFFFFFFF, 3, 16000, 1)

    def sine(amplitude, seconds):
        return b"".join(struct.pack(">h", int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / 16000)))
                        for i in range(int(16000 * seconds)))
    script = Path(folder) / "pw-record"
    script.write_text("#!/bin/sh\nexec python3 -c \"import sys; sys.stdout.buffer.write(open(sys.argv[1], 'rb').read())\" "
                      + str(Path(folder) / "stream.snd") + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (Path(folder) / "stream.snd").write_bytes(header + sine(quiet, 2.5) + sine(loud, 2.0))


def meter(quiet, loud):
    with tempfile.TemporaryDirectory() as folder:
        fake_pw_record(folder, quiet, loud)
        done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=30,
                              env={**os.environ, "PATH": folder + os.pathsep + os.environ["PATH"]})
    return done.stdout.replace("\r", "\n"), done.returncode


@unittest.skipIf(sys.platform == "win32", "Linux only: PipeWire, and the stand-in is a shell script")
class MicLevelTest(unittest.TestCase):
    def test_the_room_is_measured_first_and_a_known_loudness_is_read_correctly(self):
        out, code = meter(0.01, 0.5)  # the room at -43 dB, then 34 dB louder
        self.assertEqual(code, 0)
        self.assertIn("the room is at -4", out)  # a 0.01 sine is -43 dB RMS
        best = [float(line.split("best so far")[1].split("dB")[0]) for line in out.splitlines() if "best so far" in line]
        self.assertAlmostEqual(best[-1], 34, delta=2)

    def test_it_says_works_weak_or_nothing(self):
        for quiet, loud, word in ((0.01, 0.5, "WORKS"), (0.01, 0.03, "WEAK"), (0.01, 0.011, "Nothing rose")):
            out, _ = meter(quiet, loud)
            self.assertIn(word, out, f"{quiet} then {loud}")

    def test_it_says_what_it_is_when_pipewire_is_missing(self):
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=20,
                                  env={"PATH": empty})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("pw-record", done.stderr + done.stdout)


if __name__ == "__main__":
    unittest.main()
