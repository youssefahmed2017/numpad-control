"""Automatic updates: finding a newer release, installing it from git or a zip, and the
service doing it by itself (or only saying so)."""

import asyncio
import base64
import hashlib
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


def make_key():
    """A throwaway release key: (private key, its public key as release_key.py stores it)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, base64.b64encode(public).decode()


def sign(private, tag="v0.2.0", commit="a" * 40, zip_sha256="b" * 64, **changes):
    """A release.sig, the way tools/sign-release makes it."""
    statement = json.dumps({"app": "numpad-pilot", "tag": tag, "commit": commit, "zip_sha256": zip_sha256,
                            **changes}, sort_keys=True, separators=(",", ":"))
    return json.dumps({"statement": statement,
                       "signature": base64.b64encode(private.sign(statement.encode())).decode()}).encode()


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

    def test_a_tag_must_be_exactly_a_version(self):
        # A tag ends up in a git ref and a download URL: nothing extra may ride along.
        for tag in ("v1.2.3\n", "v1.2.3 ", "v1.2.3/../x", "v١.٢.٣", "v1.2.3;id", "v1.2.3.zip", "../v1.2.3", "v1.2.3-rc1", "vv1.2.3", ""):
            self.assertIsNone(updater.parse(tag), repr(tag))

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


class SignatureTest(unittest.TestCase):
    def setUp(self):
        self.private, self.public = make_key()

    def test_a_release_signed_with_the_key_is_accepted(self):
        signed = updater.verify_signature("v0.2.0", sign(self.private), self.public)
        self.assertEqual((signed["commit"], signed["zip_sha256"]), ("a" * 40, "b" * 64))

    def test_someone_elses_key_is_refused(self):
        other, _ = make_key()
        with self.assertRaisesRegex(updater.UpdateError, "isn't signed"):
            updater.verify_signature("v0.2.0", sign(other), self.public)

    def test_a_changed_statement_is_refused(self):
        document = json.loads(sign(self.private))
        document["statement"] = document["statement"].replace("a" * 40, "c" * 40)  # point at other code
        with self.assertRaisesRegex(updater.UpdateError, "isn't signed"):
            updater.verify_signature("v0.2.0", json.dumps(document).encode(), self.public)

    def test_a_signature_for_another_release_cannot_be_replayed(self):
        with self.assertRaisesRegex(updater.UpdateError, "different release"):
            updater.verify_signature("v0.3.0", sign(self.private, tag="v0.2.0"), self.public)

    def test_another_app_with_the_same_key_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, "different release"):
            updater.verify_signature("v0.2.0", sign(self.private, app="something-else"), self.public)

    def test_a_release_signed_under_the_old_or_the_new_program_id_is_accepted(self):
        # 0.2.7 and older insist on "numpad-pilot" (what sign-release still writes); "numpad-control" is accepted too.
        for app in ("numpad-pilot", "numpad-control"):
            signed = updater.verify_signature("v0.2.0", sign(self.private, app=app), self.public)
            self.assertEqual(signed["tag"], "v0.2.0", app)

    def test_odd_commits_and_hashes_are_refused(self):
        for changes in ({"commit": "main"}, {"commit": "A" * 40}, {"zip_sha256": "xyz"}, {"commit": None}):
            with self.assertRaises(updater.UpdateError, msg=str(changes)):
                updater.verify_signature("v0.2.0", sign(self.private, **changes), self.public)

    def test_garbage_is_refused(self):
        for blob in (b"", b"not json", b"[]", b"{}", b'{"statement": 1, "signature": 2}',
                     b'{"statement": "{}", "signature": "!!!"}'):
            with self.assertRaises(updater.UpdateError, msg=repr(blob)):
                updater.verify_signature("v0.2.0", blob, self.public)

    def test_without_a_key_nothing_is_trusted(self):
        with mock.patch.object(updater.release_key, "PUBLIC_KEY", ""), \
                self.assertRaisesRegex(updater.UpdateError, "isn't signed"):
            updater.verify_signature("v0.2.0", sign(self.private))

    def test_an_unsigned_or_unreachable_release_is_never_installed(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(updater, "_download", side_effect=urllib.error.HTTPError("u", 404, "Not Found", {}, None)), \
                mock.patch.object(updater, "_update_git") as by_git, mock.patch.object(updater, "_update_zip") as by_zip, \
                self.assertRaisesRegex(updater.UpdateError, "no signature"):
            updater.install("v0.2.0", root)
        by_git.assert_not_called()
        by_zip.assert_not_called()

    def test_install_passes_on_only_what_was_signed(self):
        root = Path(tempfile.mkdtemp())
        blob = sign(self.private, commit="d" * 40, zip_sha256="e" * 64)
        with mock.patch.object(updater.release_key, "PUBLIC_KEY", self.public), \
                mock.patch.object(updater, "_download", return_value=blob), \
                mock.patch.object(updater, "_update_zip") as by_zip, mock.patch.object(updater, "_update_packages"), \
                mock.patch.object(updater, "_save_state"):
            updater.install("v0.2.0", root)
        by_zip.assert_called_once_with("v0.2.0", "e" * 64, root)
        (root / ".git").mkdir()
        with mock.patch.object(updater.release_key, "PUBLIC_KEY", self.public), \
                mock.patch.object(updater, "_download", return_value=blob), \
                mock.patch.object(updater, "_update_git") as by_git, mock.patch.object(updater, "_update_packages"), \
                mock.patch.object(updater, "_save_state"):
            updater.install("v0.2.0", root)
        by_git.assert_called_once_with("v0.2.0", "d" * 40, root)

    def test_a_download_bigger_than_the_limit_is_refused(self):
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(b"x" * 100)), \
                self.assertRaisesRegex(updater.UpdateError, "bigger than expected"):
            updater._download("https://example.com/x", 50)


class WindowsInstallerUpdateTest(unittest.TestCase):
    """Windows copies update by running the newer, signed Setup (a file swap can't replace what is in use)."""

    def setUp(self):
        self.private, self.public = make_key()
        self.root = Path(tempfile.mkdtemp())
        (self.root / updater.INSTALLER_MARKER).write_text("")
        self.state = Path(tempfile.mkdtemp())
        for patch in (mock.patch.object(updater.paths, "state_dir", lambda: self.state),
                      mock.patch.object(updater.release_key, "PUBLIC_KEY", self.public),
                      mock.patch.object(updater, "_save_state")):
            patch.start()
            self.addCleanup(patch.stop)

    def signature(self, **changes):
        return sign(self.private, tag="v0.2.7", **changes)

    def test_a_signed_installer_is_downloaded_checked_and_started(self):
        setup_bytes = b"MZ fake setup"
        with mock.patch.object(updater, "_download", return_value=self.signature(
                installer_sha256=hashlib.sha256(setup_bytes).hexdigest())), \
                mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(setup_bytes)), \
                mock.patch.object(updater.subprocess, "Popen") as popen, \
                mock.patch.object(updater, "_update_packages") as pip, mock.patch.object(updater, "_update_zip") as zipped:
            self.assertEqual(updater.install("v0.2.7", self.root), "installer")
        argv = popen.call_args.args[0]
        self.assertEqual(Path(argv[0]).name, "NumpadControl-Setup-0.2.7.exe")
        self.assertEqual(Path(argv[0]).read_bytes(), setup_bytes)
        self.assertEqual(argv[1:], ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"])
        pip.assert_not_called()  # the installer carries the packages; this Python has no pip
        zipped.assert_not_called()

    def test_a_swapped_installer_is_deleted_and_never_run(self):
        with mock.patch.object(updater, "_download", return_value=self.signature(installer_sha256="a" * 64)), \
                mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(b"MZ evil")), \
                mock.patch.object(updater.subprocess, "Popen") as popen, \
                self.assertRaisesRegex(updater.UpdateError, "isn't the file that was signed"):
            updater.install("v0.2.7", self.root)
        popen.assert_not_called()
        self.assertEqual(list((self.state / "updates").glob("*.exe")), [], "the bad file is not left lying around")

    def test_an_oversized_installer_is_refused_and_deleted(self):
        destination = self.state / "big.exe"
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(b"x" * 100)), \
                self.assertRaisesRegex(updater.UpdateError, "bigger than expected"):
            updater._download_file("https://example.com/x.exe", destination, 50, "0" * 64)
        self.assertFalse(destination.exists())

    def test_a_release_signed_without_an_installer_is_not_installed(self):
        with mock.patch.object(updater, "_download", return_value=self.signature()), \
                mock.patch.object(updater.subprocess, "Popen") as popen, \
                self.assertRaisesRegex(updater.UpdateError, "no signed Windows installer"):
            updater.install("v0.2.7", self.root)
        popen.assert_not_called()

    def test_the_installer_hash_must_be_a_hash(self):
        for bad in ("zzz", "A" * 64, "a" * 63, 5, None):
            with self.assertRaises(updater.UpdateError, msg=repr(bad)):
                updater.verify_signature("v0.2.7", self.signature(installer_sha256=bad), self.public)

    def test_older_installers_are_cleared_before_a_new_one_is_saved(self):
        (self.state / "updates").mkdir()
        old = self.state / "updates" / "NumpadControl-Setup-0.2.5.exe"
        old.write_bytes(b"old")
        with mock.patch.object(updater, "_download_file"), mock.patch.object(updater.subprocess, "Popen"):
            updater._update_installer("v0.2.7", "a" * 64)
        self.assertFalse(old.exists())

    def test_a_package_managers_copy_still_updates_only_through_it(self):
        (self.root / updater.PACKAGED_MARKER).write_text("")
        with mock.patch.object(updater.subprocess, "Popen") as popen, \
                self.assertRaisesRegex(updater.UpdateError, "package manager"):
            updater.install("v0.2.7", self.root)
        popen.assert_not_called()


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
        self.signed = subprocess.run(["git", "rev-parse", "v0.2.0^{commit}"], cwd=self.origin, check=True,
                                     capture_output=True, text=True).stdout.strip()
        (self.origin / "file.txt").write_text("unfinished")
        git(self.origin, "commit", "-qam", "work in progress after the release")
        self.unfinished = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.origin, check=True,
                                         capture_output=True, text=True).stdout.strip()

    def test_moves_to_the_release_not_to_newer_unfinished_work(self):
        updater._update_git("v0.2.0", self.signed, self.copy)
        self.assertEqual((self.copy / "file.txt").read_text(), "0.2.0")

    def test_a_tag_that_is_not_the_signed_commit_is_refused(self):
        # The tag on GitHub was moved to other code after the author signed the release.
        with self.assertRaisesRegex(updater.UpdateError, "isn't the commit that was signed"):
            updater._update_git("v0.2.0", self.unfinished, self.copy)
        self.assertEqual((self.copy / "file.txt").read_text(), "0.1.0", "nothing was merged")

    def test_a_copy_with_local_changes_is_left_alone(self):
        (self.copy / "file.txt").write_text("my own change")
        with self.assertRaisesRegex(updater.UpdateError, "local changes"):
            updater._update_git("v0.2.0", self.signed, self.copy)
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
            updater._update_zip("v0.2.0", hashlib.sha256(release).hexdigest(), self.root)
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
            updater._update_zip("v0.2.0", hashlib.sha256(release).hexdigest(), self.root)
        self.assertTrue((self.root / "numpadctl" / "old_module.py").exists(), "nothing was changed")

    def test_refuses_something_that_isnt_numpad_control(self):
        other = self.make_zip({"other-1.0/readme.txt": "hi"})
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(other)), \
                self.assertRaisesRegex(updater.UpdateError, "doesn't look like"):
            updater._update_zip("v0.2.0", hashlib.sha256(other).hexdigest(), self.root)

    def test_a_swapped_download_is_refused_before_anything_changes(self):
        signed_file = self.make_zip({"numpad-control-0.2.0/numpadctl/__init__.py": "good"})
        swapped = self.make_zip({"numpad-control-0.2.0/numpadctl/__init__.py": "evil"})
        with mock.patch.object(updater.urllib.request, "urlopen", return_value=Response(swapped)), \
                self.assertRaisesRegex(updater.UpdateError, "isn't the file that was signed"):
            updater._update_zip("v0.2.0", hashlib.sha256(signed_file).hexdigest(), self.root)
        self.assertTrue((self.root / "numpadctl" / "old_module.py").exists(), "nothing was changed")
        self.assertFalse((self.root / "numpadctl" / "__init__.py").exists())


