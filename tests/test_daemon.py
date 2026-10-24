import asyncio
import unittest
from unittest import mock

from evdev import ecodes

from numpadctl import daemon

# Shrink the timings so the tests run fast.
FAST = dict(ZERO_BURST_WINDOW=0.02, HOLD_TIME=0.1, DOUBLE_TAP_TIME=0.08,
            REPEAT_DELAY=0.1, REPEAT_INTERVAL=0.03, RAPID_DELAY=0.2)


def b(action, **params):
    return {"action": action, "params": params}


def make_cfg(bindings, layer_bindings=None, layer_key=None, profiles=()):
    cfg = {"device": {"vendor": "c0f4", "product": "05f5"}, "grab": True,
           "feedback": True, "layer_key": layer_key, "obs": {},
           "profiles": [{"name": "Default", "match": "", "bindings": bindings,
                         "layer_bindings": layer_bindings or {}}, *profiles]}
    return cfg


class DaemonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.patches = [mock.patch.object(daemon, k, v) for k, v in FAST.items()]
        self.patches.append(mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None))
        for p in self.patches:
            p.start()
        self.fired = []
        self.d = daemon.Daemon(run_action=lambda key, binding, slot: self.fired.append(binding["action"]))

    def tearDown(self):
        self.d.reset()
        for p in self.patches:
            p.stop()

    async def tap(self, code, hold=0.0):
        self.d.on_event(code, True)
        await asyncio.sleep(hold)
        self.d.on_event(code, False)

    async def test_tap_fires_immediately(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        self.d.on_event(ecodes.KEY_KP5, True)
        self.assertEqual(self.fired, ["media_play_pause"])
        self.d.on_event(ecodes.KEY_KP5, False)

    async def test_hold_vs_tap(self):
        self.d.cfg = make_cfg({"5": {"tap": b("obs_start_recording"), "hold": b("obs_stop_recording")}})
        await self.tap(ecodes.KEY_KP5, hold=0.02)
        self.assertEqual(self.fired, ["obs_start_recording"])
        await self.tap(ecodes.KEY_KP5, hold=0.2)
        self.assertEqual(self.fired, ["obs_start_recording", "obs_stop_recording"])

    async def test_double_tap(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_next"), "double": b("media_previous")}})
        await self.tap(ecodes.KEY_KP5)
        await asyncio.sleep(0.02)
        await self.tap(ecodes.KEY_KP5)
        await asyncio.sleep(0.15)
        self.assertEqual(self.fired, ["media_previous"])
        await self.tap(ecodes.KEY_KP5)
        await asyncio.sleep(0.15)
        self.assertEqual(self.fired, ["media_previous", "media_next"])

    async def test_repeat_while_held(self):
        self.d.cfg = make_cfg({"-": {"tap": b("volume_down")}})
        await self.tap(ecodes.KEY_KPMINUS, hold=0.25)
        count = len(self.fired)
        self.assertGreaterEqual(count, 4)  # 1 + repeats every 0.03s after 0.1s
        await asyncio.sleep(0.1)
        self.assertEqual(len(self.fired), count, "must stop repeating on release")

    async def test_non_repeating_action_fires_once(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        await self.tap(ecodes.KEY_KP5, hold=0.25)
        self.assertEqual(self.fired, ["media_play_pause"])

    async def hold(self, binding, seconds):
        self.d.cfg = make_cfg({"5": {"hold": binding}})
        await self.tap(ecodes.KEY_KP5, hold=seconds)
        count = len(self.fired)
        await asyncio.sleep(0.1)
        self.assertEqual(len(self.fired), count, "must stop when the key is let go")
        return count

    async def test_hold_fires_once_before_the_rapid_delay(self):
        # hold time 0.1 + rapid delay 0.2: held 0.25 s is past the hold but before rapid-fire
        self.assertEqual(await self.hold(b("volume_down"), 0.25), 1)

    async def test_hold_rapid_fires_after_the_delay_for_safe_actions(self):
        self.assertGreaterEqual(await self.hold(b("volume_down"), 0.5), 4)

    async def test_rapid_fire_switched_off(self):
        self.assertEqual(await self.hold(dict(b("volume_down"), rapid=False), 0.5), 1)

    async def test_unsafe_actions_fire_once_unless_switched_on(self):
        self.assertEqual(await self.hold(b("open_browser"), 0.5), 1)
        self.fired.clear()
        self.assertGreaterEqual(await self.hold(dict(b("open_browser"), rapid=True), 0.5), 4)

    async def test_confirm_actions_never_rapid_fire(self):
        self.assertEqual(await self.hold(dict(b("shutdown"), rapid=True), 0.5), 1)

    async def test_slow_actions_do_not_pile_up(self):
        import concurrent.futures
        still_running = concurrent.futures.Future()  # never finishes, like a long macro
        calls = []
        self.d.run_action = lambda key, binding, slot: calls.append(slot) or still_running
        await self.hold(dict(b("macro", steps=[]), rapid=True), 0.5)
        self.assertEqual(calls, ["hold", "hold"], "the first run, then one rapid-fire run that never ends")

    async def test_000_burst_and_single_zero(self):
        self.d.cfg = make_cfg({"0": {"tap": b("media_stop")}, "000": {"tap": b("open_browser")}})
        for _ in range(3):
            self.d.on_event(ecodes.KEY_KP0, True)
            self.d.on_event(ecodes.KEY_KP0, False)
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["open_browser"])
        await self.tap(ecodes.KEY_KP0)
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["open_browser", "media_stop"])

    async def test_zero_can_be_held(self):
        self.d.cfg = make_cfg({"0": {"tap": b("media_stop"), "hold": b("lock_screen")}})
        await self.tap(ecodes.KEY_KP0, hold=0.2)
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["lock_screen"])

    async def test_layer_key(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_next")}},
                              layer_bindings={"5": {"tap": b("media_previous")}},
                              layer_key="Enter")
        await self.tap(ecodes.KEY_KP5)
        self.d.on_event(ecodes.KEY_KPENTER, True)
        await self.tap(ecodes.KEY_KP5)
        self.d.on_event(ecodes.KEY_KPENTER, False)
        await self.tap(ecodes.KEY_KP5)
        self.assertEqual(self.fired, ["media_next", "media_previous", "media_next"])

    async def test_profile_overrides_and_falls_back(self):
        obs_profile = {"name": "OBS", "match": "com.obsproject.Studio",
                       "bindings": {"5": {"tap": b("obs_toggle_recording")}}, "layer_bindings": {}}
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}, "6": {"tap": b("media_next")}},
                              profiles=[obs_profile])
        with mock.patch.object(daemon, "active_window_class", return_value="com.obsproject.Studio"):
            await self.tap(ecodes.KEY_KP5)
            await self.tap(ecodes.KEY_KP6)
        with mock.patch.object(daemon, "active_window_class", return_value="firefox"):
            await self.tap(ecodes.KEY_KP5)
        self.assertEqual(self.fired, ["obs_toggle_recording", "media_next", "media_play_pause"])

    async def test_capture_mode_runs_nothing_but_reports_keys(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        writer = mock.Mock()
        self.d.clients.add(writer)
        self.d.capturing.add(writer)
        await self.tap(ecodes.KEY_KP5)
        self.assertEqual(self.fired, [])
        self.assertIn(b'"key": "5"', writer.write.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()

    async def test_daemon_passes_the_slot_that_fired(self):
        slots = []
        self.d.run_action = lambda key, binding, slot: slots.append(slot)
        self.d.cfg = make_cfg({"5": {"tap": b("media_next"), "hold": b("shutdown"),
                                     "double": b("reboot")}})
        await self.tap(ecodes.KEY_KP5, hold=0.2)            # hold
        await self.tap(ecodes.KEY_KP5)                       # double tap
        await asyncio.sleep(0.02)
        await self.tap(ecodes.KEY_KP5)
        await asyncio.sleep(0.15)
        self.assertEqual(slots, ["hold", "double"])


class SocketTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = mock.patch.object(daemon, "SOCKET_PATH", Path(self.tmp.name) / "s.sock")
        self.path_patch.start()
        self.reload_patch = mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None)
        self.reload_patch.start()
        self.fired = []
        self.d = daemon.Daemon(run_action=lambda key, binding, slot: self.fired.append(binding["action"]))
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        await self.d.serve()
        self.reader, self.writer = await asyncio.open_unix_connection(str(daemon.SOCKET_PATH))

    async def asyncTearDown(self):
        self.writer.close()
        self.path_patch.stop()
        self.reload_patch.stop()
        self.tmp.cleanup()

    async def message(self):
        import json
        return json.loads(await asyncio.wait_for(self.reader.readline(), 2))

    async def send(self, message):
        import json
        self.writer.write((json.dumps(message) + "\n").encode())
        await self.writer.drain()
        await asyncio.sleep(0.02)

    async def test_status_then_key_events(self):
        self.assertEqual(await self.message(), {"event": "status", "connected": False, "devices": []})
        self.d.key_event("5", True)
        self.d.key_event("5", False)
        self.assertEqual(await self.message(), {"event": "key", "key": "5"})
        self.assertEqual(self.fired, ["media_play_pause"])

    async def test_learn_mode_blocks_actions_until_turned_off(self):
        await self.message()
        await self.send({"cmd": "capture", "on": True})
        self.d.key_event("5", True)
        self.d.key_event("5", False)
        self.assertEqual(self.fired, [])
        await self.send({"cmd": "capture", "on": False})
        self.d.key_event("5", True)
        self.d.key_event("5", False)
        self.assertEqual(self.fired, ["media_play_pause"])

    async def test_capture_ends_when_window_disconnects(self):
        await self.message()
        await self.send({"cmd": "capture", "on": True})
        self.writer.close()
        await asyncio.sleep(0.05)
        self.d.key_event("5", True)
        self.assertEqual(self.fired, ["media_play_pause"])

    async def test_detect_uses_next_key_on_our_device(self):
        await self.message()
        dev = mock.Mock()
        dev.name, dev.info.vendor, dev.info.product = "Usb KeyBoard", 0xc0f4, 0x05f5
        self.d.devices = [dev]
        with mock.patch.object(daemon, "detect_device", return_value=None):
            await self.send({"cmd": "detect"})
            self.d.key_event("7", True)
            self.assertEqual(self.fired, [], "the detect press must not run an action")
            await self.message()  # the key event
            self.assertEqual(await self.message(), {"event": "detected", "spec": {
                "vendor": "c0f4", "product": "05f5", "name": "Usb KeyBoard"}})

