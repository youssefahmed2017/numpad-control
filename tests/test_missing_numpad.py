"""A missing numpad gets a notification (once, after a few seconds), and so does its return."""

import asyncio
import unittest
from unittest import mock

from numpadctl import daemon
from tests.test_games import FakeNumpad


class MissingNumpadTest(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, plugged, seconds):
        real_sleep = asyncio.sleep
        with mock.patch.object(daemon, "MISSING_NOTICE", 0.05), \
                mock.patch.object(daemon.asyncio, "sleep", lambda s: real_sleep(min(s, 0.01))), \
                mock.patch.object(daemon.numpad_input, "open_numpad",
                                  lambda spec, grab: FakeNumpad() if plugged[0] else None), \
                mock.patch.object(daemon.actions, "notify") as notify, \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None):
            d = daemon.Daemon(run_action=lambda *a: None)
            d.cfg = dict(d.cfg, pause_for_games=False)
            loop = asyncio.create_task(d._device_loop())
            for step in seconds:
                await real_sleep(step[0])
                plugged[0] = step[1]
            loop.cancel()
        return [c.args[0] for c in notify.call_args_list]

    async def test_unplugged_then_plugged_in(self):
        said = await self.run_loop([False], [(0.2, True), (0.1, True)])
        self.assertEqual(said, ["Numpad not found", "Numpad connected"])

    async def test_a_quick_wobble_says_nothing(self):
        said = await self.run_loop([False], [(0.01, True), (0.1, True)])
        self.assertEqual(said, [])

    async def test_plugged_in_from_the_start_says_nothing(self):
        said = await self.run_loop([True], [(0.1, True)])
        self.assertEqual(said, [])


if __name__ == "__main__":
    unittest.main()
