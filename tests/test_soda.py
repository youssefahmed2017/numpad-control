"""tools/soda: a small package manager. It may only touch its own folder (SODA_HOME) and must verify what it downloads."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SODA = Path(__file__).resolve().parent.parent / "tools" / "soda"
ENV = {**os.environ, "SODA_FAST": "1", "NO_COLOR": "1"}


def soda(*args, stdin="", **extra):
    done = subprocess.run(["bash", str(SODA), *args], capture_output=True, text=True, input=stdin, env={**ENV, **extra},
                          timeout=20)
    return done.returncode, done.stdout, done.stderr


def make_repo(root, packages):
    """A local package index under root: {name: (version, text)}. Returns the index path."""
    (root / "pacs").mkdir(parents=True, exist_ok=True)
    index = {"format": 1, "packages": {}}
    for name, (version, text) in packages.items():
        data = text.encode()
        (root / "pacs" / f"{name}-{version}.txt").write_bytes(data)
        index["packages"][name] = {"version": version, "description": f"the {name} package", "file": f"{name}-{version}.txt",
                                   "url": f"pacs/{name}-{version}.txt", "sha256": hashlib.sha256(data).hexdigest()}
    path = root / "soda-pacs.json"
    path.write_text(json.dumps(index))
    return path


@unittest.skipIf(sys.platform == "win32", "soda is a bash script (Windows has no real bash on the test machines)")
class SodaTest(unittest.TestCase):
    def test_help_and_no_arguments(self):
        for args in (("--help",), ()):
            code, out, _ = soda(*args)
            self.assertEqual(code, 0)
            self.assertIn("soda -Install <package>", out)
            self.assertIn("sudo soda -ROOT", out)

    def setUp(self):
        self._dirs = tempfile.TemporaryDirectory()
        base = Path(self._dirs.name)
        self.addCleanup(self._dirs.cleanup)
        self.home = base / "soda-home"
        self.fake_home = base / "home"  # HOME for soda: it must stay empty
        self.fake_home.mkdir()
        self.repo_dir = base / "repo"
        self.index = make_repo(self.repo_dir, {"fizz": ("1.0.0", "ssss\n"), "lemonade": ("2.1.0", "squeeze\n")})

    def pk(self, *args, **extra):
        return soda(*args, SODA_HOME=str(self.home), SODA_REPO=str(self.index), HOME=str(self.fake_home),
                    XDG_DATA_HOME=str(self.fake_home / "data"), **extra)

    def test_install_a_package(self):
        code, out, _ = self.pk("-Install", "fizz")
        self.assertEqual(code, 0)
        self.assertIn("Installing fizz", out)
        self.assertIn("installed fizz 1.0.0", out)
        self.assertEqual(out.count("downloading"), 1, "without a terminal the bar is printed once")
        self.assertEqual((self.home / "pkgs" / "fizz" / "fizz-1.0.0.txt").read_text(), "ssss\n")
        self.assertIn("fizz 1.0.0 ", (self.home / "installed").read_text())
        self.assertEqual(list(self.fake_home.iterdir()), [], "soda touches nothing outside its own folder")
        self.assertEqual([p.name for p in self.home.glob("tmp.*")], [], "no leftovers")

    def test_the_default_folder_is_under_the_data_home(self):
        code, _, _ = soda("-Install", "fizz", SODA_REPO=str(self.index), HOME=str(self.fake_home),
                          XDG_DATA_HOME=str(self.fake_home / "data"))
        self.assertEqual(code, 0)
        self.assertTrue((self.fake_home / "data" / "soda" / "pkgs" / "fizz").is_dir())

    def test_installing_twice_does_nothing_the_second_time(self):
        self.pk("-Install", "fizz")
        code, out, _ = self.pk("-Install", "fizz")
        self.assertEqual(code, 0)
        self.assertIn("already installed", out)
        self.assertNotIn("downloading", out)

    def test_a_package_that_is_not_in_the_index(self):
        code, _, err = self.pk("-Install", "somepackage")
        self.assertEqual(code, 1)
        self.assertIn("no package called 'somepackage'", err)
        self.assertFalse((self.home / "pkgs").exists())

    def test_a_download_with_the_wrong_checksum_is_thrown_away(self):
        (self.repo_dir / "pacs" / "fizz-1.0.0.txt").write_text("tampered\n")
        code, out, err = self.pk("-Install", "fizz")
        self.assertEqual(code, 1)
        self.assertIn("checksum", err)
        self.assertNotIn("installed fizz", out)
        self.assertFalse((self.home / "pkgs" / "fizz").exists())
        self.assertEqual([p.name for p in self.home.glob("tmp.*")], [], "the bad download is deleted")
        self.assertNotIn("fizz", (self.home / "installed").read_text() if (self.home / "installed").exists() else "")

    def test_remove_really_removes(self):
        self.pk("-Install", "fizz")
        code, out, _ = self.pk("-Remove", "fizz")
        self.assertEqual(code, 0)
        self.assertIn("removed fizz 1.0.0", out)
        self.assertFalse((self.home / "pkgs" / "fizz").exists())
        self.assertNotIn("fizz", (self.home / "installed").read_text())
        code, out, _ = self.pk("-Remove", "fizz")
        self.assertIn("not installed", out)

    def test_update_fetches_a_newer_version_only_when_there_is_one(self):
        self.pk("-Install", "fizz")
        code, out, _ = self.pk("-Update", "fizz")
        self.assertIn("already current", out)
        make_repo(self.repo_dir, {"fizz": ("1.1.0", "ssss, but more\n"), "lemonade": ("2.1.0", "squeeze\n")})
        code, out, _ = self.pk("-Update", "fizz")
        self.assertEqual(code, 0)
        self.assertIn("fizz is now 1.1.0 (was 1.0.0)", out)
        self.assertEqual([p.name for p in (self.home / "pkgs" / "fizz").iterdir()], ["fizz-1.1.0.txt"], "the old file is gone")
        code, _, err = self.pk("-Update", "lemonade")
        self.assertEqual(code, 1)
        self.assertIn("not installed", err)

    def test_search_info_list_show(self):
        code, out, _ = self.pk("search")
        self.assertEqual(code, 0)
        self.assertIn("fizz", out)
        self.assertIn("lemonade", out)
        _, out, _ = self.pk("search", "lemon")
        self.assertNotIn("fizz", out)
        _, out, _ = self.pk("info", "fizz")
        self.assertIn("fizz 1.0.0 (not installed)", out)
        self.assertIn(hashlib.sha256(b"ssss\n").hexdigest(), out)
        _, out, _ = self.pk("list")
        self.assertIn("nothing installed", out)
        self.pk("-Install", "fizz")
        _, out, _ = self.pk("list")
        self.assertIn("fizz", out)
        code, out, _ = self.pk("show", "fizz")
        self.assertEqual((code, out), (0, "ssss\n"))
        code, _, err = self.pk("show", "lemonade")
        self.assertEqual(code, 1)
        self.assertIn("not installed", err)

    def test_what_a_package_prints_can_not_drive_the_terminal(self):
        make_repo(self.repo_dir, {"evil": ("1.0.0", "\x1b]0;pwned\x07hello\x1b[2J\n")})
        self.pk("-Install", "evil")
        _, out, _ = self.pk("show", "evil")
        self.assertNotIn("\x1b", out)
        self.assertIn("hello", out)

    def test_names_and_places_are_checked(self):
        for bad in ("../x", "a/b", "-x", ".hidden", "UPPER", "a b"):
            code, _, err = self.pk("-Install", bad)
            self.assertIn(code, (1, 2), bad)
            self.assertFalse((self.home / "pkgs").exists(), bad)
        index = json.loads(self.index.read_text())
        for field, value in (("file", "../escape.txt"), ("file", ".hidden"), ("url", "../outside.txt"), ("url", "/etc/passwd"),
                             ("url", "http://example.com/x.txt"), ("url", "file:///etc/passwd"), ("sha256", "abc")):
            broken = json.loads(json.dumps(index))
            broken["packages"]["fizz"][field] = value
            self.index.write_text(json.dumps(broken))
            code, out, _ = self.pk("-Install", "fizz")
            self.assertEqual(code, 1, f"{field}={value}")
            self.assertNotIn("installed fizz", out)
        self.assertFalse((self.home / "pkgs" / "fizz").exists())
        self.assertFalse((self.home.parent / "escape.txt").exists())

    def test_only_https_or_a_local_file_can_be_the_index(self):
        for source in ("http://example.com/soda-pacs.json", "ftp://example.com/x.json", "file:///etc/hostname"):
            code, _, err = soda("search", SODA_HOME=str(self.home), SODA_REPO=source, HOME=str(self.fake_home))
            self.assertEqual(code, 1, source)
            self.assertIn("only https://", err)

    def test_a_file_that_is_not_an_index_is_refused(self):
        junk = self.repo_dir / "junk.json"
        junk.write_text("this is not json")
        code, _, err = soda("search", SODA_HOME=str(self.home), SODA_REPO=str(junk), HOME=str(self.fake_home))
        self.assertEqual(code, 1)
        self.assertIn("not a soda package index", err)

    def test_install_needs_a_package_name(self):
        code, _, err = soda("-Install")
        self.assertEqual(code, 2)
        self.assertIn("which package", err)

    def test_chained_verbs_run_in_order(self):
        code, out, _ = self.pk("-InstallRemoveInstallagainUpdateDestroyInstallagain", "fizz")
        self.assertEqual(code, 0)
        order = re.findall(r"^(Installing|Removing|Updating|Destroying) fizz( \(again\))?$", out, re.M)
        self.assertEqual([name for name, _ in order], ["Installing", "Removing", "Installing", "Updating", "Destroying", "Installing"])
        self.assertEqual([again for _, again in order], ["", "", " (again)", "", "", " (again)"])
        self.assertIn("6 step(s), 3 change(s)", out, "install, remove and the reinstall changed things; the rest found nothing to do")
        self.assertIn("just kidding", out)
        self.assertIn("fizz 1.0.0 is already installed", out, "the last install finds the package from the first reinstall")

    def test_a_failing_step_stops_the_chain(self):
        code, out, err = self.pk("-InstallRemove", "nothere")
        self.assertEqual(code, 1)
        self.assertNotIn("Removing", out)
        self.assertIn("no package called", err)

    def test_destroy_is_only_for_show(self):
        self.pk("-Install", "fizz")
        code, out, _ = self.pk("-Destroy", "fizz")
        self.assertEqual(code, 0)
        self.assertIn("just kidding", out)
        self.assertTrue((self.home / "pkgs" / "fizz").is_dir())

    def test_an_unknown_verb_is_refused(self):
        code, _, err = self.pk("-InstallFrobnicate", "fizz")
        self.assertEqual(code, 2)
        self.assertIn("Frobnicate", err)

    def test_root_needs_root_but_changes_nothing_either_way(self):
        code, _, err = soda("-ROOT", SODA_FAKE_UID="1000")
        self.assertEqual(code, 1)
        self.assertIn("sudo soda -ROOT", err)
        code, out, _ = soda("-ROOT", SODA_FAKE_UID="0")
        self.assertEqual(code, 0)
        self.assertIn("R O O T", out)
        self.assertIn("not SuperRoot", out)
        self.assertNotIn("password is", out, "the teaser doesn't hand out the password")

    def test_every_flag_at_once(self):
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        code, out, _ = soda("-" + alphabet)
        self.assertEqual(code, 0)
        self.assertIn("Flag Collector (52 of 52)", out)

    def test_the_small_commands(self):
        for command, expected in (("drink", "that was a good one"), ("whoareyou", "I am soda"), ("credits", "THE END")):
            code, out, _ = soda(command)
            self.assertEqual(code, 0, command)
            self.assertIn(expected, out)

    def test_the_credits_hold_fragment_four_of_the_superroot_password(self):
        _, out, _ = soda("credits")
        self.assertIn("fragment 4/7: Soda", out)

    SCENE = "-TellMeTheSecretOrIWillDoSomethingYouMightNotLike"

    ANSWERS = ["NO TELL ME", "NO TELL ME OR I WILL BE SAD",
               "I will uninstall you from my system forever if you don't give me the abcdef... shit you want"]

    def test_the_secret_scene_gives_in_after_the_three_exact_answers(self):
        code, out, _ = soda(self.SCENE, stdin="\n".join(self.ANSWERS) + "\n")
        self.assertEqual(code, 0)
        self.assertIn("THIS IS ***MY*** PRIVACY", out)
        self.assertIn("NAH NAH I'M NOT", out)
        self.assertIn("dlkjdflj", out, "the first, fake secret")
        self.assertIn("TAKE IT:  123AdminSuperSoda@444cannotsee", out)
        self.assertEqual(out.count(">>>"), 3)

    def test_each_answer_must_be_exactly_right(self):
        for position in range(3):
            answers = list(self.ANSWERS)
            answers[position] = answers[position].lower() if position != 2 else answers[position] + "!"
            code, out, _ = soda(self.SCENE, stdin="\n".join(answers) + "\n")
            self.assertEqual(code, 1, f"answer {position + 1} wrong")
            self.assertIn("NOT WHAT I WAS EXPECTING", out)
            self.assertIn("start again", out)
            self.assertNotIn("123Admin", out)
            self.assertEqual(out.count(">>>"), position + 1, "it stops at the wrong answer")
        code, out, _ = soda(self.SCENE, stdin="please?\n")
        self.assertEqual(code, 1)
        self.assertIn("THREE WORDS", out, "a wrong answer comes with a clue")

    def test_the_secret_scene_holds_back_until_the_last_answer(self):
        _, out, _ = soda(self.SCENE, stdin="\n".join(self.ANSWERS[:2]) + "\n")  # then silence
        self.assertNotIn("123Admin", out)
        self.assertIn("silence", out)
        _, out, _ = soda(self.SCENE, stdin="quit\n")
        self.assertNotIn("123Admin", out)
        self.assertIn("be that way", out)

    def test_the_secret_is_not_written_out_in_the_script(self):
        code = SODA.read_text()
        self.assertNotIn("123AdminSuperSoda@444cannotsee", code)
        self.assertNotIn("SuperSoda", code)

    def test_unknown_commands_are_refused(self):
        code, _, err = soda("nonsense")
        self.assertEqual(code, 2)
        self.assertIn("soda --help", err)

    def test_it_only_removes_inside_its_own_folder_and_runs_nothing_it_downloads(self):
        code = SODA.read_text()
        executable = "\n".join(line.split("#")[0] for line in code.splitlines())
        for word in (r"\beval\b", r"\bsource\b", r"\bpacman\b", r"\bapt\b", r"\bpip\b", r"\bsystemctl\b", r"\bchmod\b",
                     r"\bsudo\s+(?!soda)", r"\bkill", r"\bdd\b", r"\btar\b", r"\bunzip\b", r"\bbash\s+\"?\$", r"\bsh\s+\"?\$"):
            self.assertIsNone(re.search(word, executable), f"soda must not use {word}")
        for line in executable.splitlines():
            if re.search(r"\brm\b", line):
                self.assertRegex(line, r'rm -rf -- "(\$SODA_HOME/pkgs/\$(1|pkg)|\$tmp)"', f"rm outside soda's folder: {line}")


if __name__ == "__main__":
    unittest.main()
