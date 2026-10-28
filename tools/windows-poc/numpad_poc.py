"""NumpadPilot - Windows proof of concept.

Answers one question before the real Windows version is built: can Windows
tell an external numpad apart from the main keyboard, and stop only the
numpad from typing? It uses the Interception driver through its official
library (interception.dll), the same way the Windows version would.

    python numpad_poc.py              watch: shows which keyboard every key comes from
    python numpad_poc.py --block 2    also stops keyboard 2 from typing, for 30 seconds

Every key is passed on to Windows as usual, except from the blocked keyboard.
If the keyboard ever stops responding, close this window with the mouse.
"""

import argparse
import ctypes
import struct
import sys
import time
from collections import Counter
from pathlib import Path

MAX_KEYBOARD = 10
FILTER_KEY_ALL = 0xFFFF
KEY_UP, KEY_E0 = 0x01, 0x02
STROKE_SIZE = 20          # sizeof(InterceptionMouseStroke), the size of every stroke
WATCH_SECONDS = 300       # watch mode stops by itself after 5 minutes
BLOCK_SECONDS = 30        # block mode stops by itself after 30 seconds

# Scan codes (set 1) of the numpad keys; (code, has E0 prefix) -> name.
NUMPAD = {
    (0x45, False): "NumLock", (0x35, True): "/", (0x37, False): "*", (0x4A, False): "-",
    (0x47, False): "7", (0x48, False): "8", (0x49, False): "9", (0x4E, False): "+",
    (0x4B, False): "4", (0x4C, False): "5", (0x4D, False): "6",
    (0x4F, False): "1", (0x50, False): "2", (0x51, False): "3", (0x1C, True): "Enter",
    (0x52, False): "0", (0x53, False): ".",
}
OTHER = {(0x1C, False): "Enter (main)", (0x0E, False): "Backspace", (0x01, False): "Esc",
         (0x39, False): "Space", (0x1D, False): "Ctrl", (0x2A, False): "Shift"}
OTHER.update({(0x02 + i, False): f"{(i + 1) % 10} (top row)" for i in range(10)})

Stroke = ctypes.c_ubyte * STROKE_SIZE
Predicate = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)


def key_name(code, state):
    """Readable name for a scan code; numpad keys are marked as such."""
    e0 = bool(state & KEY_E0)
    if (code, e0) in NUMPAD:
        return f"numpad {NUMPAD[(code, e0)]}"
    return OTHER.get((code, e0), f"scan code {code:#04x}{' E0' if e0 else ''}")


def is_numpad_key(code, state):
    return (code, bool(state & KEY_E0)) in NUMPAD


def parse_hardware_id(raw):
    """interception_get_hardware_id gives UTF-16 strings separated by NULs; keep the first."""
    for part in raw.decode("utf-16-le", errors="replace").split("\0"):
        if part:
            return part
    return ""


def load_library(path=None):
    candidates = [Path(path)] if path else [Path(__file__).with_name("interception.dll")]
    for candidate in candidates:
        if candidate.exists():
            lib = ctypes.CDLL(str(candidate))
            break
    else:
        sys.exit("interception.dll not found next to this script - see README.md, step 3.")
    lib.interception_create_context.restype = ctypes.c_void_p
    lib.interception_destroy_context.argtypes = [ctypes.c_void_p]
    lib.interception_set_filter.argtypes = [ctypes.c_void_p, Predicate, ctypes.c_ushort]
    lib.interception_wait_with_timeout.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    lib.interception_wait_with_timeout.restype = ctypes.c_int
    lib.interception_receive.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_send.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_get_hardware_id.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    lib.interception_get_hardware_id.restype = ctypes.c_uint
    return lib


def hardware_id(lib, context, device):
    buffer = ctypes.create_string_buffer(1024)
    size = lib.interception_get_hardware_id(context, device, buffer, len(buffer))
    return parse_hardware_id(buffer.raw[:size]) if size else ""


def run(lib, block=None, seconds=None, out=print, clock=time.monotonic):
    """Watch keys (and swallow those from keyboard `block`); returns {keyboard: Counter}."""
    context = lib.interception_create_context()
    if not context:
        sys.exit("Couldn't start Interception - is the driver installed, and did you reboot after?")
    seen = {}
    try:
        keyboards = {d: hardware_id(lib, context, d) for d in range(1, MAX_KEYBOARD + 1)}
        keyboards = {d: hwid for d, hwid in keyboards.items() if hwid}
        if not keyboards:
            sys.exit("Interception sees no keyboards - is the driver installed, and did you reboot after?")
        out("Keyboards Interception can see:")
        for device, hwid in keyboards.items():
            out(f"  keyboard {device}: {hwid}")
        if block is not None:
            out(f"\nBlocking keyboard {block} for {seconds} seconds: its keys should NOT type anything.")
        out("\nPress keys on the numpad and on the main keyboard (Ctrl+C on the main keyboard stops):\n")

        predicate = Predicate(lambda device: 1 if 1 <= device <= MAX_KEYBOARD else 0)
        lib.interception_set_filter(context, predicate, FILTER_KEY_ALL)
        stroke = Stroke()
        deadline = clock() + seconds
        while clock() < deadline:
            device = lib.interception_wait_with_timeout(context, 500)
            if device <= 0 or lib.interception_receive(context, device, stroke, 1) <= 0:
                continue
            code, state, _info = struct.unpack_from("<HHI", bytes(stroke))
            blocked = device == block
            if not blocked:
                lib.interception_send(context, device, stroke, 1)  # let it type as usual
            if not state & KEY_UP:
                seen.setdefault(device, Counter())[is_numpad_key(code, state)] += 1
                out(f"  keyboard {device}: {key_name(code, state):<20}{'  (blocked)' if blocked else ''}")
    except KeyboardInterrupt:
        pass
    finally:
        lib.interception_destroy_context(context)
    return seen


def summary(seen, out=print):
    numpads = [d for d, counts in seen.items() if counts[True] and counts[True] >= counts[False]]
    out("\nSummary:")
    for device, counts in sorted(seen.items()):
        out(f"  keyboard {device}: {counts[True]} numpad keys, {counts[False]} other keys")
    if numpads:
        out(f"\nYour numpad looks like keyboard {numpads[0]}. "
            f"Next: python numpad_poc.py --block {numpads[0]}")
    else:
        out("\nNo keyboard sent mostly numpad keys - press some keys on the numpad next time.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--block", type=int, metavar="N", help="stop keyboard N from typing (for 30 seconds)")
    parser.add_argument("--dll", help="path to interception.dll (default: next to this script)")
    args = parser.parse_args()
    lib = load_library(args.dll)
    seen = run(lib, block=args.block, seconds=BLOCK_SECONDS if args.block else WATCH_SECONDS)
    summary(seen)


if __name__ == "__main__":
    main()
