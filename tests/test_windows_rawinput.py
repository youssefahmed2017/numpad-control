"""The driver-free Windows backend.

KeyRouter's decisions and the window's handling are tested everywhere (no Windows calls).
The end-to-end test at the bottom runs only on Windows (GitHub's Windows runner): it
loads the real numpadhook.dll, installs the real hook, presses keys with SendInput and
checks which ones a window receives.

Main keyboard = device 1 (it has its own number pad), numpad = device 3."""

import ctypes
import sys
import threading
import time
import unittest
from unittest import mock

from numpadctl.platform import windows_rawinput as wr

NUMPAD, MAIN = 3, 1
SCAN = {"5": 0x4C, "0": 0x52, "Enter": 0x1C, "-": 0x4A, "+": 0x4E, "/": 0x35, "*": 0x37,
        "NumLock": 0x45, "a": 0x1E}


class KeyRouterTest(unittest.TestCase):
    def router(self, grab=True):
        self.emitted = []
        return wr.KeyRouter(lambda device: device == NUMPAD, grab, self.emitted.append)

    def test_numpad_keys_reach_the_service_and_are_blocked(self):
        r = self.router()
        for key, e0 in [("5", False), ("-", False), ("+", False), ("/", True), ("*", False), ("NumLock", False)]:
            r.raw(NUMPAD, SCAN[key], e0, False, 1.0)
            self.assertTrue(r.should_block(SCAN[key], False, 1.0), key)
        self.assertEqual(self.emitted, [("5", True), ("-", True), ("+", True), ("/", True), ("*", True),
                                        ("NumLock", True)])

    def test_the_main_keyboards_number_pad_still_types(self):
        r = self.router()
        r.raw(MAIN, SCAN["5"], False, False, 1.0)
        self.assertFalse(r.should_block(SCAN["5"], False, 1.0))
        self.assertEqual(self.emitted, [])

    def test_the_last_keyboard_decides(self):
        """Numpad Enter, then the main keyboard's Enter (same scan code): only the first is blocked."""
        r = self.router()
        r.raw(NUMPAD, SCAN["Enter"], True, False, 1.0)
        self.assertTrue(r.should_block(SCAN["Enter"], False, 1.0))
        r.raw(MAIN, SCAN["Enter"], False, False, 1.1)
        self.assertFalse(r.should_block(SCAN["Enter"], False, 1.1))

    def test_presses_and_releases_are_tracked_apart(self):
        r = self.router()
        r.raw(NUMPAD, SCAN["5"], False, False, 1.0)
        self.assertFalse(r.should_block(SCAN["5"], True, 1.0), "the release hasn't come from the numpad yet")
        r.raw(NUMPAD, SCAN["5"], False, True, 1.1)
        self.assertTrue(r.should_block(SCAN["5"], True, 1.1))
        self.assertEqual(self.emitted, [("5", True), ("5", False)])

    def test_keys_sent_by_programs_are_never_blocked(self):
        """Device 0 = SendInput (our own actions, AutoHotkey...): it overrides an earlier numpad press."""
        r = self.router()
        r.raw(NUMPAD, SCAN["5"], False, False, 1.0)
        r.raw(0, SCAN["5"], False, False, 1.1)
        self.assertFalse(r.should_block(SCAN["5"], False, 1.1))
        self.assertEqual(self.emitted, [("5", True)])

    def test_an_old_answer_expires(self):
        r = self.router()
        r.raw(NUMPAD, SCAN["5"], False, False, 1.0)
        self.assertFalse(r.should_block(SCAN["5"], False, 1.0 + wr.FRESH + 1))

    def test_not_grabbed_reports_but_never_blocks(self):
        r = self.router(grab=False)
        r.raw(NUMPAD, SCAN["5"], False, False, 1.0)
        self.assertEqual(self.emitted, [("5", True)])
        self.assertFalse(r.should_block(SCAN["5"], False, 1.0))

    def test_a_held_key_is_reported_once_but_every_repeat_is_blocked(self):
        r = self.router()
        for t in (1.0, 1.03, 1.06):
            r.raw(NUMPAD, SCAN["5"], False, False, t)
            self.assertTrue(r.should_block(SCAN["5"], False, t))
        self.assertEqual(self.emitted, [("5", True)])

    def test_000_key_bursts(self):
        r = self.router()
        for t in (1.0, 1.005, 1.01):
            r.raw(NUMPAD, SCAN["0"], False, False, t)
        self.assertEqual(self.emitted, [("0", True)] * 3)

    def test_an_unexpected_key_from_the_numpad_is_logged_once(self):
        r = self.router()
        with self.assertLogs("numpadctl", "WARNING") as logs:
            for t in (1.0, 2.0):
                r.raw(NUMPAD, SCAN["a"], False, False, t)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("0x1e", logs.output[0])
        self.assertEqual(self.emitted, [])

    def test_hook_lparam(self):
        down = (0x4C << 16) | 1
        up = down | (1 << 30) | (1 << 31)
        self.assertEqual(wr._query_key(0x65, down), (0x4C, False))
        self.assertEqual(wr._query_key(0x65, up), (0x4C, True))


