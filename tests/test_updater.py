"""Automatic updates: finding a newer release, installing it from git or a zip, and the
service doing it by itself (or only saying so)."""

import asyncio
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

from numpadctl import daemon, updater


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args], cwd=cwd,
                   check=True, capture_output=True)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VersionTest(unittest.TestCase):
    def setUp(self):
        state = Path(tempfile.mkdtemp()) / "update.json"
        patch = mock.patch.object(updater, "_state_path", lambda: state)
        patch.start()
        self.addCleanup(patch.stop)

    def test_parse(self):
        self.assertEqual(updater.parse("v0.2.0"), (0, 2, 0))
        self.assertEqual(updater.parse("0.10.1"), (0, 10, 1))
        self.assertIsNone(updater.parse("v1.0-beta"))
        self.assertGreater(updater.parse("v0.10.0"), updater.parse("v0.9.9"))

    def test_only_a_newer_release_is_offered(self):
        with mock.patch.object(updater, "__version__", "0.2.0"):
            for latest, expected in [("v0.3.0", "v0.3.0"), ("v0.2.0", None), ("v0.1.0", None), (None, None)]:
                with mock.patch.object(updater, "latest_release", return_value=latest):
                    self.assertEqual(updater.check(), expected)

    def test_checks_once_a_day(self):
        self.assertTrue(updater.due())
        with mock.patch.object(updater, "latest_release", return_value=None):
            updater.check()
        self.assertFalse(updater.due())
        self.assertTrue(updater.due(now=updater._state()["checked"] + updater.CHECK_EVERY))

    def test_latest_release_from_github(self):
        with mock.patch.object(updater.urllib.request, "urlopen",
                               return_value=Response(json.dumps({"tag_name": "v0.4.0"}).encode())):
            self.assertEqual(updater.latest_release(), "v0.4.0")
        with mock.patch.object(updater.urllib.request, "urlopen",
                               return_value=Response(json.dumps({"tag_name": "nightly"}).encode())):
            self.assertIsNone(updater.latest_release(), "only plain version tags count")
        not_found = urllib.error.HTTPError(updater.LATEST_URL, 404, "Not Found", {}, None)
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=not_found):
            self.assertIsNone(updater.latest_release(), "no release published yet")
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(updater.latest_release())


@unittest.skipIf(shutil.which("git") is None, "needs git")
class GitUpdateTest(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.origin, self.copy = base / "origin", base / "copy"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        (self.origin / "file.txt").write_text("0.1.0")
        git(self.origin, "add", ".")
        git(self.origin, "commit", "-qm", "0.1.0")
        git(base, "clone", "-q", str(self.origin), str(self.copy))
        (self.origin / "file.txt").write_text("0.2.0")
        git(self.origin, "commit", "-qam", "0.2.0")
        git(self.origin, "tag", "v0.2.0")
        (self.origin / "file.txt").write_text("unfinished")
        git(self.origin, "commit", "-qam", "work in progress after the release")

    def test_moves_to_the_release_not_to_newer_unfinished_work(self):
        updater._update_git("v0.2.0", self.copy)
        self.assertEqual((self.copy / "file.txt").read_text(), "0.2.0")

    def test_a_copy_with_local_changes_is_left_alone(self):
        (self.copy / "file.txt").write_text("my own change")
        with self.assertRaisesRegex(updater.UpdateError, "local changes"):
            updater._update_git("v0.2.0", self.copy)
        self.assertEqual((self.copy / "file.txt").read_text(), "my own change")


class ZipUpdateTest(unittest.TestCase):
    def make_zip(self, files):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            for name, text in files.items():
                z.writestr(name, text)
        return data.getvalue()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "numpadctl").mkdir()
        (self.root / "numpadctl" / "old_module.py").write_text("old")
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "marker").write_text("keep me")
        (self.root / "README.md").write_text("old readme")

    def test_swaps_in_the_release_and_keeps_the_environment(self):
        release = self.make_zip({"numpad-control-0.2.0/numpadctl/__init__.py": "__version__ = '0.2.0'",
                                 "numpad-control-0.2.0/README.md": "new readme",
                                 "numpad-control-0.2.0/.venv/evil": "x"})
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(release)):
            updater._update_zip("v0.2.0", self.root)
        self.assertTrue((self.root / "numpadctl" / "__init__.py").exists())
        self.assertFalse((self.root / "numpadctl" / "old_module.py").exists(), "the folder was replaced whole")
        self.assertEqual((self.root / "README.md").read_text(), "new readme")
        self.assertEqual((self.root / ".venv" / "marker").read_text(), "keep me")
        self.assertFalse((self.root / ".venv" / "evil").exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".venv", "README.md", "numpadctl"])

    def test_refuses_a_zip_that_writes_outside_the_folder(self):
        release = self.make_zip({"numpad-control-0.2.0/numpadctl/x.py": "", "../../escape.txt": "x"})
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(release)), \
                self.assertRaisesRegex(updater.UpdateError, "unsafe"):
            updater._update_zip("v0.2.0", self.root)
        self.assertTrue((self.root / "numpadctl" / "old_module.py").exists(), "nothing was changed")

    def test_refuses_something_that_isnt_numpad_control(self):
        with mock.patch.object(updater.urllib.request, "urlopen",
                               return_value=Response(self.make_zip({"other-1.0/readme.txt": "hi"}))), \
                self.assertRaisesRegex(updater.UpdateError, "doesn't look like"):
            updater._update_zip("v0.2.0", self.root)


