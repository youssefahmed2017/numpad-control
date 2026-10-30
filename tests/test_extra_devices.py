"""Whole keyboards added as extra devices: their keys carry the device id, they run their own bindings,
they are let go on the escape chord, and the numpad is untouched."""

import asyncio
import unittest
from unittest import mock

from numpadctl import config, daemon, keys


class FakePad:
    def __init__(self, events):
        self._events, self.closed, self.ungrabbed = events, False, False

    async def events(self):
        for item in self._events:
            yield item
            await asyncio.sleep(0)
        await asyncio.sleep(3600)

    def ungrab(self):
        self.ungrabbed = True

    def close(self):
        self.closed = True


HP = {"id": "hp", "vendor": "03f0", "product": "0024", "name": "HP keyboard", "grab": True}


class KeyIdsTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(keys.split("hp:KEY_A"), ("hp", "KEY_A"))
        self.assertEqual(keys.split("5"), ("", "5"))
        self.assertEqual(keys.split(":"), ("", ":"))

    def test_labels_ignore_the_device(self):
        self.assertEqual(keys.label_for("hp:KEY_ESC"), "Esc")
        self.assertEqual(keys.label_for("hp:KEY_A"), "A")

    def test_every_key_of_a_configured_device_is_known(self):
        cfg = {"devices": [HP]}
        self.assertTrue(keys.known("hp:KEY_A", cfg))
        self.assertFalse(keys.known("other:KEY_A", cfg))
        self.assertFalse(keys.known("KEY_A", cfg))
        self.assertEqual(keys.display("hp:KEY_A", cfg), "A")

    def test_default_config_has_no_extra_devices(self):
        self.assertEqual(config.DEFAULT_CONFIG["devices"], [])


class DaemonDevicesTest(unittest.IsolatedAsyncioTestCase):
    def make(self, events, grab=True):
        fired = []
        d = daemon.Daemon(run_action=lambda key, binding, slot: fired.append((key, binding["action"], slot)))
        d.cfg = dict(d.cfg, devices=[dict(HP, grab=grab)], pause_for_games=False)
        d.cfg["profiles"][0]["bindings"] = {"hp:KEY_F1": {"tap": {"action": "mute", "params": {}}},
                                            "1": {"tap": {"action": "open_browser", "params": {}}}}
        pad = FakePad(events)
        self.notes = []  # the notifications sent
        return d, pad, fired

    async def run_devices(self, d, pad, until):
        with mock.patch.object(daemon.numpad_input, "open_device", lambda spec, grab: pad), \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None), \
                mock.patch.object(daemon.actions, "refresh_session_env", lambda: True), \
                mock.patch.object(daemon.actions, "notify", lambda *a: self.notes.append(a)), \
                mock.patch.object(daemon, "DEVICE_CHECK_SECONDS", 0.01):
            task = asyncio.create_task(d.manage_devices())
            for _ in range(300):
                if until():
                    break
                await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_a_key_of_the_keyboard_runs_its_binding(self):
        d, pad, fired = self.make([("hp:KEY_F1", True), ("hp:KEY_F1", False)])
        await self.run_devices(d, pad, lambda: fired)
        self.assertEqual(fired, [("hp:KEY_F1", "mute", "tap")])

    async def test_the_numpads_own_1_is_not_the_keyboards_1(self):
        d, pad, fired = self.make([("hp:KEY_1", True), ("hp:KEY_1", False)])
        await self.run_devices(d, pad, lambda: False)
        self.assertEqual(fired, [])

    async def test_the_escape_chord_gives_a_grabbed_keyboard_back(self):
        d, pad, fired = self.make([("hp:KEY_LEFTCTRL", True), ("hp:KEY_LEFTALT", True), ("hp:KEY_ESC", True),
                                   ("hp:KEY_F1", True), ("hp:KEY_F1", False)])
        await self.run_devices(d, pad, lambda: d.released)
        self.assertEqual(d.released, {"hp"})
        self.assertTrue(pad.ungrabbed)
        self.assertEqual(fired, [], "the chord and what follows are not actions")

    async def test_giving_a_keyboard_back_says_so_and_how_to_take_it_again(self):
        d, pad, _ = self.make([("hp:KEY_LEFTCTRL", True), ("hp:KEY_LEFTALT", True), ("hp:KEY_ESC", True)])
        await self.run_devices(d, pad, lambda: d.released)
        title, body = self.notes[0]
        self.assertEqual(title, "Keyboard given back")
        self.assertIn("HP keyboard", body, "the name you gave it, not its id")
        self.assertIn("remove it and add it again", body)

    async def test_the_chord_does_nothing_on_a_keyboard_that_is_not_grabbed(self):
        d, pad, fired = self.make([("hp:KEY_LEFTCTRL", True), ("hp:KEY_LEFTALT", True), ("hp:KEY_ESC", True)],
                                  grab=False)
        await self.run_devices(d, pad, lambda: False)
        self.assertEqual(d.released, set())

    async def test_a_missing_keyboard_is_waited_for_quietly(self):
        d, _, fired = self.make([])
        with mock.patch.object(daemon.numpad_input, "open_device", lambda spec, grab: None), \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None), \
                mock.patch.object(daemon, "DEVICE_CHECK_SECONDS", 0.01):
            task = asyncio.create_task(d.manage_devices())
            await asyncio.sleep(0.1)
            self.assertIsNone(d.extra["hp"]["pad"])
            self.assertEqual(d.status()["extra"], {"hp": {"connected": False, "released": False}})
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_removing_the_device_from_the_config_drops_it(self):
        d, pad, _ = self.make([])
        with mock.patch.object(daemon.numpad_input, "open_device", lambda spec, grab: pad), \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None), \
                mock.patch.object(daemon, "DEVICE_CHECK_SECONDS", 0.01):
            task = asyncio.create_task(d.manage_devices())
            while d.extra.get("hp", {}).get("pad") is not pad:
                await asyncio.sleep(0.01)
            d.cfg["devices"] = []
            while d.extra:
                await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(d.status()["extra"], {})


if __name__ == "__main__":
    unittest.main()
