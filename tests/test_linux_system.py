import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("tests the Linux code (Windows has its own tests)")
import unittest
from types import SimpleNamespace
from unittest import mock

from numpadctl.platform import linux_system


class FakeTools:
    """Pretends every tool is installed; swayosd's server can be up or down."""

    def __init__(self, swayosd_running=True):
        self.calls, self.swayosd_running = [], swayosd_running

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        ok = self.swayosd_running or argv[0] != "swayosd-client"
        return SimpleNamespace(returncode=0 if ok else 1, stdout="", stderr="")

    def which(self, name):
        return f"/usr/bin/{name}"


class LinuxSystemTest(unittest.TestCase):
    def tools(self, **kwargs):
        fake = FakeTools(**kwargs)
        patches = [mock.patch.object(linux_system.subprocess, "run", fake.run),
                   mock.patch.object(linux_system.shutil, "which", fake.which)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return fake

    def test_apps_start_in_their_own_scope(self):
        self.tools()
        with mock.patch.object(linux_system.subprocess, "Popen") as popen:
            linux_system.open_url("https://example.com")
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:5], ("systemd-run", "--user", "--scope", "--quiet", "--collect"))
        self.assertEqual(argv[-2:], ("xdg-open", "https://example.com"))
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_a_url_or_path_cannot_be_read_as_an_option(self):
        self.tools()
        with mock.patch.object(linux_system.subprocess, "Popen") as popen:
            for call in (linux_system.open_url, linux_system.open_path):
                with self.assertRaises(linux_system.SystemActionError):
                    call("--help")
        popen.assert_not_called()

    def test_notification_text_is_never_an_option(self):
        self.tools()
        with mock.patch.object(linux_system.subprocess, "run") as run:
            linux_system.notify("--hint=string:x:y", "body")
        self.assertEqual(run.call_args.args[0], ["notify-send", "-a", "NumpadControl", "--", "--hint=string:x:y", "body"])

    def test_volume_uses_swayosd_when_its_server_runs(self):
        fake = self.tools()
        linux_system.change_volume(+5)
        linux_system.change_volume(-5)
        self.assertEqual(fake.calls, [["swayosd-client", "--max-volume", "100", "--output-volume", "+5"],
                                      ["swayosd-client", "--output-volume", "-5"]])

    def test_volume_falls_back_to_wpctl(self):
        fake = self.tools(swayosd_running=False)
        linux_system.change_volume(+5)
        linux_system.toggle_mute(microphone=True)
        self.assertIn(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+"], fake.calls)
        self.assertIn(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"], fake.calls)

    def test_previous_track_is_spelled_per_tool(self):
        fake = self.tools(swayosd_running=False)
        linux_system.media("previous")
        self.assertEqual(fake.calls, [["swayosd-client", "--playerctl", "prev"], ["playerctl", "previous"]])

    def test_set_volume_sets_then_only_shows_the_popup(self):
        fake = self.tools()
        linux_system.set_volume(40)
        self.assertEqual(fake.calls, [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "40%"],
                                      ["swayosd-client", "--output-volume", "+0"]])

    def test_missing_tool_gives_a_clear_error(self):
        with mock.patch.object(linux_system.shutil, "which", return_value=None):
            with self.assertRaisesRegex(linux_system.SystemActionError, "'systemctl' is not installed"):
                linux_system.power("suspend")

    def test_key_names(self):
        self.assertTrue(linux_system.is_key("LEFTMETA"))
        self.assertTrue(linux_system.is_key("F5"))
        self.assertFalse(linux_system.is_key("BANANA"))


class DefaultBrowserTest(unittest.TestCase):
    """XFCE's xdg-settings can name a launcher that doesn't exist (brave.desktop for brave-browser.desktop)."""

    def ask(self, answers, installed):
        def run(*argv, **kwargs):
            return SimpleNamespace(stdout=answers.get(argv[0] + " " + argv[-1], "") + "\n")

        def launch(app_id):
            if app_id not in installed:
                raise linux_system.SystemActionError(f"app {app_id!r} is not installed")
            self.launched.append(app_id)
        self.launched = []
        return (mock.patch.object(linux_system, "_run", run), mock.patch.object(linux_system, "launch_app", launch),
                mock.patch.object(linux_system.shutil, "which", lambda name: "/usr/bin/" + name))

    def open(self, answers, installed):
        patches = self.ask(answers, installed)
        with patches[0], patches[1], patches[2]:
            linux_system.open_default_browser()

    def test_a_launcher_that_does_not_exist_falls_back_to_the_next_handler(self):
        self.open({"xdg-settings default-web-browser": "brave.desktop", "xdg-mime text/html": "brave-browser.desktop",
                   "xdg-mime x-scheme-handler/https": "xfce4-web-browser.desktop"},
                  installed={"brave-browser.desktop", "xfce4-web-browser.desktop"})
        self.assertEqual(self.launched, ["brave-browser.desktop"])

    def test_the_first_answer_is_used_when_it_is_fine(self):
        self.open({"xdg-settings default-web-browser": "firefox.desktop", "xdg-mime text/html": "brave-browser.desktop"},
                  installed={"firefox.desktop", "brave-browser.desktop"})
        self.assertEqual(self.launched, ["firefox.desktop"])

    def test_when_nothing_is_installed_the_first_complaint_is_reported(self):
        with self.assertRaisesRegex(linux_system.SystemActionError, "brave.desktop"):
            self.open({"xdg-settings default-web-browser": "brave.desktop", "xdg-mime text/html": "gone.desktop"},
                      installed=set())


if __name__ == "__main__":
    unittest.main()
