"""setup.sh's use_latest_release: installs and updates go to the newest release, not to main."""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SETUP = Path(__file__).resolve().parent.parent / "setup.sh"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@unittest.skipIf(shutil.which("git") is None or shutil.which("bash") is None or sys.platform == "win32",
                 "needs git and bash")
class UseLatestReleaseTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.origin = self.base / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        self.commit("0.1.0", tag="v0.1.0")
        self.commit("0.2.0", tag="v0.2.0")
        self.commit("work after 0.2.0")
        function = re.search(r"^use_latest_release\(\) \{.*?^\}", SETUP.read_text(), re.S | re.M).group(0)
        self.script = ('note() { echo "$@"; }; warn() { echo "WARN $*"; }\n' + function +
                       '\nDRY_RUN=${DRY_RUN:-0}; DIR=$1; use_latest_release\n')

    def commit(self, text, tag=None):
        (self.origin / "file.txt").write_text(text)
        git(self.origin, "add", ".")
        git(self.origin, "commit", "-qm", text)
        if tag:
            git(self.origin, "tag", tag)

    def use(self, folder, dry_run="0"):
        done = subprocess.run(["bash", "-c", self.script, "x", str(folder)], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "DRY_RUN": dry_run})
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def text(self, folder):
        return (folder / "file.txt").read_text()

    def clone(self):
        folder = self.base / "install"
        git(self.base, "clone", "-q", str(self.origin), str(folder))
        return folder

    def test_a_fresh_clone_goes_back_to_the_newest_release(self):
        folder = self.clone()
        self.assertEqual(self.text(folder), "work after 0.2.0")
        self.assertIn("using release v0.2.0", self.use(folder))
        self.assertEqual(self.text(folder), "0.2.0")

    def test_an_old_install_moves_forward_to_a_new_release_only(self):
        folder = self.clone()
        self.use(folder)
        self.commit("0.3.0", tag="v0.3.0")
        self.commit("more unfinished work")
        self.use(folder)
        self.assertEqual(self.text(folder), "0.3.0")
        self.assertEqual(git(folder, "describe", "--tags", "--exact-match"), "v0.3.0")

    def test_a_copy_with_its_own_commits_is_left_alone(self):
        folder = self.clone()
        (folder / "mine.txt").write_text("mine")
        git(folder, "add", ".")
        git(folder, "commit", "-qm", "my change")
        self.assertIn("commits of its own", self.use(folder))
        self.assertTrue((folder / "mine.txt").exists())

    def test_no_release_yet_stays_where_it_is(self):
        for tag in ("v0.1.0", "v0.2.0"):
            git(self.origin, "tag", "-d", tag)
        folder = self.clone()
        self.assertIn("no release published yet", self.use(folder))
        self.assertEqual(self.text(folder), "work after 0.2.0")

    def test_a_dry_run_changes_nothing(self):
        folder = self.clone()
        self.assertIn("[dry-run]", self.use(folder, dry_run="1"))
        self.assertEqual(self.text(folder), "work after 0.2.0")

    def test_release_tags_are_picked_by_version_not_by_name(self):
        self.commit("0.10.0", tag="v0.10.0")
        self.commit("0.9.0", tag="v0.9.0")  # created later, but older
        folder = self.clone()
        self.use(folder)
        self.assertEqual(self.text(folder), "0.10.0", "0.10.0 is newer than 0.9.0, though it sorts before it as text")
        self.assertEqual(git(folder, "describe", "--tags", "--exact-match"), "v0.10.0")


if __name__ == "__main__":
    unittest.main()
