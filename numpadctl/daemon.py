"""Background service: reads the numpad and fires the bound actions.

It also listens on a Unix socket so the settings window can show whether the
service is running, light up keys as they're pressed, and use "learn" mode.
"""

import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import actions, config, games, keys, updater
from .platform import ipc, numpad_input, processes

log = logging.getLogger("numpadctl")

ZERO_BURST_WINDOW = 0.06  # the "000" key sends "0" three times within a few ms
HOLD_TIME = 0.45          # held this long = "hold"
DOUBLE_TAP_TIME = 0.3     # second press within this = "double tap"
REPEAT_DELAY = 0.4        # repeating actions start after this...
REPEAT_INTERVAL = 0.08    # ...and then run this often
RAPID_DELAY = 2.0         # a Hold action with rapid-fire on starts repeating after this much more holding
GAME_CHECK_SECONDS = 3    # how often the running programs are checked for a game with anti-cheat
MISSING_NOTICE = 5        # seconds the numpad must stay missing before saying so (not for a wobbly plug)
RETRY_DELAYS = (1, 2, 5, 10, 30)  # seconds before reopening a numpad whose reader keeps failing at once
QUICK_FAILURE = 5         # a reader that fails within this many seconds counts as failing at once
UPDATE_FIRST_CHECK = 60   # seconds after starting before looking for an update (not slowing the start)
UPDATE_LOOP_SECONDS = 3600  # how often it wakes to see whether the daily check is due

# Used by the settings window and install.sh.
detect_device = numpad_input.detect_device

active_window_class = actions.active_window_class


class Press:
    """One key between being pressed and its action being decided."""

    def __init__(self, slots):
        self.slots = slots          # {slot: binding} that apply to this press
        self.timer = None           # hold or double-tap timer
        self.repeater = None        # task re-running a repeating action
        self.done = False           # action already fired; release just cleans up
        self.waiting_double = False


def _restart_in_place():
    """Run the updated code: replace this process with a fresh service (same PID under systemd)."""
    import os
    import sys
    os.chdir(updater.ROOT)
    os.execv(sys.executable, [sys.executable, "-m", "numpadctl", "run"])


