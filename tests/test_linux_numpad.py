import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("tests the Linux code (Windows has its own tests)")
import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from evdev import ecodes

from numpadctl.platform import linux_numpad


def event(code, value, kind=ecodes.EV_KEY):
    return SimpleNamespace(type=kind, code=code, value=value)


class FakeDevice:
    def __init__(self, name, events, fail=False):
        self.name, self.path = name, "/dev/input/fake"
        self.info = SimpleNamespace(vendor=0xc0f4, product=0x05f5)
        self._events, self._fail = events, fail

    async def async_read_loop(self):
        for ev in self._events:
            yield ev
            await asyncio.sleep(0)
        if self._fail:
            raise OSError(19, "No such device")
        await asyncio.sleep(3600)


class LinuxNumpadTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, numpad, count):
        got = []
        async for item in numpad.events():
            got.append(item)
            if len(got) == count:
                return got

    async def test_key_codes_become_key_names(self):
        dev = FakeDevice("Usb KeyBoard", [
            event(ecodes.KEY_KP5, 1), event(ecodes.KEY_KP5, 2),   # autorepeat is ignored
            event(ecodes.KEY_KP5, 0), event(ecodes.KEY_A, 1),     # unmapped key is skipped
            event(0, 0, kind=ecodes.EV_SYN),                      # not a key event
            event(ecodes.KEY_KPENTER, 1), event(ecodes.KEY_KPCOMMA, 1)])
        got = await asyncio.wait_for(self.collect(linux_numpad.Numpad([dev]), 4), 2)
        self.assertEqual(got, [("5", True), ("5", False), ("Enter", True), (".", True)])

    async def test_several_devices_are_merged(self):
        a = FakeDevice("Usb KeyBoard", [event(ecodes.KEY_KP1, 1)])
        b = FakeDevice("Usb KeyBoard Consumer Control", [event(ecodes.KEY_KP2, 1)])
        got = await asyncio.wait_for(self.collect(linux_numpad.Numpad([a, b]), 2), 2)
        self.assertEqual(sorted(got), [("1", True), ("2", True)])

    async def test_unplugging_raises(self):
        dev = FakeDevice("Usb KeyBoard", [event(ecodes.KEY_KP1, 1)], fail=True)
        with self.assertRaises(OSError):
            await asyncio.wait_for(self.collect(linux_numpad.Numpad([dev]), 99), 2)

    def test_spec_uses_the_main_device_name(self):
        numpad = linux_numpad.Numpad([FakeDevice("Usb KeyBoard System Control", []),
                                      FakeDevice("Usb KeyBoard", [])])
        self.assertEqual(numpad.spec, {"vendor": "c0f4", "product": "05f5", "name": "Usb KeyBoard"})
        self.assertEqual(len(numpad.names), 2)

    def test_every_numpad_key_has_a_name(self):
        self.assertEqual(set(linux_numpad.KEY_CODES) | {"000"},
                         {"NumLock", "/", "*", "Backspace", "-", "+", "Enter", ".", "000",
                          *map(str, range(10))})


if __name__ == "__main__":
    unittest.main()
