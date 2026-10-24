"""Reading the numpad on Linux: evdev devices, grabbed so they don't also type.

Produces key names ("5", "Enter", "0", …) for the service; a burst of three
"0"s (the "000" key) is recognised by the service, not here.
"""

import asyncio
import logging
import select
import time

import evdev
from evdev import ecodes

log = logging.getLogger("numpadctl")

# Key name -> evdev key codes that produce it.
KEY_CODES = {
    "NumLock": ["KEY_NUMLOCK"],
    "/": ["KEY_KPSLASH"],
    "*": ["KEY_KPASTERISK"],
    "Backspace": ["KEY_BACKSPACE"],
    "7": ["KEY_KP7"], "8": ["KEY_KP8"], "9": ["KEY_KP9"],
    "-": ["KEY_KPMINUS"],
    "4": ["KEY_KP4"], "5": ["KEY_KP5"], "6": ["KEY_KP6"],
    "+": ["KEY_KPPLUS"],
    "1": ["KEY_KP1"], "2": ["KEY_KP2"], "3": ["KEY_KP3"],
    "Enter": ["KEY_KPENTER"],
    "0": ["KEY_KP0"],
    ".": ["KEY_KPDOT", "KEY_KPCOMMA"],
}
CODE_TO_KEY = {ecodes.ecodes[name]: key for key, names in KEY_CODES.items() for name in names}


def device_spec(dev):
    return {"vendor": f"{dev.info.vendor:04x}", "product": f"{dev.info.product:04x}",
            "name": dev.name}


def list_devices():
    """[(path, vendor, product, name)] of every readable input device."""
    result = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        result.append((path, f"{dev.info.vendor:04x}", f"{dev.info.product:04x}", dev.name))
        dev.close()
    return result


def detect_device(timeout=15):
    """Wait for a numpad key press on any keyboard; return its device spec (or None)."""
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if ecodes.KEY_KP0 in dev.capabilities().get(ecodes.EV_KEY, []):
            devices.append(dev)
        else:
            dev.close()
    if not devices:
        raise RuntimeError("no readable keyboards found - is the udev rule installed?")
    try:
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select(devices, [], [], remaining)
            for dev in ready:
                for ev in dev.read():
                    if ev.type == ecodes.EV_KEY and ev.value == 1 and ev.code in CODE_TO_KEY:
                        return device_spec(dev)
        return None
    finally:
        for dev in devices:
            dev.close()


class Numpad:
    """The opened input devices of one numpad (a USB numpad often has several)."""

    def __init__(self, devices):
        self.devices = devices

    @property
    def names(self):
        return [d.name for d in self.devices]

    @property
    def spec(self):
        return device_spec(min(self.devices, key=lambda d: len(d.name)))

    async def events(self):
        """Yield (key name, pressed) until a device goes away (then raises OSError)."""
        queue = asyncio.Queue()

        async def pump(dev):
            try:
                async for ev in dev.async_read_loop():
                    if ev.type != ecodes.EV_KEY or ev.value not in (0, 1):  # ignore autorepeat
                        continue
                    key = CODE_TO_KEY.get(ev.code)
                    if key is None:
                        if ev.value == 1:
                            log.info("unmapped key %s", ecodes.KEY.get(ev.code, ev.code))
                        continue
                    await queue.put((key, ev.value == 1))
            except OSError as e:
                await queue.put(e)

        tasks = [asyncio.create_task(pump(d)) for d in self.devices]
        try:
            while True:
                item = await queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            for task in tasks:
                task.cancel()

    def close(self):
        for dev in self.devices:
            try:
                dev.close()
            except OSError:
                pass


def open_numpad(spec, grab):
    """Open (and grab) every input device of the numpad; None if it isn't there."""
    vendor, product = int(spec["vendor"], 16), int(spec["product"], 16)
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.info.vendor, dev.info.product) == (vendor, product) \
                and ecodes.EV_KEY in dev.capabilities():
            devices.append(dev)
        else:
            dev.close()
    if not devices:
        return None
    for dev in devices:
        log.info("listening on %s (%s)", dev.path, dev.name)
        if grab:
            try:
                dev.grab()
            except OSError as e:
                log.warning("could not grab %s: %s", dev.path, e)
    return Numpad(devices)
