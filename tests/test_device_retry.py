"""A numpad reader that fails at once (e.g. Windows refusing the keyboard hook) is retried
with growing pauses, not thousands of times a second."""

import asyncio
import unittest
from unittest import mock

from numpadctl import daemon


class BrokenNumpad:
    names, spec = ["numpad"], {"vendor": "c0f4", "product": "05f5"}

    async def events(self):
        raise OSError("the numpad reader failed: Windows refused the keyboard hook (error 126)")
        yield

    def close(self):
        pass


class RetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_quick_failures_back_off(self):
        opened, sleeps = [], []
        real_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            await real_sleep(0)

        def open_numpad(spec, grab):
            opened.append(1)
            return BrokenNumpad()

        delays = (0.0011, 0.0012, 0.0013, 0.0014, 0.0015)  # distinct from the service's other pauses
        with mock.patch.object(daemon, "RETRY_DELAYS", delays), \
                mock.patch.object(daemon.numpad_input, "open_numpad", open_numpad), \
                mock.patch.object(daemon.asyncio, "sleep", fake_sleep), \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None), \
                self.assertLogs("numpadctl", "WARNING") as logs:
            d = daemon.Daemon(run_action=lambda *a: None)
            d.cfg = dict(d.cfg, pause_for_games=False)
            loop = asyncio.create_task(d._device_loop())
            while len(opened) < 8:
                await real_sleep(0)
            loop.cancel()
        retry_sleeps = [s for s in sleeps if s in delays]
        self.assertEqual(retry_sleeps[:6], [*delays, delays[-1]], "longer each time, up to the longest")
        self.assertLessEqual(len(logs.output), 3, "logged a few times, not every attempt")


if __name__ == "__main__":
    unittest.main()
