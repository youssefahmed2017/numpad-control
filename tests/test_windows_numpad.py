"""The Windows input backend, against a fake interception.dll (like the dad's PC:
main keyboard = devices 1 and 2, numpad = device 3)."""

import asyncio
import ctypes
import struct
import threading
import unittest
from unittest import mock

from numpadctl.platform import windows_numpad as wn

DEVICES = {1: "HID\\VID_5566&PID_0008&REV_0100&MI_00&Col01",
           2: "HID\\VID_5566&PID_0008&REV_0100&MI_01",
           3: "HID\\VID_C0F4&PID_05F5&REV_0110&MI_00"}
NUMPAD = {"vendor": "c0f4", "product": "05f5"}


class FakeInterception:
    def __init__(self, strokes=()):
        self.devices = dict(DEVICES)
        self.queue = list(strokes)            # (device, code, state)
        self.filtered, self.sent, self.contexts = set(), [], 0
        self.pending, self.lock = None, threading.Lock()

    def interception_create_context(self):
        self.contexts += 1
        return 1000 + self.contexts

    def interception_destroy_context(self, context):
        self.contexts -= 1

    def interception_get_hardware_id(self, context, device, buffer, size):
        if device not in self.devices:
            return 0
        raw = (self.devices[device] + "\0\0").encode("utf-16-le")
        ctypes.memmove(buffer, raw, len(raw))
        return len(raw)

    def interception_set_filter(self, context, predicate, flags):
        chosen = {d for d in range(1, 21) if predicate(d)}
        self.filtered = chosen if flags else self.filtered - chosen

    def interception_wait_with_timeout(self, context, ms):
        with self.lock:
            while self.queue:
                device, code, state = self.queue.pop(0)
                if device in self.filtered:  # the driver only hands over filtered devices
                    self.pending = (code, state)
                    return device
        threading.Event().wait(ms / 1000 / 20)
        return 0

    def interception_receive(self, context, device, stroke, count):
        struct.pack_into("<HHI", stroke, 0, *self.pending, 0)
        return 1

    def interception_send(self, context, device, stroke, count):
        self.sent.append((device,) + struct.unpack_from("<HH", bytes(stroke)))
        return 1


class WindowsNumpadTest(unittest.IsolatedAsyncioTestCase):
    def use(self, fake):
        patch = mock.patch.object(wn, "_lib", fake)
        patch.start()
        self.addCleanup(patch.stop)
        return fake

    async def collect(self, numpad, count, timeout=2):
        got = []

        async def run():
            async for item in numpad.events():
                got.append(item)
                if len(got) == count:
                    return
        await asyncio.wait_for(run(), timeout)
        return got

    def test_ids_from_hardware_id(self):
        self.assertEqual(wn.parse_ids(DEVICES[3]), ("c0f4", "05f5"))
        self.assertIsNone(wn.parse_ids("ACPI\\PNP0303"))

    async def test_only_the_numpad_is_captured(self):
        fake = self.use(FakeInterception())
        numpad = wn.open_numpad(NUMPAD, grab=True)
        self.addCleanup(numpad.close)
        self.assertEqual(fake.filtered, {3}, "the main keyboard (1, 2) is never captured")
        self.assertEqual(numpad.spec, {"vendor": "c0f4", "product": "05f5", "name": DEVICES[3]})

    async def test_keys_names_and_held_key_reported_once(self):
        fake = self.use(FakeInterception([
            (3, 0x4C, 0), (3, 0x4C, 0), (3, 0x4C, 0),      # "5" held: Windows repeats the press
            (3, 0x4C, wn.KEY_UP),
            (3, 0x1C, wn.KEY_E0), (3, 0x1C, wn.KEY_E0 | wn.KEY_UP),  # numpad Enter
            (3, 0x0E, 0),                                  # the numpad's Backspace
            (3, 0x1E, 0),                                  # not a numpad key: ignored
            (3, 0x52, 0), (3, 0x52, wn.KEY_UP)]))
        numpad = wn.open_numpad(NUMPAD, grab=True)
        self.addCleanup(numpad.close)
        got = await self.collect(numpad, 7)
        self.assertEqual(got, [("5", True), ("5", False), ("Enter", True), ("Enter", False),
                               ("Backspace", True), ("0", True), ("0", False)])
        self.assertEqual(fake.sent, [], "grabbed: nothing from the numpad types")

    async def test_not_grabbed_still_types(self):
        fake = self.use(FakeInterception([(3, 0x4F, 0), (3, 0x4F, wn.KEY_UP)]))
        numpad = wn.open_numpad(NUMPAD, grab=False)
        self.addCleanup(numpad.close)
        await self.collect(numpad, 2)
        self.assertEqual(len(fake.sent), 2)

    async def test_unplugging_raises(self):
        fake = self.use(FakeInterception())
        numpad = wn.open_numpad(NUMPAD, grab=True)
        self.addCleanup(numpad.close)
        with mock.patch.object(wn, "PRESENCE_CHECK_SECONDS", 0.05):
            del fake.devices[3]
            with self.assertRaisesRegex(OSError, "unplugged"):
                await self.collect(numpad, 1)

    def test_missing_numpad(self):
        fake = self.use(FakeInterception())
        self.assertIsNone(wn.open_numpad({"vendor": "1234", "product": "5678"}, grab=True))
        self.assertEqual(fake.contexts, 0, "the context is released again")

    def test_detect_passes_keys_through(self):
        fake = self.use(FakeInterception([(2, 0x1E, 0), (3, 0x4F, 0)]))  # "a" on main, then numpad 1
        self.assertEqual(wn.detect_device(timeout=2)["vendor"], "c0f4")
        self.assertEqual([d for d, *_ in fake.sent], [2, 3], "every key still types while detecting")
        self.assertEqual(fake.contexts, 0)

    def test_close_releases_the_context(self):
        fake = self.use(FakeInterception())
        wn.open_numpad(NUMPAD, grab=True).close()
        self.assertEqual(fake.contexts, 0)
        self.assertEqual(fake.filtered, set())


if __name__ == "__main__":
    unittest.main()


class ServiceOnWindowsBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_000_and_keys_through_the_service(self):
        from numpadctl import daemon
        from tests.test_daemon import b, make_cfg
        fake = FakeInterception([(3, 0x52, 0), (3, 0x52, wn.KEY_UP)] * 3      # the 000 key: three 0s
                                + [(3, 0x4C, 0), (3, 0x4C, wn.KEY_UP)])        # then 5
        with mock.patch.object(wn, "_lib", fake), \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None):
            fired = []
            d = daemon.Daemon(run_action=lambda key, binding, slot: fired.append((key, binding["action"])))
            d.cfg = make_cfg({"000": {"tap": b("obs_save_replay")}, "5": {"tap": b("media_play_pause")}})
            numpad = wn.open_numpad(NUMPAD, grab=True)
            reader = asyncio.create_task(d.read(numpad))
            await asyncio.sleep(0.6)
            reader.cancel()
            numpad.close()
        self.assertEqual(fired, [("000", "obs_save_replay"), ("5", "media_play_pause")])
