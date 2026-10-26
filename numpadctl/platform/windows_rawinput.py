"""Reading the numpad on Windows without a driver: Raw Input plus a keyboard hook DLL.

Two Windows mechanisms, each doing what it can:

  1. Raw Input tells this program about every key from every keyboard, with the
     keyboard it came from, and nothing can stop it from arriving. Keys from the
     numpad go to the service from here, whatever app is in front.
  2. numpadhook.dll (numpadhook/numpadhook.c) stops the numpad's keys from typing.
     It's installed as a WH_KEYBOARD hook, so Windows loads it into apps; just before
     an app receives a key a number pad has, it asks this program's window whether
     that key came from the numpad (Raw Input told us before the app got the key),
     and if so the app never sees it. Keys a number pad doesn't have never ask.

No driver and nothing in the kernel. A low-level hook (WH_KEYBOARD_LL) can't do the
second part: it runs before Raw Input, and a key it swallows never gets a Raw Input,
so it can't know the keyboard. Known gaps: 32-bit apps and apps running as
administrator don't load the DLL, so the numpad still types there (its actions work).
Same interface as linux_numpad.py.

    python -m numpadctl.platform.windows_rawinput          prints keys from the configured numpad
    python -m numpadctl.platform.windows_rawinput --all    prints every key from every keyboard
"""

import asyncio
import ctypes
import logging
import struct
import threading
import time
from ctypes import wintypes
from pathlib import Path

from .windows_numpad import KEY_CODES, PRESENCE_CHECK_SECONDS, PRESENCE_MISSES, RepeatFilter, parse_ids

log = logging.getLogger("numpadctl")

WH_KEYBOARD = 2
WM_QUIT, WM_TIMER, WM_INPUT = 0x0012, 0x0113, 0x00FF
WM_APP = 0x8000
QUERY_MESSAGE = WM_APP + 0x4E50  # numpadhook.dll asks "was this key the numpad's?" (same number in the C file)
SERVER_CLASS = "NumpadCtlHookServer"  # the DLL finds our window by this class (same in the C file)
RIDEV_INPUTSINK, RID_INPUT, RIM_TYPEKEYBOARD, RIDI_DEVICENAME = 0x0100, 0x10000003, 1, 0x20000007
RI_KEY_BREAK, RI_KEY_E0 = 0x01, 0x02
PM_REMOVE = 0x0001
WS_POPUP, WS_EX_TOOLWINDOW = 0x80000000, 0x00000080
ERROR_CLASS_ALREADY_EXISTS = 1410

TICK_MS = 250              # timer for presence checks and stopping
FRESH = 5.0                # a numpad key the app gets this much later than its Raw Input still counts
NUMPAD_SCANS = {code for code, _ in KEY_CODES}
DLL_PATH = Path(__file__).with_name("numpadhook.dll")

# Fixed sizes, as on Windows (wintypes' DWORD is 8 bytes on Linux, where the tests also run).
USHORT, DWORD, UINT, ULONG = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32
LRESULT = ctypes.c_ssize_t
_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)  # (CFUNCTYPE: tests on Linux)
WNDPROC = _FUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", USHORT), ("usUsage", USHORT),
                ("dwFlags", DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", DWORD)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", DWORD), ("dwSize", DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", USHORT), ("Flags", USHORT), ("Reserved", USHORT),
                ("VKey", USHORT), ("Message", UINT), ("ExtraInformation", ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD), ("_spare", ctypes.c_byte * 16)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", UINT), ("style", UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON)]


_user32 = None
_kernel32 = None


def _kernel():
    """kernel32 with return types set: without them ctypes cuts 64-bit handles down to 32 bits."""
    global _kernel32
    if _kernel32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k.GetModuleHandleW.restype = wintypes.HMODULE
        k.GetCurrentThreadId.restype = wintypes.DWORD
        k.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
        k.GetProcAddress.restype = ctypes.c_void_p
        _kernel32 = k
    return _kernel32


def _api():
    """user32 with argument types set (a private copy: other modules use ctypes.windll.user32)."""
    global _user32
    if _user32 is not None:
        return _user32
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
    u.SetWindowsHookExW.restype = wintypes.HHOOK
    u.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    u.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u.RegisterClassExW.restype = wintypes.ATOM
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    u.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                  ctypes.POINTER(wintypes.UINT), wintypes.UINT]
    u.GetRawInputData.restype = wintypes.UINT
    u.GetRawInputDeviceList.argtypes = [ctypes.POINTER(RAWINPUTDEVICELIST), ctypes.POINTER(wintypes.UINT),
                                        wintypes.UINT]
    u.GetRawInputDeviceList.restype = wintypes.UINT
    u.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                         ctypes.POINTER(wintypes.UINT)]
    u.GetRawInputDeviceInfoW.restype = wintypes.UINT
    u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                               wintypes.UINT]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.restype = LRESULT
    u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    u.SetTimer.restype = ctypes.c_size_t
    _user32 = u
    return u


