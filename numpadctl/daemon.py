"""Background service: reads the numpad and fires the bound actions.

It also listens on a Unix socket so the settings window can show whether the
service is running, light up keys as they're pressed, and use "learn" mode.
"""

import asyncio
import json
import logging
import os
import select
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evdev
from evdev import ecodes

from . import actions, config

log = logging.getLogger("numpadctl")

ZERO_BURST_WINDOW = 0.06  # the "000" key sends KEY_KP0 three times within a few ms
HOLD_TIME = 0.45          # held this long = "hold"
DOUBLE_TAP_TIME = 0.3     # second press within this = "double tap"
REPEAT_DELAY = 0.4        # repeating actions start after this...
REPEAT_INTERVAL = 0.08    # ...and then run this often

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) \
    / "numpad-control.sock"

CODE_TO_KEY = {ecodes.ecodes[name]: key
               for key, names in config.KEYS.items() for name in names}
KP0 = ecodes.KEY_KP0


def find_devices(spec):
    vendor, product = int(spec["vendor"], 16), int(spec["product"], 16)
    found = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.info.vendor, dev.info.product) == (vendor, product) \
                and ecodes.EV_KEY in dev.capabilities():
            found.append(dev)
        else:
            dev.close()
    return found


def detect_device(timeout=15):
    """Wait for a numpad key press on any keyboard; return its device spec."""
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if KP0 in dev.capabilities().get(ecodes.EV_KEY, []):
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


def device_spec(dev):
    return {"vendor": f"{dev.info.vendor:04x}", "product": f"{dev.info.product:04x}",
            "name": dev.name}


active_window_class = actions.active_window_class


class Press:
    """One key between being pressed and its action being decided."""

    def __init__(self, slots):
        self.slots = slots          # {slot: binding} that apply to this press
        self.timer = None           # hold or double-tap timer
        self.repeater = None        # task re-running a repeating action
        self.done = False           # action already fired; release just cleans up
        self.waiting_double = False


