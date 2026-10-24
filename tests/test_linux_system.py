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


if __name__ == "__main__":
    unittest.main()
