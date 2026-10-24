"""Reading the numpad on Windows: the Interception driver, via its interception.dll.

Interception can capture one keyboard without touching the others, which a
plain Windows keyboard hook can't. Only the numpad's devices are captured (a
filter set just for them), so the main keyboard never passes through here.

Same interface as linux_numpad.py: key names like "5", "Enter", "0"; a burst of
three "0"s (the "000" key) is recognised by the service.

    python -m numpadctl.platform.windows_numpad    prints keys from the configured numpad
"""

import asyncio
import ctypes
import os
import re
import struct
import threading
import time
from pathlib import Path

MAX_KEYBOARD = 10
FILTER_KEY_NONE, FILTER_KEY_ALL = 0x0000, 0xFFFF
KEY_UP, KEY_E0 = 0x01, 0x02
STROKE_SIZE = 20           # sizeof(InterceptionMouseStroke): every stroke has this size
WAIT_MS = 200              # how often the reader thread checks whether it should stop
PRESENCE_CHECK_SECONDS = 2 # Interception doesn't report unplugging, so look regularly

# Scan codes (set 1); (code, has E0 prefix) -> key name. Independent of NumLock.
KEY_CODES = {
    (0x45, False): "NumLock", (0x35, True): "/", (0x37, False): "*", (0x0E, False): "Backspace",
    (0x47, False): "7", (0x48, False): "8", (0x49, False): "9", (0x4A, False): "-",
    (0x4B, False): "4", (0x4C, False): "5", (0x4D, False): "6", (0x4E, False): "+",
    (0x4F, False): "1", (0x50, False): "2", (0x51, False): "3", (0x1C, True): "Enter",
    (0x52, False): "0", (0x53, False): ".",
}

Stroke = ctypes.c_ubyte * STROKE_SIZE
Predicate = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)

_lib = None


class InterceptionMissing(RuntimeError):
    pass


def _library():
    """Load interception.dll once: NUMPADCTL_INTERCEPTION_DLL, next to this file, or on PATH."""
    global _lib
    if _lib is not None:
        return _lib
    candidates = [os.environ.get("NUMPADCTL_INTERCEPTION_DLL"), Path(__file__).with_name("interception.dll"),
                  "interception.dll"]
    for candidate in filter(None, candidates):
        try:
            lib = ctypes.CDLL(str(candidate))
            break
        except OSError:
            continue
    else:
        raise InterceptionMissing(
            "interception.dll wasn't found - install the Interception driver and put its "
            "library\\x64\\interception.dll next to numpadctl\\platform\\windows_numpad.py")
    lib.interception_create_context.restype = ctypes.c_void_p
    lib.interception_destroy_context.argtypes = [ctypes.c_void_p]
    lib.interception_set_filter.argtypes = [ctypes.c_void_p, Predicate, ctypes.c_ushort]
    lib.interception_wait_with_timeout.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    lib.interception_wait_with_timeout.restype = ctypes.c_int
    lib.interception_receive.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_send.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_get_hardware_id.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_get_hardware_id.restype = ctypes.c_uint
    _lib = lib
    return lib


def _context(lib):
    context = lib.interception_create_context()
    if not context:
        raise InterceptionMissing("the Interception driver isn't running - install it and restart the PC")
    return context


def _hardware_id(lib, context, device):
    """First string of the device's hardware IDs, e.g. HID\\VID_C0F4&PID_05F5&REV_0110&MI_00."""
    buffer = ctypes.create_string_buffer(1024)
    size = lib.interception_get_hardware_id(context, device, buffer, len(buffer))
    for part in buffer.raw[:size].decode("utf-16-le", errors="replace").split("\0"):
        if part:
            return part
    return ""


