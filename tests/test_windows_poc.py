import ctypes
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "windows-poc"))
import numpad_poc  # noqa: E402

KEYBOARDS = {1: "HID\\VID_046D&PID_C31C (main keyboard)", 2: "HID\\VID_C0F4&PID_05F5 (numpad)"}


class FakeInterception:
    """Stands in for interception.dll: a main keyboard (1) and a numpad (2)."""

    def __init__(self, strokes):
        self.queue = list(strokes)  # (device, code, state)
        self.sent, self.destroyed, self.pending = [], False, None

    def interception_create_context(self):
        return 1234

    def interception_destroy_context(self, context):
        self.destroyed = True

    def interception_get_hardware_id(self, context, device, buffer, size):
        if device not in KEYBOARDS:
            return 0
        raw = (KEYBOARDS[device] + "\0HID_DEVICE_SYSTEM_KEYBOARD\0\0").encode("utf-16-le")
        ctypes.memmove(buffer, raw, len(raw))
        return len(raw)

    def interception_set_filter(self, context, predicate, flags):
        self.filter = (predicate(1), predicate(2), predicate(11), flags)

    def interception_wait_with_timeout(self, context, ms):
        if not self.queue:
            return 0
        self.pending = self.queue.pop(0)
        return self.pending[0]

    def interception_receive(self, context, device, stroke, count):
        _, code, state = self.pending
        struct.pack_into("<HHI", stroke, 0, code, state, 0)
        return 1

    def interception_send(self, context, device, stroke, count):
        self.sent.append((device,) + struct.unpack_from("<HH", bytes(stroke)))
        return 1


def clock_after(steps):
    ticks = iter(range(10 ** 6))
    return lambda: next(ticks) / steps


class WindowsProofOfConceptTest(unittest.TestCase):
    STROKES = [(1, 0x02, 0), (1, 0x02, 1),                         # "1" on the main keyboard
               (2, 0x4F, 0), (2, 0x4F, 1),                         # numpad 1
               (2, 0x1C, numpad_poc.KEY_E0), (2, 0x1C, numpad_poc.KEY_E0 | 1),  # numpad Enter
               (1, 0x1C, 0), (1, 0x1C, 1)]                         # main Enter

    def run_poc(self, block=None):
        lib, lines = FakeInterception(self.STROKES), []
        seen = numpad_poc.run(lib, block=block, seconds=1, out=lines.append, clock=clock_after(100))
        return lib, seen, lines

    def test_watch_passes_every_key_through(self):
        lib, seen, lines = self.run_poc()
        self.assertEqual(len(lib.sent), len(self.STROKES))
        self.assertTrue(lib.destroyed)
        self.assertEqual(lib.filter, (1, 1, 0, numpad_poc.FILTER_KEY_ALL))  # keyboards only, not mice
        self.assertIn("  keyboard 2: HID\\VID_C0F4&PID_05F5 (numpad)", lines)
        self.assertTrue(any("keyboard 2: numpad Enter" in l for l in lines))
        self.assertTrue(any("keyboard 1: Enter (main)" in l for l in lines))

    def test_block_swallows_only_the_numpad(self):
        lib, seen, lines = self.run_poc(block=2)
        self.assertEqual({d for d, *_ in lib.sent}, {1}, "numpad strokes, including releases, are swallowed")
        self.assertEqual(len(lib.sent), 4)
        self.assertTrue(any("(blocked)" in l and "keyboard 2" in l for l in lines))

    def test_summary_names_the_numpad(self):
        _, seen, _ = self.run_poc()
        lines = []
        numpad_poc.summary(seen, out=lines.append)
        self.assertIn("python numpad_poc.py --block 2", lines[-1])

    def test_names(self):
        self.assertEqual(numpad_poc.key_name(0x35, numpad_poc.KEY_E0), "numpad /")
        self.assertEqual(numpad_poc.key_name(0x35, 0), "scan code 0x35")  # "/" on the main keyboard
        self.assertEqual(numpad_poc.parse_hardware_id("A\0B\0\0".encode("utf-16-le")), "A")


if __name__ == "__main__":
    unittest.main()