# ---------------------------------------------------------------- keyboards

def _device_name(handle):
    """\\\\?\\HID#VID_C0F4&PID_05F5&MI_00#... for a Raw Input device handle ("" if it's gone)."""
    u, size = _api(), wintypes.UINT(0)
    u.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, None, ctypes.byref(size))
    if not size.value:
        return ""
    buffer = ctypes.create_unicode_buffer(size.value + 1)
    if u.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, buffer, ctypes.byref(size)) in (0, 0xFFFFFFFF):
        return ""
    return buffer.value


def _keyboards():
    """{device handle: device name} of every keyboard Windows sees now."""
    u, count = _api(), wintypes.UINT(0)
    size = ctypes.sizeof(RAWINPUTDEVICELIST)
    if u.GetRawInputDeviceList(None, ctypes.byref(count), size) == 0xFFFFFFFF:
        raise OSError("Windows wouldn't list the keyboards")
    items = (RAWINPUTDEVICELIST * max(count.value, 1))()
    got = u.GetRawInputDeviceList(items, ctypes.byref(count), size)
    if got == 0xFFFFFFFF:
        raise OSError("Windows wouldn't list the keyboards")
    found = {}
    for item in items[:got]:
        if item.dwType == RIM_TYPEKEYBOARD:
            name = _device_name(item.hDevice)
            if name:
                found[item.hDevice] = name
    return found


def _spec(name):
    vendor, product = parse_ids(name)
    return {"vendor": vendor, "product": product, "name": name}


def list_devices():
    """[(keyboard number, vendor, product, device name)] of every keyboard."""
    return [(f"keyboard {n}", *(parse_ids(name) or ("????", "????")), name)
            for n, name in enumerate(_keyboards().values(), 1)]


# ---------------------------------------------------------------- deciding about each key

class KeyRouter:
    """What happens to each key, without any Windows calls (so tests can drive it).

    raw() gets every key's Raw Input: the numpad's keys go to the service, and the
    keyboard each numpad-type key last came from is remembered. should_block() answers
    numpadhook.dll's question, which comes after that key's Raw Input."""

    def __init__(self, is_numpad, grab, emit):
        self.is_numpad = is_numpad  # device handle -> True for the numpad
        self.grab, self.emit = grab, emit
        self.repeats = RepeatFilter()
        self.source = {}      # (scan code, released?) -> (from the numpad?, when)
        self.unknown = set()  # codes the numpad sent that aren't numpad keys (logged once each)

    def raw(self, device, scan, e0, up, now):
        if scan not in NUMPAD_SCANS:
            if device and not up and (scan, e0) not in self.unknown and self.is_numpad(device):
                self.unknown.add((scan, e0))
                log.warning("the numpad sent a key that isn't a numpad key (scan code %#x%s); it types as usual",
                            scan, ", E0" if e0 else "")
            return
        # device 0: a key sent by a program (SendInput), e.g. one of our own actions: never the numpad
        from_numpad = bool(device) and self.is_numpad(device)
        self.source[(scan, up)] = (from_numpad, now)
        key = KEY_CODES.get((scan, e0))
        if from_numpad and key and self.repeats.passes(key, not up, now):
            self.emit((key, not up))

    def should_block(self, scan, up, now):
        if not self.grab:
            return False
        from_numpad, when = self.source.get((scan, up), (False, 0.0))
        return from_numpad and now - when <= FRESH


