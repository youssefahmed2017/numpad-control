"""numpad-control check: a guided test of a numpad model, for the compatibility list.

It finds the numpad (press any key on it), then asks for each key in turn, a held key
and the 000 key, and prints a summary plus one line for docs/compatibility.md. Keys a
model doesn't have are skipped by waiting: nothing pressed for a few seconds = "not on
this numpad". Run it with the service stopped, so the numpad is free.
"""

import asyncio
import platform
import sys
import time

from . import daemon, ui_common
from .platform import ipc, numpad_input

KEY_WAIT = 6        # seconds to press each key before it counts as missing
SETTLE = 0.35       # after a key, events this soon still belong to it (000's burst, the release)
HOLD_SECONDS = 2

KEYS = [key for key, *_ in ui_common.LAYOUT if key != "000"]


def judge_key(expected, events):
    """events: [(key, down, t)] seen after asking for `expected`. -> "ok", "missing" or "sent X"."""
    downs = [key for key, down, _ in events if down]
    if not downs:
        return "missing"
    return "ok" if downs[0] == expected else f"sent {downs[0]}"


def judge_hold(events):
    downs = [k for k, down, _ in events if down]
    ups = [k for k, down, _ in events if not down]
    if not downs:
        return "missing"
    if len(downs) == 1 and len(ups) == 1:
        return "ok"
    return f"{len(downs)} presses for one hold"


def judge_000(events):
    """The 000 key sends three 0s within a few milliseconds; the service makes that one key."""
    times = [t for key, down, t in events if key == "0" and down]
    if not times:
        return "missing"
    if len(times) >= 3 and times[2] - times[0] <= daemon.ZERO_BURST_WINDOW:
        return "ok"
    if len(times) >= 3:
        return f"three 0s, but {1000 * (times[2] - times[0]):.0f} ms apart (too slow to be one key)"
    return f"{len(times)} zero(s): no 000 key, or it sends something else"


class Recorder:
    """Collects the numpad's events in the background; take() waits for the next batch."""

    def __init__(self, numpad):
        self.numpad, self.queue = numpad, asyncio.Queue()

    async def run(self):
        async for key, down in self.numpad.events():
            self.queue.put_nowait((key, down, time.monotonic()))

    def drain(self):
        while not self.queue.empty():
            self.queue.get_nowait()

    async def take(self, wait, settle=SETTLE):
        """Events from the first one (within `wait` s) until none came for `settle` s."""
        events = []
        try:
            events.append(await asyncio.wait_for(self.queue.get(), wait))
            while True:
                events.append(await asyncio.wait_for(self.queue.get(), settle))
        except asyncio.TimeoutError:
            return events


async def run_checks(numpad, say=print):
    recorder = Recorder(numpad)
    reader = asyncio.create_task(recorder.run())
    results = {}
    try:
        say(f"\nPress each key when asked. A key your numpad doesn't have: just wait {KEY_WAIT} seconds.\n")
        for key in KEYS:
            recorder.drain()
            say(f"  Press  {key:<10}", end=" ", flush=True)
            results[key] = judge_key(key, await recorder.take(KEY_WAIT))
            say(results[key])
        recorder.drain()
        say(f"  Hold 5 for {HOLD_SECONDS} seconds, then let go", end=" ", flush=True)
        results["hold"] = judge_hold(await recorder.take(KEY_WAIT, settle=HOLD_SECONDS + 1))
        say(results["hold"])
        recorder.drain()
        say("  Press  000 (if your numpad has it)", end=" ", flush=True)
        results["000"] = judge_000(await recorder.take(KEY_WAIT))
        say(results["000"])
    finally:
        reader.cancel()
    return results


def summary(spec, results, model):
    keys = {k: v for k, v in results.items() if k in KEYS}
    working = sum(v == "ok" for v in keys.values())
    missing = [k for k, v in keys.items() if v == "missing"]
    wrong = [f"{k} ({v})" for k, v in keys.items() if v not in ("ok", "missing")]
    good = not wrong and results.get("hold") == "ok" and results.get("000") in ("ok", "missing")
    system = f"{platform.system()} {platform.release()}"
    row = (f"| {model} | {spec['vendor']}:{spec['product']} | {system} | {working}/{len(keys)} | "
           f"{', '.join(missing) or '-'} | {results.get('hold')} | {results.get('000')} | "
           f"{'works' if good else 'problems: ' + ', '.join(wrong) if wrong else 'works, see notes'} |")
    return good, row, wrong


def service_running():
    try:
        ipc.connect().close()
        return True
    except OSError:
        return False


def main(ask=input, say=print):
    if service_running():
        say("The NumpadPilot service is running and holds the numpad. Stop it first\n"
            "(Linux: systemctl --user stop numpad-control; Windows: Quit in the tray menu),\n"
            "then run this again.")
        return 1
    say("Press any key on the numpad you want to test…")
    spec = numpad_input.detect_device(20)
    if not spec:
        say("No numpad key was pressed.")
        return 1
    say(f"Found {spec['vendor']}:{spec['product']}  ({spec.get('name', '')})")
    numpad = numpad_input.open_numpad(spec, grab=True)
    if numpad is None:
        say("It disappeared again - is it plugged in firmly?")
        return 1
    try:
        results = asyncio.run(run_checks(numpad, say=lambda *a, **k: say(*a, **k)))
    finally:
        numpad.close()
    model = ask("\nWhat is this numpad's brand and model (as on the box or the shop page)? ").strip() or "unknown"
    good, row, wrong = summary(spec, results, model)
    say("\nResult: " + ("it works with NumpadPilot." if good else "there were problems:"))
    for problem in wrong:
        say(f"  - {problem}")
    if results.get("hold") != "ok":
        say(f"  - holding a key: {results.get('hold')}")
    say("\nFor docs/compatibility.md (or paste it into a GitHub issue):\n")
    say(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
