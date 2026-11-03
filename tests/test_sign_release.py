"""tools/sign-release: what it refuses to sign, and that what it signs is what the updater checks."""

import base64
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from numpadctl import updater

TOOL = Path(__file__).resolve().parent.parent / "tools" / "sign-release"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@unittest.skipIf(shutil.which("git") is None or sys.platform == "win32", "needs git and a POSIX shell layout")
class SignReleaseTest(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.origin, self.repo = base / "origin.git", base / "repo"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(base, "clone", "-q", str(self.origin), str(self.repo))
        (self.repo / "tools").mkdir()
        shutil.copy(TOOL, self.repo / "tools" / "sign-release")
        (self.repo / "numpadctl").mkdir()
        (self.repo / "numpadctl" / "__init__.py").write_text('__version__ = "0.2.6"\n')
        self.key = base / "release.key"
        out = subprocess.run([sys.executable, str(self.repo / "tools" / "sign-release"), "keygen", str(self.key)],
                             check=True, capture_output=True, text=True).stdout.splitlines()
        self.public = out[-1]
        (self.repo / "numpadctl" / "release_key.py").write_text(f'PUBLIC_KEY = "{self.public}"\n')
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "0.2.6")
        git(self.repo, "tag", "v0.2.6")
        git(self.repo, "push", "-q", "origin", "main", "v0.2.6")

    def sign(self, tag="v0.2.6", answer=None, key=None, installer=None):
        return subprocess.run([sys.executable, str(self.repo / "tools" / "sign-release"), "sign", tag,
                               "--key", str(key or self.key), "--no-upload", "--installer", installer or "none"], cwd=self.repo,
                              input=(answer or tag) + "\n", capture_output=True, text=True)

    def files(self, done):
        folder = Path(done.stdout.split("Files: ")[1].split(",")[0]).parent
        self.addCleanup(shutil.rmtree, folder, True)
        return folder / "source.zip", folder / "release.sig"

    def test_what_it_signs_passes_the_updaters_check(self):
        done = self.sign()
        self.assertEqual(done.returncode, 0, done.stderr)
        archive, signature = self.files(done)
        signed = updater.verify_signature("v0.2.6", signature.read_bytes(), self.public)
        self.assertEqual(signed["commit"], git(self.repo, "rev-parse", "v0.2.6^{commit}"))
        self.assertEqual(signed["zip_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        names = zipfile.ZipFile(archive).namelist()
        self.assertIn("numpad-control-v0.2.6/numpadctl/__init__.py", names)
        self.assertFalse(any(".git/" in n for n in names))

    def test_the_windows_installer_hash_is_signed_when_there_is_one(self):
        setup = self.key.with_name("NumpadControl-Setup-0.2.6.exe")
        setup.write_bytes(b"MZ the installer CI built")
        done = self.sign(installer=str(setup))
        self.assertEqual(done.returncode, 0, done.stderr)
        _, signature = self.files(done)
        signed = updater.verify_signature("v0.2.6", signature.read_bytes(), self.public)
        self.assertEqual(signed["installer_sha256"], hashlib.sha256(setup.read_bytes()).hexdigest())
        self.assertIn("built by CI", done.stdout)

    def test_without_an_installer_the_signature_says_nothing_about_one(self):
        done = self.sign()
        _, signature = self.files(done)
        self.assertNotIn("installer_sha256", updater.verify_signature("v0.2.6", signature.read_bytes(), self.public))
        self.assertIn("Windows copies won't auto-update", done.stdout)

    def test_a_missing_installer_file_is_refused(self):
        done = self.sign(installer="/nonexistent/Setup.exe")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("isn't a file", done.stderr)

    def test_nothing_is_signed_without_typing_the_tag(self):
        done = self.sign(answer="yes")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not confirmed", done.stderr)

    def test_a_tag_that_was_moved_on_github_is_refused(self):
        (self.repo / "numpadctl" / "evil.py").write_text("x")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "later")
        git(self.repo, "tag", "-f", "v0.2.6")  # the local tag moves; GitHub still has the old one
        done = self.sign()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("on GitHub", done.stderr)

    def test_a_tag_that_does_not_match_the_version_is_refused(self):
        git(self.repo, "tag", "v0.2.7")
        git(self.repo, "push", "-q", "origin", "v0.2.7")
        done = self.sign("v0.2.7")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("says 0.2.6", done.stderr)

    def test_a_key_that_is_not_the_one_in_the_repo_is_refused(self):
        other = self.key.with_name("other.key")
        subprocess.run([sys.executable, str(self.repo / "tools" / "sign-release"), "keygen", str(other)],
                       check=True, capture_output=True)
        done = self.sign(key=other)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("isn't the one in numpadctl/release_key.py", done.stderr)

    def test_keygen_never_overwrites_a_key(self):
        again = subprocess.run([sys.executable, str(self.repo / "tools" / "sign-release"), "keygen", str(self.key)],
                               capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(oct(self.key.stat().st_mode & 0o777), "0o600")
        self.assertEqual(len(base64.b64decode(self.key.read_text().strip())), 32)


if __name__ == "__main__":
    unittest.main()
