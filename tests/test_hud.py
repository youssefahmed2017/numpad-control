"""The key map overlay (Ghost HUD): what the service tells it, when the service runs it, and how it draws."""

import asyncio
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from numpadctl import actions, config, daemon  # noqa: E402


def b(action, **params):
    return {"action": action, "params": params}


def make_cfg(layer_bindings, layer_key=".", bindings=None, profiles=(), **extra):
    return {"device": {"vendor": "c0f4", "product": "05f5"}, "grab": True, "feedback": True, "layer_key": layer_key,
            "obs": {}, "profiles": [{"name": "Default", "match": "", "bindings": bindings or {},
                                     "layer_bindings": layer_bindings}, *profiles], **extra}


class SlotSummaryTest(unittest.TestCase):
    def test_the_press_action_is_the_text(self):
        self.assertEqual(actions.slot_summary({"tap": b("mic_mute")}), "Mute / unmute microphone")

    def test_extra_slots_show_as_a_count(self):
        self.assertEqual(actions.slot_summary({"tap": b("mic_mute"), "hold": b("volume_up"), "double": b("lock_screen")}),
                         "Mute / unmute microphone +2")

    def test_a_key_with_only_a_hold_or_double_says_so(self):
        self.assertEqual(actions.slot_summary({"hold": b("screenshot_full")}), "Hold: Full screen")
        self.assertEqual(actions.slot_summary({"double": b("lock_screen")}), "2×: Lock screen")

    def test_nothing_or_unknown_gives_nothing(self):
        self.assertEqual(actions.slot_summary({}), "")
        self.assertEqual(actions.slot_summary({"tap": b("no_such_action")}), "")


class HudSettingsTest(unittest.TestCase):
    def test_defaults_clamping_and_junk(self):
        self.assertEqual(config.hud_settings({}), {"enabled": True, "opacity": 90})
        self.assertEqual(config.hud_settings({"hud": {"enabled": False, "opacity": 5}}), {"enabled": False, "opacity": 30})
        self.assertEqual(config.hud_settings({"hud": {"opacity": 500}})["opacity"], 100)
        self.assertEqual(config.hud_settings({"hud": {"opacity": "lots"}})["opacity"], 90)
        self.assertEqual(config.hud_settings({"hud": "yes"}), {"enabled": True, "opacity": 90})


class LayerMessagesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patch = mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None)
        patch.start()
        self.addCleanup(patch.stop)
        self.d = daemon.Daemon(run_action=lambda *a: None)
        self.sent = []
        self.d.broadcast = self.sent.append

    def huds(self):
        return [m for m in self.sent if m.get("event") == "hud"]

    def test_holding_the_layer_key_shows_what_the_layer_does_and_letting_go_hides_it(self):
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}, "8": {"hold": b("screenshot_full")}},
                              hud={"enabled": True, "opacity": 60})
        self.d.on_key(".", True)
        self.d.on_key(".", True)  # a repeat of the same state says nothing more
        self.assertEqual(self.huds(), [{"event": "hud", "on": True, "opacity": 60,
                                        "keys": {"7": "Mute / unmute microphone", "8": "Hold: Full screen"}}])
        self.d.on_key(".", False)
        self.assertEqual(self.huds()[-1], {"event": "hud", "on": False, "opacity": 60, "keys": {}})
        self.assertEqual(len(self.huds()), 2)

    def test_other_keys_do_not_show_it(self):
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}})
        self.d.on_key("5", True)
        self.d.on_key("5", False)
        self.assertEqual(self.huds(), [])

    def test_the_focused_apps_profile_decides_what_is_shown(self):
        app = {"name": "OBS", "match": "obs", "bindings": {}, "layer_bindings": {"7": {"tap": b("volume_up")}}}
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}, "9": {"tap": b("lock_screen")}}, profiles=[app])
        with mock.patch.object(daemon, "active_window_class", lambda: "obs"):
            keys = self.d.hud_keys()
        self.assertEqual(keys, {"7": "Volume up", "9": "Lock screen"}, "the app's keys first, the default for the rest")
        with mock.patch.object(daemon, "active_window_class", lambda: "kitty"):
            self.assertEqual(self.d.hud_keys()["7"], "Mute / unmute microphone")

    def test_losing_the_numpad_while_the_layer_key_is_down_hides_it(self):
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}})
        self.d.on_key(".", True)
        self.d.reset()
        self.assertFalse(self.huds()[-1]["on"])
        self.d.reset()
        self.assertEqual(len(self.huds()), 2, "and only once")

    async def test_preview_shows_then_hides_unless_the_layer_key_is_held(self):
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}})
        with mock.patch.object(daemon, "HUD_PREVIEW_DELAY", 0.03), mock.patch.object(daemon, "HUD_PREVIEW_SECONDS", 0.05), \
                mock.patch.object(daemon.Daemon, "ensure_hud", lambda self: None):
            self.d.hud_preview()
            await asyncio.sleep(0.2)
        self.assertEqual([m["on"] for m in self.huds()], [True, False])

    async def test_preview_does_not_hide_a_key_map_you_are_holding_open(self):
        self.d.cfg = make_cfg({"7": {"tap": b("mic_mute")}})
        with mock.patch.object(daemon, "HUD_PREVIEW_DELAY", 0.02), mock.patch.object(daemon, "HUD_PREVIEW_SECONDS", 0.05), \
                mock.patch.object(daemon.Daemon, "ensure_hud", lambda self: None):
            self.d.hud_preview()
            self.d.layer_held = True
            await asyncio.sleep(0.2)
        self.assertEqual([m["on"] for m in self.huds()], [True], "no hide while the layer key is down")