class ServiceUpdatesTest(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, mode, tag="v9.0.0", install_error=None):
        d = daemon.Daemon(run_action=lambda *a: None, restart=mock.Mock())
        d.cfg = dict(d.cfg, updates=mode)
        with mock.patch.object(daemon, "UPDATE_FIRST_CHECK", 0), \
                mock.patch.object(daemon, "UPDATE_LOOP_SECONDS", 0.01), \
                mock.patch.object(daemon.updater, "due", return_value=True), \
                mock.patch.object(daemon.updater, "check", return_value=tag), \
                mock.patch.object(daemon.updater, "install", side_effect=install_error) as install, \
                mock.patch.object(daemon.actions, "notify") as notify, \
                mock.patch.object(daemon.ipc, "stop_server"):
            task = asyncio.create_task(d.update_loop())
            await asyncio.sleep(0.1)
            task.cancel()
        return d, install, notify

    async def test_auto_installs_and_restarts(self):
        d, install, notify = await self.run_loop("auto")
        install.assert_called_once_with("v9.0.0")
        d.restart.assert_called_once()
        self.assertEqual(notify.call_args.args[0], "NumpadPilot updated")

    async def test_notify_only_says_so_once(self):
        d, install, notify = await self.run_loop("notify")
        install.assert_not_called()
        d.restart.assert_not_called()
        self.assertEqual(notify.call_count, 1)

    async def test_off_does_nothing(self):
        d, install, notify = await self.run_loop("off")
        install.assert_not_called()
        notify.assert_not_called()

    async def test_a_failed_update_keeps_running(self):
        d, install, notify = await self.run_loop("auto", install_error=updater.UpdateError("local changes"))
        d.restart.assert_not_called()
        self.assertEqual(notify.call_args.args, ("NumpadPilot couldn't update", "local changes"))

    async def test_waits_while_a_key_is_held(self):
        d = daemon.Daemon(run_action=lambda *a: None, restart=mock.Mock())
        d.presses["5"] = object()
        with mock.patch.object(daemon, "UPDATE_FIRST_CHECK", 0), \
                mock.patch.object(daemon.updater, "due", return_value=True), \
                mock.patch.object(daemon.updater, "check", return_value="v9.0.0"), \
                mock.patch.object(daemon.updater, "install") as install:
            task = asyncio.create_task(d.update_loop())
            await asyncio.sleep(0.05)
            task.cancel()
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
