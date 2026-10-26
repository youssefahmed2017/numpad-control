"""Reading the numpad on Windows without a driver: Raw Input plus a low-level keyboard hook.

Raw Input says which keyboard a key came from but can't stop it; a low-level hook
(WH_KEYBOARD_LL) can stop a key but doesn't know its keyboard. Windows calls the hook
first, and only then delivers the key's Raw Input, so:

  1. the hook holds back every key the numpad has (and keeps later keys in line behind
     it, so nothing gets typed out of order);
  2. the key's Raw Input arrives a moment later and names its keyboard: from the numpad,
     it's passed to the service (and swallowed when grabbed); from any other keyboard,
     it's sent again unchanged with SendInput, marked so the hook lets it through.

Only keys with a numpad scan code wait (the number pad, NumLock, Backspace), and only
for about a millisecond. No driver, nothing installed, nothing in the kernel: the same
user-mode APIs as Discord's or OBS's hotkeys, so anti-cheat systems have nothing to
block. Same interface as linux_numpad.py.

    python -m numpadctl.platform.windows_rawinput    prints keys from the configured numpad
"""

import asyncio
import collections
import ctypes
import logging
import threading
import time
from ctypes import wintypes
from pathlib import Path

from .windows_numpad import KEY_CODES, PRESENCE_CHECK_SECONDS, PRESENCE_MISSES, RepeatFilter, parse_ids

log = logging.getLogger("numpadctl")

WH_KEYBOARD_LL, HC_ACTION = 13, 0
LLKHF_EXTENDED, LLKHF_INJECTED, LLKHF_UP = 0x01, 0x10, 0x80
WM_QUIT, WM_TIMER, WM_INPUT = 0x0012, 0x0113, 0x00FF
RIDEV_INPUTSINK, RID_INPUT, RIM_TYPEKEYBOARD, RIDI_DEVICENAME = 0x0100, 0x10000003, 1, 0x20000007
RI_KEY_BREAK, RI_KEY_E0 = 0x01, 0x02
HWND_MESSAGE = -3
INPUT_KEYBOARD, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 1, 0x0001, 0x0002

REPLAYED = 0x4E504443      # dwExtraInfo of keys we send again ("NPDC"), so the hook lets them pass
TICK_MS = 20               # how often held keys are checked for a Raw Input that never came
MATCH_TIMEOUT = 0.15       # a held key with no Raw Input by then is let through as typed
NUMPAD_SCANS = {code for code, _ in KEY_CODES}