class WindowHandlingTest(unittest.TestCase):
    """The window procedure's part, with Windows mocked out."""

    def listener(self, raws=()):
        self.emitted = []
        router = wr.KeyRouter(lambda device: device == NUMPAD, True, self.emitted.append)
        listener = wr._Listener(lambda *raw: False, lambda now: False, router)
        pending = list(raws)  # Raw Input waiting in the queue when the DLL asks
        api = mock.Mock(**{"PeekMessageW.side_effect": lambda *a: 1 if pending else 0,
                           "DefWindowProcW.return_value": 0})
        return listener, api, lambda lparam: pending.pop(0)

    def test_the_dll_question_reads_waiting_raw_input_first(self):
        listener, api, read = self.listener(raws=[(NUMPAD, SCAN["5"], False, False, 0, 0x65)])
        with mock.patch.object(wr, "_api", return_value=api), mock.patch.object(wr, "_read_raw", read):
            answer = listener.handle(1234, wr.QUERY_MESSAGE, 0x65, (SCAN["5"] << 16) | 1)
        self.assertEqual(answer, 1, "blocked: Raw Input said it came from the numpad")
        self.assertEqual(self.emitted, [("5", True)])

    def test_a_main_keyboard_key_is_let_through(self):
        listener, api, read = self.listener(raws=[(MAIN, SCAN["5"], False, False, 0, 0x65)])
        with mock.patch.object(wr, "_api", return_value=api), mock.patch.object(wr, "_read_raw", read):
            self.assertEqual(listener.handle(1234, wr.QUERY_MESSAGE, 0x65, (SCAN["5"] << 16) | 1), 0)

    def test_raw_input_messages_feed_the_router(self):
        listener, api, read = self.listener(raws=[(NUMPAD, SCAN["-"], False, False, 0, 0x6D)])
        with mock.patch.object(wr, "_api", return_value=api), mock.patch.object(wr, "_read_raw", read):
            self.assertIsNone(listener.handle(1234, wr.WM_INPUT, 0, 99), "DefWindowProc still cleans up")
        self.assertEqual(self.emitted, [("-", True)])

    def test_without_a_router_nothing_is_blocked(self):
        listener = wr._Listener(lambda *raw: False, lambda now: False)
        self.assertEqual(listener.handle(1234, wr.QUERY_MESSAGE, 0x65, (SCAN["5"] << 16) | 1), 0)

    def test_errors_in_the_window_never_reach_windows(self):
        broken = mock.Mock(**{"handle.side_effect": ZeroDivisionError})
        with mock.patch.dict(wr._windows, {1234: broken}), self.assertLogs("numpadctl", "ERROR"):
            self.assertEqual(wr._window_proc(1234, wr.QUERY_MESSAGE, 0, 0), 0)


class DllTest(unittest.TestCase):
    def test_the_c_file_matches_the_python_side(self):
        source = (wr.DLL_PATH.parent / "numpadhook" / "numpadhook.c").read_text().lower()
        self.assertIn(f"#define query_message (wm_app + {wr.QUERY_MESSAGE - wr.WM_APP:#x})", source)
        self.assertIn(f'#define server_class l"{wr.SERVER_CLASS.lower()}"', source)
        for code in wr.NUMPAD_SCANS:
            self.assertIn(f"case {code:#04x}:", source, "every numpad key asks the service")

    def test_the_dll_is_built_and_exports_the_hook(self):
        data = wr.DLL_PATH.read_bytes()
        self.assertEqual(data[:2], b"MZ")
        self.assertIn(b"KeyboardProc", data)


