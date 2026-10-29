"""tools/soda: a joke package manager. It must print things and change nothing."""

import os
import re
import subprocess
import unittest
from pathlib import Path

SODA = Path(__file__).resolve().parent.parent / "tools" / "soda"
ENV = {**os.environ, "SODA_FAST": "1", "NO_COLOR": "1"}


def soda(*args, **extra):
    done = subprocess.run(["bash", str(SODA), *args], capture_output=True, text=True, env={**ENV, **extra}, timeout=20)
    return done.returncode, done.stdout, done.stderr


class SodaTest(unittest.TestCase):
    def test_help_and_no_arguments(self):
        for args in (("--help",), ()):
            code, out, _ = soda(*args)
            self.assertEqual(code, 0)
            self.assertIn("soda -Install <package>", out)
            self.assertIn("sudo soda -ROOT", out)

    def test_install_a_package(self):
        code, out, _ = soda("-Install", "somepackage")
        self.assertEqual(code, 0)
        self.assertIn("Installing somepackage", out)
        self.assertIn("nothing was installed", out)
        self.assertEqual(out.count("downloading"), 1, "without a terminal the bar is printed once")

    def test_install_needs_a_package_name(self):
        code, _, err = soda("-Install")
        self.assertEqual(code, 2)
        self.assertIn("which package", err)

    def test_chained_verbs_run_in_order(self):
        code, out, _ = soda("-InstallRemoveInstallagainUpdateDestroyInstallagain", "somepackage")
        self.assertEqual(code, 0)
        order = re.findall(r"^(Installing|Removing|Updating|Destroying) somepackage( \(again\))?$", out, re.M)
        self.assertEqual([name for name, _ in order], ["Installing", "Removing", "Installing", "Updating", "Destroying", "Installing"])
        self.assertEqual([again for _, again in order], ["", "", " (again)", "", "", " (again)"])
        self.assertIn("6 step(s), 0 changes", out)
        self.assertIn("just kidding", out)

    def test_an_unknown_verb_is_refused(self):
        code, _, err = soda("-InstallFrobnicate", "x")
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

    def test_unknown_commands_are_refused(self):
        code, _, err = soda("nonsense")
        self.assertEqual(code, 2)
        self.assertIn("soda --help", err)

    def test_it_can_not_change_anything(self):
        """Soda only prints: no file, network or package commands anywhere in it."""
        code = SODA.read_text()
        executable = "\n".join(line.split("#")[0] for line in code.splitlines())
        for word in (r"\brm\b", r"\bmv\b", r"\bcp\b", r"\bdd\b", r"\bcurl\b", r"\bwget\b", r"\beval\b", r"\bpacman\b",
                     r"\bapt\b", r"\bpip\b", r"\bsystemctl\b", r"\bchmod\b", r"\bkill", r">\s*/", r">>"):
            self.assertIsNone(re.search(word, executable), f"soda must not use {word}")


if __name__ == "__main__":
    unittest.main()