class LateOverlayTest(unittest.IsolatedAsyncioTestCase):
    """An overlay that connects after the key map should already be showing is told right away."""

    async def connect(self, d):
        class Writer:
            def __init__(self):
                self.sent = []

            def write(self, data):
                self.sent.append(data)

            def is_closing(self):
                return False

            def close(self):
                pass

            async def drain(self):
                pass

        class Reader:
            async def readline(self):
                return b""
        writer = Writer()
        sent = []
        d.send = lambda w, message: sent.append(message)
        await d.handle_client(Reader(), writer)
        return sent

    async def test_a_new_client_hears_the_key_map_if_it_should_be_showing(self):
        with mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None):
            d = daemon.Daemon(run_action=lambda *a: None)
            d.cfg = make_cfg({"7": {"tap": b("mic_mute")}})
            self.assertEqual([m["event"] for m in await self.connect(d)], ["status"])
            d.layer_held = True
            self.assertEqual([m["event"] for m in await self.connect(d)], ["status", "hud"])
            d.layer_held = False
            d.hud_show_until = daemon.time.monotonic() + 5  # a preview
            self.assertEqual([m["event"] for m in await self.connect(d)], ["status", "hud"])


class FakeProcess:
    def __init__(self):
        self.alive, self.terminated = True, False

    def poll(self):
        return None if self.alive else 1

    def terminate(self):
        self.terminated, self.alive = True, False


class SupervisorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.spawned = []

        def spawn():
            self.spawned.append(FakeProcess())
            return self.spawned[-1]
        for patch in (mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None),
                      mock.patch.object(daemon, "spawn_hud", spawn),
                      mock.patch.object(daemon, "HUD_CHECK_SECONDS", 0.01)):
            patch.start()
            self.addCleanup(patch.stop)
        self.d = daemon.Daemon(run_action=lambda *a: None)

    async def watch(self, until=None, seconds=0.1):
        task = asyncio.create_task(self.d.manage_hud())
        for _ in range(int(seconds / 0.01)):
            await asyncio.sleep(0.01)
            if until and until():
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def test_it_runs_when_a_layer_key_is_set_and_stops_with_the_service(self):
        self.d.cfg = make_cfg({}, layer_key=".")
        await self.watch()
        self.assertEqual(len(self.spawned), 1)
        self.assertTrue(self.spawned[0].terminated, "it goes when the service goes")

    async def test_without_a_layer_key_or_when_switched_off_it_never_runs(self):
        self.d.cfg = make_cfg({}, layer_key=None)
        await self.watch()
        self.d.cfg = make_cfg({}, layer_key=".", hud={"enabled": False})
        await self.watch()
        self.assertEqual(self.spawned, [])

    async def test_turning_it_off_stops_it(self):
        self.d.cfg = make_cfg({}, layer_key=".")
        task = asyncio.create_task(self.d.manage_hud())
        await asyncio.sleep(0.05)
        self.d.cfg = make_cfg({}, layer_key=".", hud={"enabled": False})
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(self.spawned[0].terminated)
        self.assertEqual(len(self.spawned), 1)

    async def test_a_new_look_restarts_it(self):
        self.d.cfg = make_cfg({}, layer_key=".", accent="Orchid")
        task = asyncio.create_task(self.d.manage_hud())
        await asyncio.sleep(0.05)
        self.d.cfg = make_cfg({}, layer_key=".", accent="Blue")
        await asyncio.sleep(0.08)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(len(self.spawned), 2)
        self.assertTrue(self.spawned[0].terminated)

    async def test_one_that_keeps_dying_is_not_restarted_in_a_tight_loop(self):
        self.d.cfg = make_cfg({}, layer_key=".")
        task = asyncio.create_task(self.d.manage_hud())
        for _ in range(30):
            await asyncio.sleep(0.01)
            for process in self.spawned:
                process.alive = False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(len(self.spawned), 1, "it waits (5 s, then 10...) after dying at once")

    async def test_a_preview_starts_it_even_without_a_layer_key(self):
        self.d.cfg = make_cfg({}, layer_key=None)
        self.d.hud_preview_until = daemon.time.monotonic() + 5
        await self.watch()
        self.assertEqual(len(self.spawned), 1)

    async def test_a_preview_starts_it_at_once_not_at_the_next_check(self):
        self.d.cfg = make_cfg({}, layer_key=None)
        with mock.patch.object(daemon, "HUD_CHECK_SECONDS", 3600):  # the supervisor would take an hour
            self.d.hud_preview()
        self.assertEqual(len(self.spawned), 1)


