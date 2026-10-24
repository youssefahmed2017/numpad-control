"""The Windows system actions, tested on Linux: SendInput calls are captured."""

import ctypes
import inspect
import unittest
from unittest import mock

from numpadctl.platform import linux_system, windows_system as ws


def keys(inputs):
    """(vk or scan code, up?, extended?/unicode?) per INPUT, for readable asserts."""
    out = []
    for item in inputs:
        ki = item.u.ki
        if ki.dwFlags & ws.KEYEVENTF_UNICODE:
            out.append(("char", chr(ki.wScan) if ki.wScan < 0xD800 else ki.wScan, bool(ki.dwFlags & ws.KEYEVENTF_KEYUP)))
        else:
            out.append((ki.wVk, bool(ki.dwFlags & ws.KEYEVENTF_KEYUP), bool(ki.dwFlags & ws.KEYEVENTF_EXTENDEDKEY)))
    return out


class WindowsSystemTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        patch = mock.patch.object(ws, "_send_inputs", lambda inputs: self.sent.append(keys(inputs)))
        patch.start()
        self.addCleanup(patch.stop)

    def test_same_functions_as_linux(self):
        public = lambda m: {n for n, f in vars(m).items()
                            if inspect.isfunction(f) and not n.startswith("_") and f.__module__ == m.__name__}
        self.assertEqual(public(ws), public(linux_system))

    def test_structures_have_windows_sizes(self):
        self.assertEqual(ctypes.sizeof(ws.KEYBDINPUT), 24)
        self.assertEqual(ctypes.sizeof(ws.INPUT), 40)

    def test_key_combo_held_then_released_in_reverse(self):
        ws.press_keys([["LEFTMETA", "Q"], ["ENTER"]])
        self.assertEqual(self.sent, [[(0x5B, False, True), (ord("Q"), False, False),
                                      (ord("Q"), True, False), (0x5B, True, True),
                                      (0x0D, False, False), (0x0D, True, False)]])

    def test_same_key_names_as_linux_for_the_common_keys(self):
        for name in ("LEFTCTRL", "LEFTSHIFT", "LEFTALT", "LEFTMETA", "ENTER", "DOWN", "F5", "Q", "1"):
            with self.subTest(name):
                self.assertTrue(ws.is_key(name) and linux_system.is_key(name))
        self.assertFalse(ws.is_key("BANANA"))

    def test_type_text_unicode_newline_and_emoji(self):
        ws.type_text("Hi é\n😀")
        sent = self.sent[0]
        self.assertEqual(sent[:6], [("char", "H", False), ("char", "H", True), ("char", "i", False),
                                    ("char", "i", True), ("char", " ", False), ("char", " ", True)])
        self.assertIn(("char", "é", False), sent)
        self.assertIn((0x0D, False, False), sent, "a newline presses Enter")
        self.assertEqual([k for k in sent if k[0] == "char" and isinstance(k[1], int) and not k[2]],
                         [("char", 0xD83D, False), ("char", 0xDE00, False)], "emoji as a surrogate pair")

    def test_media_and_volume_keys(self):
        ws.media("previous")
        ws.change_volume(+5)
        ws.change_volume(-5)
        self.assertEqual(self.sent[0], [(0xB1, False, True), (0xB1, True, True)])
        self.assertEqual(len(self.sent[1]), 4, "+5% = 2 presses of Windows' 2% steps")
        self.assertEqual(self.sent[2][0], (0xAE, False, True))

    def test_set_volume_goes_to_zero_then_up(self):
        ws.set_volume(40)
        down, up = self.sent
        self.assertEqual(len(down), 2 * 50)
        self.assertEqual(len(up), 2 * 20)
        self.assertEqual(up[0], (0xAF, False, True))

    def test_microphone_mute_says_not_yet(self):
        with self.assertRaisesRegex(ws.SystemActionError, "isn't supported on Windows yet"):
            ws.toggle_mute(microphone=True)

    def test_power(self):
        with mock.patch.object(ws.subprocess, "run") as run:
            ws.power("reboot")
        self.assertEqual(run.call_args.args[0], ["shutdown", "/r", "/t", "0"])

    def test_open_url_and_missing_app(self):
        with mock.patch.object(ws.os, "startfile", create=True) as startfile:
            ws.open_url("https://example.com")
        startfile.assert_called_once_with("https://example.com")
        with self.assertRaisesRegex(ws.SystemActionError, "wasn't found"):
            ws.launch_app(r"C:\nope\nothing.exe")

    def test_notification_text_goes_through_the_environment(self):
        with mock.patch.object(ws.subprocess, "Popen") as popen:
            ws.notify("Live!", "Went live at 20:00; 'quotes' $(x)")
        env = popen.call_args.kwargs["env"]
        self.assertEqual((env["NUMPAD_TITLE"], env["NUMPAD_BODY"]), ("Live!", "Went live at 20:00; 'quotes' $(x)"))
        self.assertNotIn("Went live", " ".join(popen.call_args.args[0]), "never pasted into the script")


if __name__ == "__main__":
    unittest.main()
