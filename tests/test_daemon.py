import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock


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

    async def tap(self, key, hold=0.0):
        self.d.on_key(key, True)
        await asyncio.sleep(hold)
        self.d.on_key(key, False)

    async def test_tap_fires_immediately(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        self.d.on_key("5", True)
        self.assertEqual(self.fired, ["media_play_pause"])
        self.d.on_key("5", False)

    async def test_hold_vs_tap(self):
        self.d.cfg = make_cfg({"5": {"tap": b("obs_start_recording"), "hold": b("obs_stop_recording")}})
        await self.tap("5", hold=0.02)
        self.assertEqual(self.fired, ["obs_start_recording"])
        await self.tap("5", hold=0.2)
        self.assertEqual(self.fired, ["obs_start_recording", "obs_stop_recording"])

    async def test_double_tap(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_next"), "double": b("media_previous")}})
        await self.tap("5")
        await asyncio.sleep(0.02)
        await self.tap("5")
        await asyncio.sleep(0.15)
        self.assertEqual(self.fired, ["media_previous"])
        await self.tap("5")
        await asyncio.sleep(0.15)
        self.assertEqual(self.fired, ["media_previous", "media_next"])

    async def test_repeat_while_held(self):
        self.d.cfg = make_cfg({"-": {"tap": b("volume_down")}})
        await self.tap("-", hold=0.25)
        count = len(self.fired)
        self.assertGreaterEqual(count, 4)  # 1 + repeats every 0.03s after 0.1s
        await asyncio.sleep(0.1)
        self.assertEqual(len(self.fired), count, "must stop repeating on release")

    async def test_non_repeating_action_fires_once(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        await self.tap("5", hold=0.25)
        self.assertEqual(self.fired, ["media_play_pause"])

    async def hold(self, binding, seconds):
        self.d.cfg = make_cfg({"5": {"hold": binding}})
        await self.tap("5", hold=seconds)
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
            self.d.on_key("0", True)
            self.d.on_key("0", False)
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["open_browser"])
        await self.tap("0")
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["open_browser", "media_stop"])

    async def test_zero_can_be_held(self):
        self.d.cfg = make_cfg({"0": {"tap": b("media_stop"), "hold": b("lock_screen")}})
        await self.tap("0", hold=0.2)
        await asyncio.sleep(0.05)
        self.assertEqual(self.fired, ["lock_screen"])

    async def test_layer_key(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_next")}},
                              layer_bindings={"5": {"tap": b("media_previous")}},
                              layer_key="Enter")
        await self.tap("5")
        self.d.on_key("Enter", True)
        await self.tap("5")
        self.d.on_key("Enter", False)
        await self.tap("5")
        self.assertEqual(self.fired, ["media_next", "media_previous", "media_next"])

    async def test_profile_overrides_and_falls_back(self):
        obs_profile = {"name": "OBS", "match": "com.obsproject.Studio",
                       "bindings": {"5": {"tap": b("obs_toggle_recording")}}, "layer_bindings": {}}
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}, "6": {"tap": b("media_next")}},
                              profiles=[obs_profile])
        with mock.patch.object(daemon, "active_window_class", return_value="com.obsproject.Studio"):
            await self.tap("5")
            await self.tap("6")
        with mock.patch.object(daemon, "active_window_class", return_value="firefox"):
            await self.tap("5")
        self.assertEqual(self.fired, ["obs_toggle_recording", "media_next", "media_play_pause"])

    async def test_capture_mode_runs_nothing_but_reports_keys(self):
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        writer = mock.Mock()
        self.d.clients.add(writer)
        self.d.capturing.add(writer)
        await self.tap("5")
        self.assertEqual(self.fired, [])
        self.assertIn(b'"key": "5"', writer.write.call_args_list[-1].args[0])


    async def test_daemon_passes_the_slot_that_fired(self):
        slots = []
        self.d.run_action = lambda key, binding, slot: slots.append(slot)
        self.d.cfg = make_cfg({"5": {"tap": b("media_next"), "hold": b("shutdown"),
                                     "double": b("reboot")}})
        await self.tap("5", hold=0.2)            # hold
        await self.tap("5")                       # double tap
        await asyncio.sleep(0.02)
        await self.tap("5")
        await asyncio.sleep(0.15)
        self.assertEqual(slots, ["hold", "double"])


class SocketTest(unittest.IsolatedAsyncioTestCase):
    """Window <-> service messages, over the Linux Unix socket."""
    transport = "unix"

    async def asyncSetUp(self):
        import os
        import tempfile
        from pathlib import Path
        from numpadctl.platform import ipc, paths
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = mock.patch.object(paths, "runtime_dir", lambda: Path(self.tmp.name))
        self.path_patch.start()
        self.env_patch = mock.patch.dict(os.environ, {"NUMPADCTL_IPC": self.transport})
        self.env_patch.start()
        self.reload_patch = mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None)
        self.reload_patch.start()
        self.fired = []
        self.d = daemon.Daemon(run_action=lambda key, binding, slot: self.fired.append(binding["action"]))
        self.d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
        await self.d.serve()
        self.reader, self.writer = await asyncio.open_connection(sock=ipc.connect())

    async def asyncTearDown(self):
        self.writer.close()
        self.path_patch.stop()
        self.env_patch.stop()
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
        self.assertEqual(await self.message(), {"event": "status", "connected": False, "devices": [], "paused_for": None})
        self.d.key_event("5", True)
        self.d.key_event("5", False)
        self.assertEqual(await self.message(), {"event": "key", "key": "5", "label": "5", "unknown": False})
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

    async def test_raw_feed_shows_every_event_only_while_asked(self):
        class Fake:
            def __init__(self, items):
                self.items = items

            async def events(self):
                for item in self.items:
                    yield item
        await self.message()
        await self.send({"cmd": "raw", "on": True})
        await self.d.read(Fake([("0", True), ("0", False)]))
        first, second = await self.message(), await self.message()
        self.assertEqual((first["event"], first["key"], first["down"]), ("raw", "0", True))
        self.assertFalse(second["down"])
        await self.send({"cmd": "raw", "on": False})
        self.assertEqual(self.d.raw_clients, set())

    async def test_detect_uses_next_key_on_our_device(self):
        await self.message()
        self.d.numpad = SimpleNamespace(spec={"vendor": "c0f4", "product": "05f5", "name": "Usb KeyBoard"})
        with mock.patch.object(daemon.numpad_input, "detect_device", return_value=None):
            await self.send({"cmd": "detect"})
            self.d.key_event("7", True)
            self.assertEqual(self.fired, [], "the detect press must not run an action")
            await self.message()  # the key event
            self.assertEqual(await self.message(), {"event": "detected", "spec": {
                "vendor": "c0f4", "product": "05f5", "name": "Usb KeyBoard"}})


class SocketOverTCPTest(SocketTest):
    """The same messages over the localhost connection Windows will use."""
    transport = "tcp"

    async def test_wrong_key_is_rejected(self):
        import json
        from numpadctl.platform import ipc
        await self.message()  # the real client got its status
        info = json.loads(ipc._tcp_info_path().read_text())
        reader, writer = await asyncio.open_connection("127.0.0.1", info["port"])
        writer.write(b"not-the-key\n")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"", "connection closed, nothing sent")
        writer.close()


if __name__ == "__main__":
    unittest.main()