def _query_key(wparam, lparam):
    """(scan code, released?) from a WH_KEYBOARD hook's lParam (keystroke message flags)."""
    return (lparam >> 16) & 0xFF, bool((lparam >> 31) & 1)


def _read_raw(lparam):
    """(device handle, scan code, E0?, released?, extra info, virtual key) of a WM_INPUT keyboard message, or None."""
    data, size = RAWINPUT(), wintypes.UINT(ctypes.sizeof(RAWINPUT))
    if _api().GetRawInputData(lparam, RID_INPUT, ctypes.byref(data), ctypes.byref(size),
                              ctypes.sizeof(RAWINPUTHEADER)) in (0, 0xFFFFFFFF):
        return None
    if data.header.dwType != RIM_TYPEKEYBOARD:
        return None
    k = data.keyboard
    return data.header.hDevice or 0, k.MakeCode, bool(k.Flags & RI_KEY_E0), bool(k.Flags & RI_KEY_BREAK), \
        k.ExtraInformation, k.VKey


# ---------------------------------------------------------------- the window and the hook

# Windows gives a process one Raw Input window for keyboards, so while the numpad is open,
# detect_device listens through its window instead of opening a second one.
_shared_lock = threading.Lock()
_numpad_listener = None   # the open numpad's _Listener
_observers = []           # more on_raw callbacks run by it
_windows = {}             # window handle -> its _Listener (one window procedure serves them all)
_class_registered = False


def _window_proc(hwnd, message, wparam, lparam):
    listener = _windows.get(hwnd)
    if listener is not None:
        try:
            handled = listener.handle(hwnd, message, wparam, lparam)
            if handled is not None:
                return handled
        except Exception:  # an exception must never reach Windows (or leave an app waiting)
            log.exception("input window")
            if message == QUERY_MESSAGE:
                return 0
    return _api().DefWindowProcW(hwnd, message, wparam, lparam)


_WINDOW_PROC = WNDPROC(_window_proc)  # kept alive for as long as the class exists


