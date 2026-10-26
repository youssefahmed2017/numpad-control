"""The driver-free Windows backend's decisions (KeySorter), without Windows: what the hook
holds back, which keys go to the service, and which are typed again unchanged.

Main keyboard = device 1 (it has its own number pad), numpad = device 3."""

import unittest
from unittest import mock

from numpadctl.platform import windows_rawinput as wr

NUMPAD, MAIN = 3, 1
SCAN = {"5": 0x4C, "0": 0x52, "Enter": 0x1C, "Backspace": 0x0E, "NumLock": 0x45, "a": 0x1E, "b": 0x30}


class KeySorterTest(unittest.TestCase):
    def sorter(self, grab=True):
        self.emitted, self.replayed = [], []
        return wr.KeySorter(lambda device: device == NUMPAD, grab, self.emitted.append,
                            lambda held: self.replayed.append((held.scan, held.up)))

    def press(self, s, device, key, up=False, extended=False, now=0.0):
        """One key as Windows reports it: first to the hook, then (unless it typed right away) its Raw Input."""
        blocked = s.hook(SCAN[key], extended, up, 0, now)
        s.raw(device, SCAN[key], extended, up)
        return blocked

    def test_numpad_keys_go_to_the_service_and_never_type(self):
        s = self.sorter()
        self.assertTrue(self.press(s, NUMPAD, "5"))
        self.assertTrue(self.press(s, NUMPAD, "5", up=True))
        self.assertTrue(self.press(s, NUMPAD, "Enter", extended=True))
        self.assertEqual(self.emitted, [("5", True), ("5", False), ("Enter", True)])
        self.assertEqual(self.replayed, [])
        self.assertFalse(s.held)

    def test_the_main_keyboards_number_pad_still_types(self):
        s = self.sorter()
        self.assertTrue(self.press(s, MAIN, "5"), "held back until its keyboard is known...")
        self.press(s, MAIN, "Backspace")
        self.assertEqual(self.replayed, [(SCAN["5"], False), (SCAN["Backspace"], False)], "...then typed again")
        self.assertEqual(self.emitted, [])

    def test_other_keys_type_right_away(self):
        s = self.sorter()
        self.assertFalse(s.hook(SCAN["a"], False, False, 0, 0.0))
        s.raw(MAIN, SCAN["a"], False, False)
        self.assertEqual((self.emitted, self.replayed), ([], []))

    def test_keys_after_a_held_one_stay_in_order(self):
        """Typing "5a" fast on the main keyboard: "a" must not overtake the held "5"."""
        s = self.sorter()
        self.assertTrue(s.hook(SCAN["5"], False, False, 0, 0.0))
        self.assertTrue(s.hook(SCAN["a"], False, False, 0, 0.0), "a waits behind 5")
        self.assertTrue(s.hook(SCAN["5"], False, True, 0, 0.0))
        self.assertTrue(s.hook(SCAN["b"], False, False, 0, 0.0))
        self.assertEqual(self.replayed, [])
        for scan, up in [(SCAN["5"], False), (SCAN["a"], False), (SCAN["5"], True), (SCAN["b"], False)]:
            s.raw(MAIN, scan, False, up)
        self.assertEqual(self.replayed, [(SCAN["5"], False), (SCAN["a"], False), (SCAN["5"], True),
                                         (SCAN["b"], False)])
        self.assertFalse(s.held)

    def test_a_numpad_key_between_typed_keys(self):
        s = self.sorter()
        s.hook(SCAN["5"], False, False, 0, 0.0)          # numpad 5
        s.hook(SCAN["a"], False, False, 0, 0.0)          # main a, waits behind it
        s.raw(NUMPAD, SCAN["5"], False, False)
        s.raw(MAIN, SCAN["a"], False, False)
        self.assertEqual(self.emitted, [("5", True)])
        self.assertEqual(self.replayed, [(SCAN["a"], False)])

    def test_raw_input_of_a_key_that_already_typed_is_ignored(self):
        """'a' typed right away; its Raw Input arrives after the hook already held a "5"."""
        s = self.sorter()
        s.hook(SCAN["a"], False, False, 0, 0.0)
        s.hook(SCAN["5"], False, False, 0, 0.0)
        s.raw(MAIN, SCAN["a"], False, False)
        self.assertEqual(len(s.held), 1)
        s.raw(NUMPAD, SCAN["5"], False, False)
        self.assertEqual(self.emitted, [("5", True)])

    def test_numlock_from_the_hook_matches_its_raw_input(self):
        """The hook marks NumLock as extended; Raw Input doesn't (no E0)."""
        s = self.sorter()
        s.hook(SCAN["NumLock"], True, False, 0x90, 0.0)
        s.raw(NUMPAD, SCAN["NumLock"], False, False)
        self.assertEqual(self.emitted, [("NumLock", True)])

    def test_not_grabbed_numpad_keys_reach_the_service_and_type(self):
        s = self.sorter(grab=False)
        self.press(s, NUMPAD, "5")
        self.assertEqual(self.emitted, [("5", True)])
        self.assertEqual(self.replayed, [(SCAN["5"], False)])

    def test_held_key_with_no_raw_input_is_typed_after_a_while(self):
        s = self.sorter()
        s.hook(SCAN["5"], False, False, 0, 0.0)
        s.hook(SCAN["a"], False, False, 0, 0.0)
        s.tick(wr.MATCH_TIMEOUT / 2)
        self.assertEqual(self.replayed, [])
        s.tick(wr.MATCH_TIMEOUT + 0.01)
        self.assertEqual(self.replayed, [(SCAN["5"], False), (SCAN["a"], False)])
        self.assertFalse(s.held)

    def test_a_held_numpad_key_is_reported_once(self):
        s = self.sorter()
        for _ in range(3):  # Windows repeats a held key as more presses
            self.press(s, NUMPAD, "5")
        self.press(s, NUMPAD, "5", up=True)
        self.assertEqual(self.emitted, [("5", True), ("5", False)])
        self.assertEqual(self.replayed, [], "the repeats don't type either")

    def test_an_unexpected_key_from_the_numpad_is_logged_once(self):
        s = self.sorter()
        with self.assertLogs("numpadctl", "WARNING") as logs:
            for _ in range(3):
                self.press(s, NUMPAD, "a")
        self.assertEqual(len(logs.output), 1)
        self.assertIn("0x1e", logs.output[0])
        self.assertEqual((self.emitted, self.replayed), ([], []))

    def test_000_key_bursts(self):
        s = self.sorter()
        for _ in range(3):
            self.press(s, NUMPAD, "0")
        self.assertEqual(self.emitted, [("0", True)] * 3)


