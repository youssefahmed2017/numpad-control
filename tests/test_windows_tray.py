"""The Windows tray app's logic, tested on Linux with stand-ins for winreg and pystray."""

import asyncio
import sys
import threading
import types
import unittest
from unittest import mock

from numpadctl.platform import windows_tray as tray


class FakeWinreg:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = "HKCU", 2, 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, *args):
        assert (root, path) == ("HKCU", tray.RUN_KEY)
        return self._Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class FakeDaemon:
    def __init__(self):
        self.paused, self.numpad, self.cleaned_up = False, None, False

    async def main(self):
        try:
            await asyncio.sleep(3600)
        finally:
            self.cleaned_up = True


class FakeIcon:
    def __init__(self):
        self.title, self.menu_updates, self.stopped = "", 0, False

    def update_menu(self):
        self.menu_updates += 1

    def stop(self):
        self.stopped = True


class AutostartTest(unittest.TestCase):
    def test_on_and_off(self):
        reg = FakeWinreg()
        self.assertFalse(tray.autostart_enabled(reg))
        tray.set_autostart(True, reg)
        self.assertTrue(tray.autostart_enabled(reg))
        command = reg.values["Numpad Control"]
        self.assertIn("pythonw.exe", command)
        self.assertTrue(command.endswith('numpad-control.pyw"'))
        tray.set_autostart(False, reg)
        self.assertFalse(tray.autostart_enabled(reg))
        tray.set_autostart(False, reg)  # turning it off twice is fine


class TrayAppTest(unittest.TestCase):
    def make(self):
        opened = []
        app = tray.TrayApp(FakeDaemon(), open_file=opened.append)
        app.icon = FakeIcon()
        return app, opened

    def test_status_and_pause(self):
        app, _ = self.make()
        self.assertEqual(app.status_text(), "Numpad not found - plug it in")
        app.daemon.numpad = object()
        self.assertEqual(app.status_text(), "Numpad connected")
        app.toggle_pause()
        self.assertTrue(app.daemon.paused)
        self.assertEqual(app.status_text(), "Paused")
        self.assertEqual(app.icon.title, "Numpad Control - Paused")
        self.assertGreaterEqual(app.icon.menu_updates, 1, "the menu is rebuilt so it shows the change")
        app.toggle_pause()
        self.assertFalse(app.daemon.paused)

    def test_settings_window_file_and_log(self):
        app, opened = self.make()
        with mock.patch("numpadctl.platform.windows_system.spawn") as spawn:
            app.open_settings()
        self.assertEqual(spawn.call_args.args[-1], "gui", "opens the settings window")
        self.assertTrue(spawn.call_args.args[0].endswith("pythonw.exe"))
        app.edit_settings_file()
        app.show_log()
        self.assertEqual(opened[0].name, "config.json")
        self.assertEqual(opened[1].name, "numpad-control.log")

    def test_quit_stops_the_service_and_cleans_up(self):
        app, _ = self.make()
        service = threading.Thread(target=app.run_service)
        service.start()
        threading.Event().wait(0.2)
        app.quit()
        service.join(3)
        self.assertFalse(service.is_alive())
        self.assertTrue(app.daemon.cleaned_up, "the service's cleanup ran (numpad + connection released)")
        self.assertTrue(app.icon.stopped)

    def test_a_service_error_shows_in_the_status(self):
        class Broken(FakeDaemon):
            async def main(self):
                raise RuntimeError("the Interception driver isn't running")
        app = tray.TrayApp(Broken(), open_file=lambda p: None)
        app.icon = FakeIcon()
        with mock.patch("numpadctl.actions.notify") as notify:
            app.run_service()
        self.assertEqual(app.status_text(), "Stopped: the Interception driver isn't running")
        notify.assert_called_once()

    def test_menu(self):
        made = []
        fake_pystray = types.SimpleNamespace(
            Menu=type("Menu", (), {"SEPARATOR": "---", "__init__": lambda self, *items: made.extend(items)}),
            MenuItem=lambda text, action, **kw: (text if isinstance(text, str) else text(None), action, kw))
        app, _ = self.make()
        with mock.patch.dict(sys.modules, {"pystray": fake_pystray}), \
                mock.patch.object(tray, "autostart_enabled", return_value=False):
            app.menu()
        labels = [m[0] if isinstance(m, tuple) else m for m in made]
        self.assertEqual(labels, ["Numpad not found - plug it in", "---", "Settings…", "Edit settings file",
                                  "Pause", "Start at login", "Show log", "---", "Quit"])
        default = [m for m in made if isinstance(m, tuple) and m[2].get("default")]
        self.assertEqual(default[0][0], "Settings…", "a left click opens the settings window")


class ServicePauseTest(unittest.IsolatedAsyncioTestCase):
    async def test_paused_service_ignores_keys(self):
        from numpadctl import daemon
        from tests.test_daemon import b, make_cfg
        with mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None):
            fired = []
            d = daemon.Daemon(run_action=lambda key, binding, slot: fired.append(key))
            d.cfg = make_cfg({"5": {"tap": b("media_play_pause")}})
            d.paused = True
            d.on_key("5", True)
            d.on_key("5", False)
            d.paused = False
            d.on_key("5", True)
            d.on_key("5", False)
        self.assertEqual(fired, ["5"])


class QuitEarlyTest(unittest.TestCase):
    def test_quit_before_the_service_starts(self):
        app = tray.TrayApp(FakeDaemon(), open_file=lambda p: None)
        app.quit()
        service = threading.Thread(target=app.run_service)
        service.start()
        service.join(3)
        self.assertFalse(service.is_alive(), "the service doesn't keep running after an early Quit")


if __name__ == "__main__":
    unittest.main()