def _register_class():
    global _class_registered
    if _class_registered:
        return
    wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=_WINDOW_PROC,
                     hInstance=_kernel().GetModuleHandleW(None), lpszClassName=SERVER_CLASS)
    if not _api().RegisterClassExW(ctypes.byref(wc)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
        raise OSError(f"couldn't register the input window (error {ctypes.get_last_error()})")
    _class_registered = True


class _Listener:
    """A hidden window receiving every keyboard's Raw Input, plus (with a router) the hook DLL.

    Everything runs on the thread that calls run(): Windows delivers Raw Input and the
    DLL's questions to the window's thread while it waits for messages."""

    def __init__(self, on_raw, on_tick, router=None, everything=False):
        self.on_raw, self.on_tick, self.router = on_raw, on_tick, router
        self.everything = everything  # on_raw also gets the extra info and virtual key (the --all test)
        self.thread_id = None
        self.stopped = threading.Event()

    def _raw(self, lparam):
        raw = _read_raw(lparam)
        if raw is None:
            return
        device, scan, e0, up = raw[:4]
        if self.router is not None:
            self.router.raw(device, scan, e0, up, time.monotonic())
            if device:
                with _shared_lock:
                    observers = list(_observers)
                for observer in observers:
                    observer(device, scan, e0, up)
        if (device or self.everything) and self.on_raw(*(raw if self.everything else raw[:4])):
            _api().PostQuitMessage(0)

    def _drain_raw_input(self, hwnd):
        """Handle Raw Input that's waiting (the DLL's question can arrive before it's been read)."""
        u, msg = _api(), wintypes.MSG()
        while u.PeekMessageW(ctypes.byref(msg), hwnd, WM_INPUT, WM_INPUT, PM_REMOVE):
            self._raw(msg.lParam)
            u.DefWindowProcW(hwnd, WM_INPUT, msg.wParam, msg.lParam)  # lets Windows clean the message up

    def handle(self, hwnd, message, wparam, lparam):
        """The window procedure for this listener's window; None = Windows' default handling."""
        if message == WM_INPUT:
            self._raw(lparam)
            return None  # DefWindowProc cleans the Raw Input up
        if message == QUERY_MESSAGE:
            if self.router is None:
                return 0
            self._drain_raw_input(hwnd)
            scan, up = _query_key(wparam, lparam)
            return 1 if self.router.should_block(scan, up, time.monotonic()) else 0
        if message == WM_TIMER:
            if self.on_tick(time.monotonic()):
                _api().PostQuitMessage(0)
            return 0
        return None

    def _install_hook(self):
        if not DLL_PATH.exists():
            raise OSError(f"{DLL_PATH.name} is missing next to {Path(__file__).name} (reinstall Numpad Control)")
        if struct.calcsize("P") != 8:
            raise OSError("this needs 64-bit Python")
        dll = ctypes.WinDLL(str(DLL_PATH))
        proc = _kernel().GetProcAddress(dll._handle, b"KeyboardProc")
        if not proc:
            raise OSError(f"{DLL_PATH.name} has no KeyboardProc")
        hook = _api().SetWindowsHookExW(WH_KEYBOARD, proc, dll._handle, 0)
        if not hook:
            raise OSError(f"Windows refused the keyboard hook (error {ctypes.get_last_error()})")
        self._dll = dll  # stays loaded while hooked
        return hook

    def run(self):
        global _numpad_listener
        u = _api()
        _register_class()
        hwnd = u.CreateWindowExW(WS_EX_TOOLWINDOW, SERVER_CLASS, "numpad-control", WS_POPUP, 0, 0, 0, 0,
                                 None, None, _kernel().GetModuleHandleW(None), None)
        self.thread_id = _kernel().GetCurrentThreadId()  # (now it has a message queue)
        hook = None
        try:
            if self.stopped.is_set():  # stop() came before there was a thread to tell
                return
            if not hwnd:
                raise OSError(f"couldn't create the input window (error {ctypes.get_last_error()})")
            _windows[hwnd] = self
            device = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd)  # generic desktop / keyboard
            if not u.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
                raise OSError(f"Windows refused Raw Input (error {ctypes.get_last_error()})")
            if self.router is not None and self.router.grab:
                hook = self._install_hook()
            u.SetTimer(hwnd, 1, TICK_MS, None)
            if self.router is not None:
                with _shared_lock:
                    _numpad_listener = self
            msg = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                u.DispatchMessageW(ctypes.byref(msg))
        finally:
            with _shared_lock:
                if _numpad_listener is self:
                    _numpad_listener = None
            if hook:
                u.UnhookWindowsHookEx(hook)
            if hwnd:
                _windows.pop(hwnd, None)
                u.DestroyWindow(hwnd)

    def stop(self):
        self.stopped.set()
        if self.thread_id is not None:
            _api().PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


def detect_device(timeout=15):
    """Wait for a numpad key on any keyboard and return that keyboard's spec (or None).

    Only Raw Input is used here, so every key types as usual (a key on the open numpad
    still goes to the service as well)."""
    deadline, found = time.monotonic() + timeout, []
    done = threading.Event()

    def on_raw(device, scan, e0, up):
        if found or up or (scan, e0) not in KEY_CODES:
            return bool(found)
        name = _device_name(device)
        if parse_ids(name):
            found.append(_spec(name))
            done.set()
            return True
        return False

    with _shared_lock:
        shared = _numpad_listener is not None
        if shared:
            _observers.append(on_raw)
    if shared:
        try:
            done.wait(timeout)
        finally:
            with _shared_lock:
                _observers.remove(on_raw)
    else:
        _Listener(on_raw, lambda now: now >= deadline).run()
    return found[0] if found else None