class Daemon:
    def __init__(self, run_action=None):
        self.cfg = config.load()
        self.mtime = config.mtime()
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.run_action = run_action or self._submit
        self.presses = {}
        self.layer_held = False
        self.zero_events = []
        self.zero_timer = None
        self.devices = []
        self.clients = set()
        self.capturing = set()
        self.detect_future = None

    def reload_if_changed(self):
        mtime = config.mtime()
        if mtime != self.mtime:
            self.mtime = mtime
            self.cfg = config.load()
            log.info("config reloaded")

    # ------------------------------------------------------------ running actions
    def fire(self, key, slot, binding):
        log.info("key %s %s: %s", key, slot, binding["action"])
        self.run_action(key, binding, slot)

    def _submit(self, key, binding, slot):
        self.pool.submit(self._run, key, binding, slot)

    def _run(self, key, binding, slot):
        try:
            output = actions.run(self.cfg, binding, trigger=slot)
            if output and not actions.BY_ID[binding["action"]].osd_icon:
                log.info("key %s output:\n%s", key, output)
        except Exception as e:
            log.warning("key %s failed: %s", key, e)
            actions.notify(f"Numpad key {key} failed", str(e))

    def start_repeat(self, key, press, slot, delay=None):
        delay = REPEAT_DELAY if delay is None else delay
        binding = press.slots[slot]
        action = actions.BY_ID.get(binding["action"])
        if action is None or not action.repeat:
            return

        async def repeat():
            await asyncio.sleep(delay)
            while True:
                self.run_action(key, binding, slot)
                await asyncio.sleep(REPEAT_INTERVAL)
        press.repeater = asyncio.get_running_loop().create_task(repeat())

    # ------------------------------------------------------------ raw events
    def on_event(self, code, down):
        if code == KP0:
            # Buffer 0s briefly: three in a burst is the "000" key.
            self.zero_events.append(down)
            if self.zero_timer is None:
                self.zero_timer = asyncio.get_running_loop().call_later(
                    ZERO_BURST_WINDOW, self.flush_zeros)
            return
        self.flush_zeros()
        key = CODE_TO_KEY.get(code)
        if key is None:
            if down:
                log.info("unmapped key %s", ecodes.KEY.get(code, code))
            return
        self.key_event(key, down)

    def flush_zeros(self):
        if self.zero_timer:
            self.zero_timer.cancel()
            self.zero_timer = None
        events, self.zero_events = self.zero_events, []
        downs = events.count(True)
        if downs >= 3:
            for _ in range(downs // 3):
                self.key_event("000", True)
                self.key_event("000", False)
            for _ in range(downs % 3):
                self.key_event("0", True)
                self.key_event("0", False)
            return
        for down in events:
            self.key_event("0", down)

    def key_event(self, key, down):
        if down:
            self.broadcast({"event": "key", "key": key})
        if self.detect_future and not self.detect_future.done():
            if down:
                self.detect_future.set_result(self.current_device_spec())
            return
        if self.capturing:  # the settings window is in learn mode
            return
        if key == self.cfg.get("layer_key"):
            self.layer_held = down
            return
        if down:
            self.press(key)
        else:
            self.release(key)

    # ------------------------------------------------------------ tap / hold / double
    def press(self, key):
        self.reload_if_changed()
        current = self.presses.get(key)
        if current and current.waiting_double:
            current.timer.cancel()
            current.waiting_double = False
            current.done = True
            self.fire(key, "double", current.slots["double"])
            return
        if current:
            self.cancel(current)

        window = active_window_class() if len(self.cfg["profiles"]) > 1 else ""
        slots = config.resolve(self.cfg, key, self.layer_held, window)
        if key in config.TAP_ONLY_KEYS:
            slots = {s: b for s, b in slots.items() if s == "tap"}
        if not slots:
            log.info("key %s: not bound", key)
            return

        press = Press(slots)
        self.presses[key] = press
        if "hold" in slots:
            press.timer = asyncio.get_running_loop().call_later(HOLD_TIME, self.on_hold, key)
        elif "double" not in slots:
            # Only a tap action: run it right away, no waiting.
            press.done = True
            self.fire(key, "tap", slots["tap"])
            self.start_repeat(key, press, "tap")

    def on_hold(self, key):
        press = self.presses.get(key)
        if press is None:
            return
        press.timer = None
        press.done = True
        self.fire(key, "hold", press.slots["hold"])
        self.start_repeat(key, press, "hold", delay=0)  # already held long enough

    def release(self, key):
        press = self.presses.get(key)
        if press is None:
            return
        if press.repeater:
            press.repeater.cancel()
            press.repeater = None
        if press.done:
            del self.presses[key]
            return
        if press.timer:  # let go before the hold time
            press.timer.cancel()
            press.timer = None
        if "double" in press.slots:
            press.waiting_double = True
            press.timer = asyncio.get_running_loop().call_later(
                DOUBLE_TAP_TIME, self.on_double_timeout, key)
            return
        del self.presses[key]
        if "tap" in press.slots:
            self.fire(key, "tap", press.slots["tap"])

    def on_double_timeout(self, key):
        press = self.presses.pop(key, None)
        if press and "tap" in press.slots:
            self.fire(key, "tap", press.slots["tap"])

    @staticmethod
    def cancel(press):
        if press.timer:
            press.timer.cancel()
        if press.repeater:
            press.repeater.cancel()

    def reset(self):
        for press in self.presses.values():
            self.cancel(press)
        self.presses.clear()
        self.layer_held = False
        self.zero_events = []
        if self.zero_timer:
            self.zero_timer.cancel()
            self.zero_timer = None

    # ------------------------------------------------------------ settings window link
    def status(self):
        return {"event": "status", "connected": bool(self.devices),
                "devices": [d.name for d in self.devices]}

    def current_device_spec(self):
        if not self.devices:
            return None
        return device_spec(min(self.devices, key=lambda d: len(d.name)))

    @staticmethod
    def send(writer, message):
        try:
            writer.write((json.dumps(message) + "\n").encode())
        except (ConnectionError, RuntimeError):
            pass

    def broadcast(self, message):
        for writer in list(self.clients):
            self.send(writer, message)

    async def handle_client(self, reader, writer):
        self.clients.add(writer)
        self.send(writer, self.status())
        try:
            while line := await reader.readline():
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                command = message.get("cmd")
                if command == "capture":
                    if message.get("on"):
                        self.capturing.add(writer)
                    else:
                        self.capturing.discard(writer)
                elif command == "detect":
                    asyncio.create_task(self.detect(writer))
                elif command == "status":
                    self.send(writer, self.status())
        except ConnectionError:
            pass
        finally:
            self.clients.discard(writer)
            self.capturing.discard(writer)
            writer.close()

    async def detect(self, writer):
        """Next numpad key pressed: ours (we hold it grabbed) or any other keyboard."""
        loop = asyncio.get_running_loop()
        future = self.detect_future = loop.create_future()

        def other_keyboards():
            try:
                spec = detect_device(15)
            except RuntimeError:
                spec = None
            if spec:
                loop.call_soon_threadsafe(lambda: future.done() or future.set_result(spec))
        threading.Thread(target=other_keyboards, daemon=True).start()
        try:
            spec = await asyncio.wait_for(asyncio.shield(future), 15)
        except asyncio.TimeoutError:
            spec = None
        self.detect_future = None
        self.send(writer, {"event": "detected", "spec": spec})

    async def serve(self):
        SOCKET_PATH.unlink(missing_ok=True)
        await asyncio.start_unix_server(self.handle_client, path=str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o600)

    # ------------------------------------------------------------ device loop
    async def read(self, dev):
        async for ev in dev.async_read_loop():
            if ev.type == ecodes.EV_KEY and ev.value in (0, 1):  # ignore autorepeat
                self.on_event(ev.code, ev.value == 1)

    async def watch_device_settings(self):
        """Return when the device or grab setting changes so we reopen."""
        current = (self.cfg["device"], self.cfg["grab"])
        while True:
            await asyncio.sleep(2)
            self.reload_if_changed()
            if (self.cfg["device"], self.cfg["grab"]) != current:
                log.info("device settings changed, reopening")
                return

    async def main(self):
        await self.serve()
        waiting_logged = False
        while True:
            self.reload_if_changed()
            devices = find_devices(self.cfg["device"])
            if not devices:
                if not waiting_logged:
                    log.info("numpad %s:%s not found (unplugged, or udev rule missing?)",
                             self.cfg["device"]["vendor"], self.cfg["device"]["product"])
                    waiting_logged = True
                await asyncio.sleep(2)
                continue
            waiting_logged = False
            for dev in devices:
                log.info("listening on %s (%s)", dev.path, dev.name)
                if self.cfg["grab"]:
                    try:
                        dev.grab()
                    except OSError as e:
                        log.warning("could not grab %s: %s", dev.path, e)
            self.devices = devices
            self.broadcast(self.status())

            tasks = [asyncio.create_task(self.read(d)) for d in devices]
            tasks.append(asyncio.create_task(self.watch_device_settings()))
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                if task.exception():
                    log.info("device disconnected: %s", task.exception())
            for dev in devices:
                try:
                    dev.close()
                except OSError:
                    pass
            self.devices = []
            self.reset()
            self.broadcast(self.status())


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        asyncio.run(Daemon().main())
    except KeyboardInterrupt:
        pass
    finally:
        SOCKET_PATH.unlink(missing_ok=True)