# Fixed sizes, as on Windows (wintypes' DWORD is 8 bytes on Linux, where the tests also run).
WORD, USHORT, DWORD, UINT, ULONG, LONG = (ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint32,
                                          ctypes.c_uint32, ctypes.c_int32)
ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HookProc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(  # (CFUNCTYPE: tests on Linux)
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", DWORD), ("scanCode", DWORD), ("flags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


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


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", _INPUT_UNION)]


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
        _kernel32 = k
    return _kernel32


def _api():
    """user32 with argument types set (a private copy: other modules use ctypes.windll.user32)."""
    global _user32
    if _user32 is not None:
        return _user32
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetWindowsHookExW.argtypes = [ctypes.c_int, HookProc, wintypes.HINSTANCE, wintypes.DWORD]
    u.SetWindowsHookExW.restype = wintypes.HHOOK
    u.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    u.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    u.CallNextHookEx.restype = LRESULT
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DestroyWindow.argtypes = [wintypes.HWND]
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
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.restype = LRESULT
    u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    u.SetTimer.restype = ctypes.c_size_t
    u.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    u.SendInput.restype = wintypes.UINT
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


# ---------------------------------------------------------------- telling the numpad's keys apart

Held = collections.namedtuple("Held", "scan extended up vk numpad_key since")


class KeySorter:
    """Decides, without any Windows calls, what happens to each key (so tests can drive it).

    hook() is called from the low-level hook and says whether to hold a key back;
    raw() is called with each key's Raw Input and settles the held key it belongs to;
    tick() lets through keys whose Raw Input never came."""

    def __init__(self, is_numpad, grab, emit, replay):
        self.is_numpad = is_numpad  # device handle -> True for the numpad
        self.grab, self.emit, self.replay = grab, emit, replay
        self.held = collections.deque()
        self.repeats = RepeatFilter()

    def hook(self, scan, extended, up, vk, now):
        """True: hold the key back (the hook swallows it; it's sent again later if it isn't the numpad's)."""
        numpad_key = scan in NUMPAD_SCANS
        if not numpad_key and not self.held:
            return False  # can't be the numpad's, and nothing is waiting: type it right away
        self.held.append(Held(scan, extended, up, vk, numpad_key, now))
        return True

    def raw(self, device, scan, e0, up):
        if scan not in NUMPAD_SCANS or not self.held:
            return
        head = self.held[0]
        if head.scan != scan or head.up != up:
            return  # the Raw Input of a key that was typed right away
        self.held.popleft()
        key = KEY_CODES.get((scan, e0))
        if key and self.is_numpad(device):
            if self.repeats.passes(key, not up, time.monotonic()):
                self.emit((key, not up))
            if not self.grab:
                self.replay(head)
        else:
            self.replay(head)
        self._release_waiting()

    def tick(self, now):
        while self.held and now - self.held[0].since > MATCH_TIMEOUT:
            log.debug("no Raw Input for scan code %#x: typed as usual", self.held[0].scan)
            self.replay(self.held.popleft())
            self._release_waiting()

    def _release_waiting(self):
        """Send the keys that only waited to stay in order, up to the next one that may be the numpad's."""
        while self.held and not self.held[0].numpad_key:
            self.replay(self.held.popleft())


def _replay(held):
    """Send a held key again, exactly as it was typed, marked as ours."""
    item = INPUT(type=INPUT_KEYBOARD)
    flags = (KEYEVENTF_KEYUP if held.up else 0) | (KEYEVENTF_EXTENDEDKEY if held.extended else 0)
    item.u.ki = KEYBDINPUT(wVk=held.vk, wScan=held.scan, dwFlags=flags, time=0, dwExtraInfo=REPLAYED)
    if _api().SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
        log.warning("Windows didn't take back a held key (scan code %#x)", held.scan)


def _read_raw(lparam):
    """(device handle, scan code, E0?, released?, extra info) of a WM_INPUT keyboard message, or None."""
    data, size = RAWINPUT(), wintypes.UINT(ctypes.sizeof(RAWINPUT))
    if _api().GetRawInputData(lparam, RID_INPUT, ctypes.byref(data), ctypes.byref(size),
                              ctypes.sizeof(RAWINPUTHEADER)) in (0, 0xFFFFFFFF):
        return None
    if data.header.dwType != RIM_TYPEKEYBOARD:
        return None
    k = data.keyboard
    return data.header.hDevice, k.MakeCode, bool(k.Flags & RI_KEY_E0), bool(k.Flags & RI_KEY_BREAK), \
        k.ExtraInformation


# Windows gives a process one Raw Input window for keyboards, so while the numpad is open,
# detect_device listens through its window instead of opening a second one.
_shared_lock = threading.Lock()
_numpad_listener = None   # the open numpad's _Listener
_observers = []           # more on_raw callbacks run by it


class _Listener:
    """A message-only window receiving every keyboard's Raw Input, plus (optionally) the hook.

    Everything runs on the thread that calls run(): Windows calls the hook on the thread
    that installed it, while that thread waits for messages."""

    def __init__(self, on_raw, on_tick, sorter=None):
        self.on_raw, self.on_tick, self.sorter = on_raw, on_tick, sorter
        self.thread_id = None
        self.stopped = threading.Event()

    def _hook(self, code, wparam, lparam):
        try:
            if code == HC_ACTION:
                info = KBDLLHOOKSTRUCT.from_address(lparam)
                if not info.flags & LLKHF_INJECTED and info.dwExtraInfo != REPLAYED and \
                        self.sorter.hook(info.scanCode, bool(info.flags & LLKHF_EXTENDED),
                                         bool(info.flags & LLKHF_UP), info.vkCode, time.monotonic()):
                    return 1
        except Exception:  # an exception must never leave a key stuck: let it through
            log.exception("keyboard hook")
        return _api().CallNextHookEx(None, code, wparam, lparam)

    def run(self):
        global _numpad_listener
        u = _api()
        hwnd = u.CreateWindowExW(0, "STATIC", "numpad-control", 0, 0, 0, 0, 0, HWND_MESSAGE, None, None, None)
        self.thread_id = _kernel().GetCurrentThreadId()  # (now it has a message queue)
        hook = None
        try:
            if self.stopped.is_set():  # stop() came before there was a thread to tell
                return
            if not hwnd:
                raise OSError(f"couldn't create the input window (error {ctypes.get_last_error()})")
            device = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd)  # generic desktop / keyboard
            if not u.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
                raise OSError(f"Windows refused Raw Input (error {ctypes.get_last_error()})")
            if self.sorter is not None:
                self._hook_proc = HookProc(self._hook)  # keep the callback alive while hooked
                hook = u.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc, _kernel().GetModuleHandleW(None), 0)
                if not hook:  # some Windows versions want no module at all for a low-level hook
                    hook = u.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc, None, 0)
                if not hook:
                    raise OSError(f"Windows refused the keyboard hook (error {ctypes.get_last_error()})")
            u.SetTimer(hwnd, 1, TICK_MS, None)
            if self.sorter is not None:
                with _shared_lock:
                    _numpad_listener = self
            msg = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_INPUT and msg.hWnd == hwnd:
                    raw = _read_raw(msg.lParam)
                    if raw and raw[0] and raw[4] != REPLAYED:  # no device: injected by some program
                        if self.sorter is not None:
                            with _shared_lock:
                                observers = list(_observers)
                            for observer in observers:
                                observer(*raw[:4])
                        if self.on_raw(*raw[:4]):
                            break
                elif msg.message == WM_TIMER and msg.hWnd == hwnd:
                    if self.on_tick(time.monotonic()):
                        break
                u.DispatchMessageW(ctypes.byref(msg))
        finally:
            with _shared_lock:
                if _numpad_listener is self:
                    _numpad_listener = None
            if hook:
                u.UnhookWindowsHookEx(hook)
            if self.sorter is not None:
                for held in self.sorter.held:  # never leave a key swallowed
                    _replay(held)
                self.sorter.held.clear()
            if hwnd:
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
        sorter = KeySorter(self._is_numpad, self.grab, emit, _replay)

        def on_raw(device, scan, e0, up):
            sorter.raw(device, scan, e0, up)
            return False

        def on_tick(now):
            sorter.tick(now)
            if now >= state["next_check"]:
                state["next_check"] = now + PRESENCE_CHECK_SECONDS
                state["misses"] = 0 if self._present() else state["misses"] + 1
                if state["misses"] >= PRESENCE_MISSES:
                    emit(OSError("the numpad was unplugged"))
                    return True
            return False

        return _Listener(on_raw, on_tick, sorter)

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


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from numpadctl import config

    spec = config.load()["device"]
    print("Keyboards:", *[f"  {n}: {name}" for n, _, _, name in list_devices()], sep="\n")
    numpad = open_numpad(spec, grab=True)
    if numpad is None:
        sys.exit(f"No keyboard with vendor {spec['vendor']} / product {spec['product']} - is the numpad plugged in?")
    print(f"\nListening to the numpad ({', '.join(numpad.names)}); its keys won't type. Ctrl+C stops.\n")

    async def show():
        async for key, down in numpad.events():
            print(f"  {key:<10} {'pressed' if down else 'released'}")
    try:
        asyncio.run(show())
    except (KeyboardInterrupt, OSError) as e:
        print(f"\nStopped{': ' + str(e) if isinstance(e, OSError) else ''}")
    finally:
        numpad.close()