class Numpad:
    """The numpad's keyboard devices (one numpad can show up as several)."""

    def __init__(self, wanted, devices, grab):
        self.wanted, self.devices, self.grab = wanted, devices, grab  # devices: {handle: name}
        self._known = {}  # device handle -> is it the numpad? (from its name, looked up once)
        self._listener = None

    @property
    def names(self):
        return list(self.devices.values())

    @property
    def spec(self):
        return _spec(min(self.devices.values(), key=len))

    def _is_numpad(self, device):
        if device not in self._known:
            self._known[device] = parse_ids(_device_name(device)) == self.wanted
        return self._known[device]

    def _present(self):
        """Look the numpad up again (a replugged numpad comes back with new handles)."""
        devices = {h: name for h, name in _keyboards().items() if parse_ids(name) == self.wanted}
        if devices:
            self.devices = devices
            self._known = {h: True for h in devices}
        return bool(devices)

    def _listen(self, emit):
        """The _Listener for events(): emit((key, down)), or emit(error) when the numpad goes."""
        state = {"next_check": time.monotonic() + PRESENCE_CHECK_SECONDS, "misses": 0}
        router = KeyRouter(self._is_numpad, self.grab, emit)

        def on_tick(now):
            if now >= state["next_check"]:
                state["next_check"] = now + PRESENCE_CHECK_SECONDS
                state["misses"] = 0 if self._present() else state["misses"] + 1
                if state["misses"] >= PRESENCE_MISSES:
                    emit(OSError("the numpad was unplugged"))
                    return True
            return False

        return _Listener(lambda *raw: False, on_tick, router)

    def _read(self, listener, emit):
        """Reader thread: the window, the hook and the message loop."""
        try:
            listener.run()
        except OSError as e:  # Windows refused something; the service logs it and tries again later
            emit(OSError(f"the numpad reader failed: {e}"))
        except Exception as e:  # never die silently: the service would wait for keys forever
            log.exception("numpad reader stopped")
            emit(OSError(f"the numpad reader failed: {e}"))

    async def events(self):
        """Yield (key name, pressed) until the numpad goes away (then raises OSError)."""
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def emit(item):
            loop.call_soon_threadsafe(queue.put_nowait, item)
        self._listener = self._listen(emit)
        threading.Thread(target=self._read, args=(self._listener, emit), daemon=True).start()
        try:
            while True:
                item = await queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            self.close()

    def close(self):
        if self._listener is not None:
            self._listener.stop()


def open_numpad(spec, grab):
    """The numpad's keyboard devices (by vendor/product ID); None if it isn't there.

    Nothing is hooked until events() runs."""
    wanted = (spec["vendor"].lower(), spec["product"].lower())
    devices = {h: name for h, name in _keyboards().items() if parse_ids(name) == wanted}
    return Numpad(wanted, devices, grab) if devices else None


def _show_everything(spec):
    """--all: every key from every keyboard, exactly as Windows reports it (nothing is swallowed)."""
    import re
    wanted = (spec["vendor"].lower(), spec["product"].lower())
    names = {}

    def show_raw(device, scan, e0, up, extra, vkey):
        if device not in names:
            name = _device_name(device) if device else "(sent by a program)"
            part = "".join(re.findall(r"&(MI_\w\w|Col\w\w)", name, re.I))
            names[device] = f"{'NUMPAD ' if parse_ids(name) == wanted else 'other  '}{part or name[:40]}"
        key = KEY_CODES.get((scan, e0), "(not a numpad key)")
        print(f"  {names[device]:<22} scan {scan:#04x}{' E0' if e0 else '   '} vkey {vkey:#04x}  "
              f"{'up  ' if up else 'down'}  -> {key}", flush=True)
        return False

    print("\nRaw Input is on. Press keys (numpad and main keyboard); everything types as usual. "
          "Ctrl+C stops.\n", flush=True)
    _Listener(show_raw, lambda now: False, everything=True).run()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from numpadctl import config

    spec = config.load()["device"]
    print("Keyboards:", *[f"  {n}: {name}" for n, _, _, name in list_devices()], sep="\n", flush=True)
    if "--all" in sys.argv:
        try:
            _show_everything(spec)
        except KeyboardInterrupt:
            pass
        sys.exit(0)
    numpad = open_numpad(spec, grab=True)
    if numpad is None:
        sys.exit(f"No keyboard with vendor {spec['vendor']} / product {spec['product']} - is the numpad plugged in?")
    print(f"\nListening to the numpad ({', '.join(numpad.names)}); its keys won't type. Ctrl+C stops.\n", flush=True)

    async def show():
        async for key, down in numpad.events():
            print(f"  {key:<10} {'pressed' if down else 'released'}", flush=True)
    try:
        asyncio.run(show())
    except (KeyboardInterrupt, OSError) as e:
        print(f"\nStopped{': ' + str(e) if isinstance(e, OSError) else ''}")
    finally:
        numpad.close()