class ServiceUpdatesTest(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, mode, tag="v9.0.0", install_error=None, install_result=None):
        d = daemon.Daemon(run_action=lambda *a: None, restart=mock.Mock(), quit=mock.Mock())
        d.cfg = dict(d.cfg, updates=mode)
        with mock.patch.object(daemon, "UPDATE_FIRST_CHECK", 0), \
                mock.patch.object(daemon, "UPDATE_LOOP_SECONDS", 0.01), \
                mock.patch.object(daemon.updater, "due", return_value=True), \
                mock.patch.object(daemon.updater, "check", return_value=tag), \
                mock.patch.object(daemon.updater, "install", side_effect=install_error, return_value=install_result) as install, \
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
        self.assertEqual(notify.call_args.args[0], "NumpadControl updated")

    async def test_the_windows_installer_takes_over_instead_of_restarting(self):
        d, install, notify = await self.run_loop("auto", install_result="installer")
        d.quit.assert_called_once()
        d.restart.assert_not_called()
        self.assertEqual(notify.call_args.args[0], "NumpadControl is updating")

    async def test_notify_only_says_so_once(self):
        d, install, notify = await self.run_loop("notify")
        install.assert_not_called()
        d.restart.assert_not_called()
        self.assertEqual(notify.call_count, 1)

    async def test_a_package_manager_install_only_says_so(self):
        with mock.patch.object(daemon.updater, "packaged", return_value=True):
            d, install, notify = await self.run_loop("auto")
        install.assert_not_called()
        d.restart.assert_not_called()
        self.assertIn("package manager", notify.call_args.args[1])

    async def test_off_does_nothing(self):
        d, install, notify = await self.run_loop("off")
        install.assert_not_called()
        notify.assert_not_called()

    def test_a_package_manager_install_is_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / updater.PACKAGED_MARKER).write_text("")
            self.assertTrue(updater.packaged(Path(d)))
            with self.assertRaises(updater.UpdateError):
                updater.install("v9.0.0", Path(d))

    async def test_a_failed_update_keeps_running(self):
        d, install, notify = await self.run_loop("auto", install_error=updater.UpdateError("local changes"))
        d.restart.assert_not_called()
        self.assertEqual(notify.call_args.args, ("NumpadControl couldn't update", "local changes"))

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