class HandleTypesTest(unittest.TestCase):
    """Regression: GetModuleHandleW's handle was cut to 32 bits, so Windows refused the hook (error 126)."""

    def test_handles_keep_their_full_size(self):
        fake = mock.MagicMock()
        with mock.patch.object(wr.ctypes, "WinDLL", create=True, return_value=fake), \
                mock.patch.object(wr, "_kernel32", None):
            wr._kernel()
        self.assertIs(fake.GetModuleHandleW.restype, wr.wintypes.HMODULE)
        self.assertEqual(ctypes.sizeof(fake.GetModuleHandleW.restype), ctypes.sizeof(ctypes.c_void_p))


class StructureSizeTest(unittest.TestCase):
    @unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "64-bit sizes")
    def test_sizes_match_windows_x64(self):
        self.assertEqual(ctypes.sizeof(wr.RAWINPUTHEADER), 24)
        self.assertEqual(ctypes.sizeof(wr.RAWKEYBOARD), 16)
        self.assertEqual(ctypes.sizeof(wr.RAWINPUTDEVICELIST), 16)
        self.assertEqual(ctypes.sizeof(wr.WNDCLASSEXW), 80)


@unittest.skipUnless(sys.platform == "win32", "needs real Windows")
class RealWindowsTest(unittest.TestCase):
    """The real DLL, hook and Raw Input on a real Windows desktop (GitHub's Windows runner)."""

    def test_raw_input_arrives_and_the_dll_blocks_what_the_router_says(self):
        from ctypes import wintypes
        from numpadctl.platform import windows_system as ws
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
        u.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        u.DefWindowProcW.restype = wr.LRESULT
        u.SetForegroundWindow.argtypes = u.SetFocus.argtypes = [wintypes.HWND]

        # The service side: a listener whose router blocks numpad 5 and nothing else.
        raw_seen = []

        class Router:
            grab = True

            def raw(self, device, scan, e0, up, now):
                raw_seen.append((scan, up))

            def should_block(self, scan, up, now):
                return scan == 0x4C

        listener = wr._Listener(lambda *raw: False, lambda now: False, Router())
        service = threading.Thread(target=listener.run, daemon=True)
        service.start()
        time.sleep(0.5)

        # The app side: a plain window in another thread that records the keys it receives.
        received = []

        def target_proc(hwnd, message, wparam, lparam):
            if message == 0x0100:  # WM_KEYDOWN
                received.append(wparam)
            return u.DefWindowProcW(hwnd, message, wparam, lparam)
        target_proc_ref = wr.WNDPROC(target_proc)
        ready = threading.Event()

        def app():
            module = wr._kernel().GetModuleHandleW(None)
            wc = wr.WNDCLASSEXW(cbSize=ctypes.sizeof(wr.WNDCLASSEXW), lpfnWndProc=target_proc_ref,
                                hInstance=module, lpszClassName="NumpadCtlTestTarget")
            wr._api().RegisterClassExW(ctypes.byref(wc))
            hwnd = wr._api().CreateWindowExW(0, "NumpadCtlTestTarget", "test", 0x10CF0000, 0, 0, 300, 200,
                                             None, None, module, None)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
            ready.set()
            msg = wintypes.MSG()
            end = time.monotonic() + 4
            while time.monotonic() < end:
                while wr._api().PeekMessageW(ctypes.byref(msg), None, 0, 0, wr.PM_REMOVE):
                    wr._api().DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.01)
            wr._api().DestroyWindow(hwnd)
        app_thread = threading.Thread(target=app, daemon=True)
        app_thread.start()
        ready.wait(3)
        time.sleep(0.5)

        # Press numpad 5 (the router blocks it) and numpad 6 (it should arrive).
        for scan, vk in ((0x4C, 0x65), (0x4D, 0x66)):
            for up in (False, True):
                item = ws.INPUT(type=ws.INPUT_KEYBOARD)
                item.u.ki = ws.KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=ws.KEYEVENTF_KEYUP if up else 0,
                                          time=0, dwExtraInfo=0)
                u.SendInput(1, ctypes.byref(item), ctypes.sizeof(ws.INPUT))
                time.sleep(0.1)
        app_thread.join(6)
        listener.stop()
        service.join(3)

        print(f"\nRaw Input seen: {raw_seen}\nkeys the window received: {[hex(k) for k in received]}")
        self.assertIn((0x4C, False), raw_seen, "Raw Input reached the service's window")
        if not received:
            self.skipTest("the test window never got keyboard focus on this runner")
        self.assertIn(0x66, received, "a key the router lets through arrives")
        self.assertNotIn(0x65, received, "the DLL blocked the key the router said to block")


if __name__ == "__main__":
    unittest.main()