class Daemon:
    def __init__(self, run_action=None, restart=None):
        self.cfg = config.load()
        self.mtime = config.mtime()
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.run_action = run_action or self._submit
        self.presses = {}
        self.layer_held = False
        self.zero_events = []
        self.zero_timer = None
        self.numpad = None
        self.paused = False  # Windows tray "Pause": keys are still captured, but do nothing
        self.paused_for = None  # name of the game with anti-cheat the numpad is let go for
        self.missing_notified = False  # told the user the numpad is missing (so say when it's back)
        self.restart = restart or _restart_in_place  # after an update (the Windows tray brings its own)
        self.clients = set()
        self.capturing = set()
        self.following = set()  # capturing clients that only want keys to select, not to learn new ones
        self.raw_clients = set()  # key tester windows: want every raw key event
        self.detect_future = None

    def reload_if_changed(self):
        mtime = config.mtime()
        if mtime != self.mtime:
            self.mtime = mtime
            self.cfg = config.load()
            log.info("config reloaded")
            self.sync_extra_keys()

    # ------------------------------------------------------------ running actions
    def fire(self, key, slot, binding):
        log.info("key %s %s: %s", key, slot, binding["action"])
        self.run_action(key, binding, slot)

    def _submit(self, key, binding, slot):
        return self.pool.submit(self._run, key, binding, slot)

    def _run(self, key, binding, slot):
        try:
            output = actions.run(self.cfg, binding, trigger=slot)
            if output and not actions.BY_ID[binding["action"]].osd_icon:
                log.info("key %s output:\n%s", key, output)
        except Exception as e:
            log.warning("key %s failed: %s", key, e)
            actions.notify(f"Numpad key {key} failed", str(e))

    def start_repeat(self, key, press, slot, delay=None, force=False):
        """Re-run the slot's action while the key stays down.

        Repeats actions marked repeat=True, or any action when force is set
        (a Hold slot with rapid-fire on)."""
        delay = REPEAT_DELAY if delay is None else delay
        binding = press.slots[slot]
        action = actions.BY_ID.get(binding["action"])
        if action is None or action.confirm or not (action.repeat or force):
            return

        async def repeat():
            await asyncio.sleep(delay)
            running = None
            while True:
                # A slow action (e.g. a macro) finishes before the next one starts.
                if running is None or running.done():
                    running = self.run_action(key, binding, slot)
                await asyncio.sleep(REPEAT_INTERVAL)
        press.repeater = asyncio.get_running_loop().create_task(repeat())

    # ------------------------------------------------------------ keys from the numpad
    def on_key(self, key, down):
        if key == "0":
            # Buffer 0s briefly: three in a burst is the "000" key.
            self.zero_events.append(down)
            if self.zero_timer is None:
                self.zero_timer = asyncio.get_running_loop().call_later(
                    ZERO_BURST_WINDOW, self.flush_zeros)
            return
        self.flush_zeros()
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
            downs %= 3
        elif not (downs == 2 and self.double_zero_wanted()):
            for down in events:
                self.key_event("0", down)
            return
        if downs == 2 and self.double_zero_wanted():  # a "00" key
            self.key_event(keys.DOUBLE_ZERO, True)
            self.key_event(keys.DOUBLE_ZERO, False)
            return
        for _ in range(downs):
            self.key_event("0", True)
            self.key_event("0", False)

    def sync_extra_keys(self):
        """Tell the input backend which keys were added in Learn mode, and whether Learn mode is on (Windows'
        Raw Input backend only takes over the keys it is told about; the others read everything the numpad sends)."""
        setter = getattr(self.numpad, "set_extra_keys", None)
        if setter:
            setter(keys.extra_ids(self.cfg), self.learning())

    def learning(self):
        return bool(self.capturing - self.following)

    def double_zero_wanted(self):
        """Two 0s in a burst are a "00" key only once you have added one (or are teaching the pad new keys)."""
        return self.learning() or keys.DOUBLE_ZERO in keys.extra_ids(self.cfg)

    def key_event(self, key, down):
        if down:
            self.broadcast({"event": "key", "key": key, "label": keys.label_for(key),
                            "unknown": not keys.known(key, self.cfg)})
        if self.detect_future and not self.detect_future.done():
            if down:
                self.detect_future.set_result(self.current_device_spec())
            return
        if self.capturing or self.paused:  # learn mode in the settings window, or paused
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
        if not actions.refresh_session_env():
            log.warning("no desktop session found yet - apps and windows can't open")
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
        if actions.rapid_fire(press.slots["hold"]):
            self.start_repeat(key, press, "hold", delay=RAPID_DELAY, force=True)

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
        return {"event": "status", "connected": self.numpad is not None,
                "devices": self.numpad.names if self.numpad else [], "paused_for": self.paused_for}

    def current_device_spec(self):
        return self.numpad.spec if self.numpad else None

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
                        (self.following.discard if message.get("learn", True) else self.following.add)(writer)
                    else:
                        self.capturing.discard(writer)
                        self.following.discard(writer)
                    self.sync_extra_keys()
                elif command == "raw":
                    (self.raw_clients.add if message.get("on") else self.raw_clients.discard)(writer)
                elif command == "detect":
                    asyncio.create_task(self.detect(writer))
                elif command == "status":
                    self.send(writer, self.status())
        except ConnectionError:
            pass
        finally:
            self.clients.discard(writer)
            self.capturing.discard(writer)
            self.following.discard(writer)
            self.sync_extra_keys()
            self.raw_clients.discard(writer)
            writer.close()

    async def detect(self, writer):
        """Next numpad key pressed: ours (we hold it grabbed) or any other keyboard."""
        loop = asyncio.get_running_loop()
        future = self.detect_future = loop.create_future()

        def other_keyboards():
            try:
                spec = numpad_input.detect_device(15)
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
        await ipc.start_server(self.handle_client)

    # ------------------------------------------------------------ device loop
    async def read(self, numpad):
        async for key, down in numpad.events():
            for writer in list(self.raw_clients):
                self.send(writer, {"event": "raw", "key": key, "down": down, "t": time.monotonic()})
            self.on_key(key, down)

    async def watch_device_settings(self):
        """Return when the device or grab setting changes so we reopen."""
        current = (self.cfg["device"], self.cfg["grab"])
        while True:
            await asyncio.sleep(2)
            self.reload_if_changed()
            if (self.cfg["device"], self.cfg["grab"]) != current:
                log.info("device settings changed, reopening")
                return

    async def protected_game(self):
        """The game with anti-cheat running now (when that setting is on), or None."""
        if not games.enabled(self.cfg):
            return None
        try:
            running = await asyncio.to_thread(processes.running)
        except OSError as e:
            log.warning("couldn't check for games: %s", e)
            return None
        return games.protected_game(self.cfg, running)

    async def watch_games(self):
        """Return when a game with anti-cheat starts, so the numpad is let go."""
        while True:
            await asyncio.sleep(GAME_CHECK_SECONDS)
            if await self.protected_game():
                return

    def set_paused_for(self, game):
        if game == self.paused_for:
            return
        self.paused_for = game
        if game:
            log.info("%s is running: the numpad is let go until it closes", game)
            actions.notify("Numpad paused", f"{game} is running, so the numpad types normally until it closes.")
        else:
            log.info("the game closed: taking the numpad back")
            actions.notify("Numpad back", "The game closed; your numpad keys run their actions again.")
        self.broadcast(self.status())

    async def update_loop(self):
        """Once a day: look for a newer release; install it and restart (or only say so)."""
        await asyncio.sleep(UPDATE_FIRST_CHECK)
        told = None
        while True:
            mode = self.cfg.get("updates", "auto")
            if mode == "auto" and updater.packaged():
                mode = "notify"  # the package manager installs updates, not us
            if mode in ("auto", "notify") and updater.due():
                tag = await asyncio.to_thread(updater.check)
                if tag and mode == "notify" and tag != told:
                    told = tag
                    actions.notify("NumpadPilot update", f"Version {tag[1:]} is out: " + (
                                       "update it with your package manager." if updater.packaged() else
                                       "run the installer or `python -m numpadctl update` to get it."))
                elif tag and mode == "auto":
                    while self.presses or self.layer_held:  # not in the middle of using the numpad
                        await asyncio.sleep(5)
                    try:
                        await asyncio.to_thread(updater.install, tag)
                    except (updater.UpdateError, OSError) as e:
                        log.warning("update to %s failed: %s", tag, e)
                        actions.notify("NumpadPilot couldn't update", str(e))
                    else:
                        actions.notify("NumpadPilot updated", f"Now version {tag[1:]}; restarting.")
                        self.shutdown()
                        self.restart()
                        return
            await asyncio.sleep(UPDATE_LOOP_SECONDS)

    def shutdown(self):
        """Let the numpad and the connection go (before restarting into new code)."""
        if self.numpad is not None:
            self.numpad.close()
            self.numpad = None
        ipc.stop_server()

    async def main(self):
        await self.serve()
        updates = asyncio.create_task(self.update_loop())
        try:
            await self._device_loop()
        finally:  # quitting (the task is cancelled): let the numpad and the connection go
            updates.cancel()
            if self.numpad is not None:
                self.numpad.close()
                self.numpad = None
            ipc.stop_server()

    def numpad_missing(self, since):
        """Say once that the numpad is missing (after MISSING_NOTICE seconds of it being gone)."""
        if not self.missing_notified and time.monotonic() - since >= MISSING_NOTICE:
            self.missing_notified = True
            actions.notify("Numpad not found", "Plug your numpad in; NumpadPilot picks it up by itself.")

    def numpad_found(self):
        if self.missing_notified:
            self.missing_notified = False
            actions.notify("Numpad connected", "Your numpad keys run their actions again.")

    async def _device_loop(self):
        waiting_logged = False
        missing_since = None
        quick_failures = 0
        while True:
            self.reload_if_changed()
            game = await self.protected_game()
            self.set_paused_for(game)
            if game:
                await asyncio.sleep(GAME_CHECK_SECONDS)
                continue
            numpad = numpad_input.open_numpad(self.cfg["device"], self.cfg["grab"])
            if numpad is None:
                if not waiting_logged:
                    log.info("numpad %s:%s not found (unplugged, or udev rule missing?)",
                             self.cfg["device"]["vendor"], self.cfg["device"]["product"])
                    waiting_logged = True
                missing_since = missing_since or time.monotonic()
                self.numpad_missing(missing_since)
                await asyncio.sleep(2)
                continue
            waiting_logged = False
            missing_since = None
            self.numpad_found()
            self.numpad = numpad
            self.sync_extra_keys()
            self.broadcast(self.status())

            opened = time.monotonic()
            tasks = [asyncio.create_task(self.read(numpad)),
                     asyncio.create_task(self.watch_device_settings())]
            if games.enabled(self.cfg):
                tasks.append(asyncio.create_task(self.watch_games()))
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            failed = None
            for task in done:
                if task.exception():
                    failed = task.exception()
            numpad.close()
            self.numpad = None
            self.reset()
            self.broadcast(self.status())
            if failed is None:
                quick_failures = 0
                continue
            if time.monotonic() - opened >= QUICK_FAILURE:
                quick_failures = 0
                log.info("device disconnected: %s", failed)
                continue
            # Failing right away again and again (e.g. Windows refusing the keyboard hook):
            # wait longer each time instead of retrying thousands of times a second.
            delay = RETRY_DELAYS[min(quick_failures, len(RETRY_DELAYS) - 1)]
            quick_failures += 1
            if quick_failures <= 3 or delay == RETRY_DELAYS[-1] and quick_failures % 10 == 0:
                log.warning("the numpad reader failed (%s); trying again in %s s", failed, delay)
            await asyncio.sleep(delay)


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from . import crash
    crash.install("service")
    try:
        asyncio.run(Daemon().main())
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop_server()