def parse_ids(hardware_id):
    """("c0f4", "05f5") from a hardware ID, or None: the same format as the Linux config."""
    match = re.search(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", hardware_id)
    return (match.group(1).lower(), match.group(2).lower()) if match else None


def _keyboards(lib, context):
    """{device number: hardware id} of the keyboards Interception sees now."""
    found = {}
    for device in range(1, MAX_KEYBOARD + 1):
        hwid = _hardware_id(lib, context, device)
        if hwid:
            found[device] = hwid
    return found


def _spec(hardware_id):
    vendor, product = parse_ids(hardware_id)
    return {"vendor": vendor, "product": product, "name": hardware_id}


def list_devices():
    """[(keyboard number, vendor, product, hardware id)] of every keyboard."""
    lib = _library()
    context = _context(lib)
    try:
        return [(f"keyboard {d}", *(parse_ids(hwid) or ("????", "????")), hwid)
                for d, hwid in _keyboards(lib, context).items()]
    finally:
        lib.interception_destroy_context(context)


def detect_device(timeout=15):
    """Wait for a numpad key on any keyboard and return that keyboard's spec (or None).

    Every keyboard is captured for the moment, so every key is passed on as usual."""
    lib = _library()
    context = _context(lib)
    try:
        keyboards = _keyboards(lib, context)
        predicate = Predicate(lambda device: 1 if device in keyboards else 0)
        lib.interception_set_filter(context, predicate, FILTER_KEY_ALL)
        stroke = Stroke()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            device = lib.interception_wait_with_timeout(context, WAIT_MS)
            if device <= 0 or lib.interception_receive(context, device, stroke, 1) <= 0:
                continue
            lib.interception_send(context, device, stroke, 1)
            code, state, _ = struct.unpack_from("<HHI", bytes(stroke))
            if not state & KEY_UP and (code, bool(state & KEY_E0)) in KEY_CODES \
                    and parse_ids(keyboards.get(device, "")):
                return _spec(keyboards[device])
        return None
    finally:
        lib.interception_destroy_context(context)


class Numpad:
    """The numpad's keyboard devices (one numpad can show up as several)."""

    def __init__(self, lib, context, devices, grab):
        self._lib, self._context = lib, context
        self.devices = devices  # {device number: hardware id}
        self.grab = grab
        self._stop = threading.Event()

    @property
    def names(self):
        return list(self.devices.values())

    @property
    def spec(self):
        return _spec(min(self.devices.values(), key=len))

    def _still_there(self):
        return all(_hardware_id(self._lib, self._context, d) == hwid for d, hwid in self.devices.items())

    def _read(self, emit):
        """Reader thread: blocking Interception calls; emit((key, down)) or emit(error)."""
        lib, context, stroke = self._lib, self._context, Stroke()
        held = set()  # Windows may repeat a held key as more presses; report it once
        next_check = time.monotonic() + PRESENCE_CHECK_SECONDS
        while not self._stop.is_set():
            if time.monotonic() >= next_check:
                next_check = time.monotonic() + PRESENCE_CHECK_SECONDS
                if not self._still_there():
                    emit(OSError("the numpad was unplugged"))
                    return
            device = lib.interception_wait_with_timeout(context, WAIT_MS)
            if device not in self.devices or lib.interception_receive(context, device, stroke, 1) <= 0:
                continue
            if not self.grab:
                lib.interception_send(context, device, stroke, 1)  # also let it type as usual
            code, state, _ = struct.unpack_from("<HHI", bytes(stroke))
            key = KEY_CODES.get((code, bool(state & KEY_E0)))
            down = not state & KEY_UP
            if key is None or (down and key in held):
                continue
            (held.add if down else held.discard)(key)
            emit((key, down))

    async def events(self):
        """Yield (key name, pressed) until the numpad goes away (then raises OSError)."""
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        reader = threading.Thread(target=self._read, args=(lambda item: loop.call_soon_threadsafe(queue.put_nowait, item),),
                                  daemon=True)
        reader.start()
        try:
            while True:
                item = await queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            self._stop.set()

    def close(self):
        self._stop.set()
        time.sleep(WAIT_MS / 1000 * 1.5)  # let the reader thread notice before the context goes
        self._lib.interception_set_filter(self._context, Predicate(lambda d: 1), FILTER_KEY_NONE)
        self._lib.interception_destroy_context(self._context)


def open_numpad(spec, grab):
    """Capture the numpad's keyboard devices (by vendor/product ID); None if it isn't there."""
    lib = _library()
    context = _context(lib)
    wanted = (spec["vendor"].lower(), spec["product"].lower())
    devices = {d: hwid for d, hwid in _keyboards(lib, context).items() if parse_ids(hwid) == wanted}
    if not devices:
        lib.interception_destroy_context(context)
        return None
    # Capture only these devices; other keyboards never pass through this program.
    predicate = Predicate(lambda device: 1 if device in devices else 0)
    lib.interception_set_filter(context, predicate, FILTER_KEY_ALL)
    numpad = Numpad(lib, context, devices, grab)
    numpad._predicate = predicate  # keep the callback alive as long as the filter
    return numpad


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from numpadctl import config

    spec = config.load()["device"]
    print("Keyboards:", *[f"  {n}: {hwid}" for n, _, _, hwid in list_devices()], sep="\n")
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