class SpawnTest(unittest.TestCase):
    def test_on_linux_wayland_it_runs_through_xwayland_so_it_can_float_above_everything(self):
        with mock.patch.object(daemon.subprocess, "Popen") as popen, \
                mock.patch.object(daemon.actions, "refresh_session_env", lambda: True), \
                mock.patch.dict(daemon.os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-1"}), \
                mock.patch.object(daemon, "IS_WINDOWS", False):
            daemon.spawn_hud()
        argv, kwargs = popen.call_args
        self.assertEqual(argv[0][1:], ["-m", "numpadctl_ui.hud"])
        self.assertEqual(kwargs["env"]["QT_QPA_PLATFORM"], "xcb")
        self.assertTrue(kwargs["start_new_session"])

    def test_without_xwayland_it_leaves_the_platform_alone(self):
        with mock.patch.object(daemon.subprocess, "Popen") as popen, \
                mock.patch.object(daemon.actions, "refresh_session_env", lambda: True), \
                mock.patch.dict(daemon.os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=True), \
                mock.patch.object(daemon, "IS_WINDOWS", False):
            daemon.spawn_hud()
        self.assertNotIn("QT_QPA_PLATFORM", popen.call_args.kwargs["env"])


class HudWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from numpadctl_ui import theme, tokens
        cls.app = QApplication.instance() or QApplication([])
        theme.apply(cls.app, "dark", tokens.DEFAULT_ACCENT, "standard")

    def test_it_fades_in_with_the_keys_and_fades_out_and_hides(self):
        from PySide6.QtTest import QTest
        from numpadctl_ui import hud
        window = hud.Hud()
        self.addCleanup(window.deleteLater)
        window.on_message({"event": "hud", "on": True, "opacity": 80, "keys": {"7": "Mute"}})
        QTest.qWait(300)
        self.assertTrue(window.isVisible())
        self.assertEqual(window.alpha, 1.0)
        self.assertEqual((window.keys, window.opacity), ({"7": "Mute"}, 0.8))
        window.on_message({"event": "hud", "on": False})
        QTest.qWait(300)
        self.assertFalse(window.isVisible())

    def test_it_draws_every_key_without_errors(self):
        from numpadctl_ui import hud
        window = hud.Hud()
        self.addCleanup(window.deleteLater)
        window.show_keys({"7": "A very long action name that must be shortened", "Enter": "Lock screen"}, 90)
        window.set_alpha(1.0)
        picture = window.grab()
        self.assertEqual((picture.width(), picture.height()), (window.width(), window.height()))

    def test_it_never_takes_focus_or_clicks(self):
        from PySide6.QtCore import Qt
        from numpadctl_ui import hud
        window = hud.Hud()
        self.addCleanup(window.deleteLater)
        flags = window.windowFlags()
        for flag in (Qt.WindowTransparentForInput, Qt.WindowDoesNotAcceptFocus, Qt.WindowStaysOnTopHint, Qt.FramelessWindowHint):
            self.assertTrue(flags & flag)
        self.assertTrue(window.testAttribute(Qt.WA_ShowWithoutActivating))

    def test_it_quits_when_the_service_is_gone_for_good(self):
        from numpadctl_ui import hud
        window = hud.Hud()
        self.addCleanup(window.deleteLater)
        with mock.patch.object(hud.QApplication.instance(), "quit") as quit_app:
            for _ in range(hud.GONE_AFTER - 1):
                window.on_message({"event": "status", "running": False})
            quit_app.assert_not_called()
            window.on_message({"event": "status", "running": True})  # it came back: start counting again
            for _ in range(hud.GONE_AFTER):
                window.on_message({"event": "status", "running": False})
            quit_app.assert_called_once()


if __name__ == "__main__":
    unittest.main()
