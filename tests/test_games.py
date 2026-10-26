"""Letting go of the numpad while a game with anti-cheat runs."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import daemon, games
from numpadctl.platform import processes


class GamesTest(unittest.TestCase):
    def test_known_games_and_anti_cheat_services(self):
        self.assertEqual(games.protected_game({}, {"explorer.exe", "valorant-win64-shipping.exe"}), "Valorant")
        self.assertEqual(games.protected_game({}, {"beservice.exe"}), "a game with BattlEye")
        self.assertIsNone(games.protected_game({}, {"explorer.exe", "obs64.exe"}))

    def test_extra_games_from_the_settings(self):
        cfg = {"protected_games": ["MyGame.exe"]}
        self.assertEqual(games.protected_game(cfg, {"mygame.exe"}), "MyGame.exe")

    def test_auto_means_windows_only(self):
        with mock.patch.object(games, "IS_WINDOWS", True):
            self.assertTrue(games.enabled({"pause_for_games": "auto"}))
        with mock.patch.object(games, "IS_WINDOWS", False):
            self.assertFalse(games.enabled({}))
            self.assertTrue(games.enabled({"pause_for_games": True}))
        self.assertFalse(games.enabled({"pause_for_games": False}))


class LinuxProcessesTest(unittest.TestCase):
    def test_names_from_proc_including_wine_games(self):
        proc = Path(tempfile.mkdtemp())
        for pid, cmdline, comm in [("1", b"/usr/lib/systemd/systemd\0--user\0", "systemd"),
                                   ("42", b"C:\\Games\\Valorant\\VALORANT-Win64-Shipping.exe\0", "VALORANT-Win64-S"),
                                   ("7", b"", "kworker/0:1")]:
            (proc / pid).mkdir()
            (proc / pid / "cmdline").write_bytes(cmdline)
            (proc / pid / "comm").write_text(comm + "\n")
        (proc / "self").mkdir()
        names = processes._linux(proc)
        self.assertIn("valorant-win64-shipping.exe", names)
        self.assertIn("systemd", names)
        self.assertNotIn("self", names)


class FakeNumpad:
    names, spec = ["numpad"], {"vendor": "c0f4", "product": "05f5"}

    def __init__(self):
        self.closed = False

    async def events(self):
        await asyncio.Event().wait()
        yield

    def close(self):
        self.closed = True


class ServicePausesForGamesTest(unittest.IsolatedAsyncioTestCase):
    async def test_numpad_is_let_go_while_the_game_runs_and_taken_back_after(self):
        running = [set()]
        opened = []

        def open_numpad(spec, grab):
            opened.append(FakeNumpad())
            return opened[-1]

        with mock.patch.object(daemon, "GAME_CHECK_SECONDS", 0.02), \
                mock.patch.object(daemon.processes, "running", lambda: running[0]), \
                mock.patch.object(daemon.numpad_input, "open_numpad", open_numpad), \
                mock.patch.object(daemon.actions, "notify") as notify, \
                mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None):
            d = daemon.Daemon(run_action=lambda *a: None)
            d.cfg = dict(d.cfg, pause_for_games=True)
            loop = asyncio.create_task(d._device_loop())
            await asyncio.sleep(0.1)
            self.assertEqual(len(opened), 1)
            self.assertIsNotNone(d.numpad)

            running[0] = {"fortniteclient-win64-shipping.exe"}
            await asyncio.sleep(0.15)
            self.assertTrue(opened[0].closed, "the numpad (and its keyboard hook) is let go")
            self.assertIsNone(d.numpad)
            self.assertEqual(d.paused_for, "Fortnite")
            self.assertEqual(d.status()["paused_for"], "Fortnite")
            self.assertEqual(len(opened), 1, "not reopened while the game runs")

            running[0] = set()
            await asyncio.sleep(0.15)
            self.assertIsNone(d.paused_for)
            self.assertEqual(len(opened), 2, "taken back after the game closed")
            loop.cancel()
        self.assertEqual([c.args[0] for c in notify.call_args_list], ["Numpad paused", "Numpad back"])

    async def test_off_means_no_checks(self):
        d = daemon.Daemon(run_action=lambda *a: None)
        d.cfg = dict(d.cfg, pause_for_games=False)
        with mock.patch.object(daemon.processes, "running") as running:
            self.assertIsNone(await d.protected_game())
        running.assert_not_called()


if __name__ == "__main__":
    unittest.main()