class ListenerHookTest(unittest.TestCase):
    """The hook callback itself: which keys reach the sorter."""

    def call_hook(self, flags, extra=0, sorter_result=True):
        listener = wr._Listener(None, None, mock.Mock(**{"hook.return_value": sorter_result}))
        info = wr.KBDLLHOOKSTRUCT(vkCode=0x65, scanCode=SCAN["5"], flags=flags, time=0, dwExtraInfo=extra)
        api = mock.Mock(**{"CallNextHookEx.return_value": 0})
        with mock.patch.object(wr, "_api", return_value=api):
            result = listener._hook(wr.HC_ACTION, 0x100, wr.ctypes.addressof(info))
        return result, listener.sorter.hook

    def test_typed_numpad_key_is_held(self):
        result, hook = self.call_hook(0)
        self.assertEqual(result, 1)
        hook.assert_called_once()

    def test_injected_and_replayed_keys_pass(self):
        for flags, extra in [(wr.LLKHF_INJECTED, 0), (0, wr.REPLAYED)]:
            result, hook = self.call_hook(flags, extra)
            self.assertEqual(result, 0)
            hook.assert_not_called()

    def test_a_failing_sorter_lets_the_key_through(self):
        listener = wr._Listener(None, None, mock.Mock(**{"hook.side_effect": ZeroDivisionError}))
        info = wr.KBDLLHOOKSTRUCT(vkCode=0x65, scanCode=SCAN["5"], flags=0, time=0, dwExtraInfo=0)
        api = mock.Mock(**{"CallNextHookEx.return_value": 0})
        with mock.patch.object(wr, "_api", return_value=api), self.assertLogs("numpadctl", "ERROR"):
            self.assertEqual(listener._hook(wr.HC_ACTION, 0x100, wr.ctypes.addressof(info)), 0)


class HandleTypesTest(unittest.TestCase):
    """Regression: GetModuleHandleW's handle was cut to 32 bits, so Windows refused the hook (error 126)."""

    def test_handles_keep_their_full_size(self):
        fake = mock.MagicMock()
        with mock.patch.object(wr.ctypes, "WinDLL", create=True, return_value=fake), \
                mock.patch.object(wr, "_kernel32", None):
            wr._kernel()
        self.assertIs(fake.GetModuleHandleW.restype, wr.wintypes.HMODULE)
        self.assertEqual(wr.ctypes.sizeof(fake.GetModuleHandleW.restype), wr.ctypes.sizeof(wr.ctypes.c_void_p))


class StructureSizeTest(unittest.TestCase):
    @unittest.skipUnless(wr.ctypes.sizeof(wr.ctypes.c_void_p) == 8, "64-bit sizes")
    def test_sizes_match_windows_x64(self):
        self.assertEqual(wr.ctypes.sizeof(wr.KBDLLHOOKSTRUCT), 24)
        self.assertEqual(wr.ctypes.sizeof(wr.RAWINPUTHEADER), 24)
        self.assertEqual(wr.ctypes.sizeof(wr.RAWKEYBOARD), 16)
        self.assertEqual(wr.ctypes.sizeof(wr.RAWINPUTDEVICELIST), 16)
        self.assertEqual(wr.ctypes.sizeof(wr.INPUT), 40)


if __name__ == "__main__":
    unittest.main()
