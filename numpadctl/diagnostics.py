"""A plain-text report about this install, for bug reports: paste it as it is.

collect() gathers everything (it can take a few seconds: run it in the background).
It never includes passwords: the OBS password and anything else secret is left out.
"""

import platform
import subprocess
import sys
from pathlib import Path

from . import actions, config
from .platform import IS_WINDOWS, paths

LOG_LINES = 50
ROOT = Path(__file__).resolve().parent.parent


def _run(command, timeout=10):
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              creationflags=0x08000000 if IS_WINDOWS else 0)  # no console window
        return (done.stdout + done.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"({e})"


def version():
    from . import __version__
    commit = _run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
    return f"{__version__} ({commit})" if commit and " " not in commit else __version__


def binding_problems(cfg):
    """["Profile · key slot: problem"] for every binding that wouldn't work."""
    found = []
    for profile in cfg.get("profiles", []):
        for where, bindings in (("", profile.get("bindings", {})), (" (layer)", profile.get("layer_bindings", {}))):
            for key, slots in bindings.items():
                for slot, binding in slots.items():
                    for problem in actions.binding_problems(binding, cfg):
                        found.append(f"{profile.get('name', '?')} · {key}{where} {slot}: {problem}")
    return found


def devices():
    """Lines about the keyboards the system shows, with the configured numpad marked."""
    from .platform import numpad_input
    device = config.load()["device"]
    want = device["vendor"].lower(), device["product"].lower()
    try:
        rows = numpad_input.list_devices()
    except Exception as e:
        return [f"could not list keyboards: {e}"]
    return [f"{'→' if (v.lower(), p.lower()) == want else ' '} {v}:{p}  {name}" for _, v, p, name in rows] \
        or ["no keyboards found"]


def log_tail():
    if IS_WINDOWS:
        path = paths.state_dir() / "numpad-control.log"
        try:
            return path.read_text(errors="replace").splitlines()[-LOG_LINES:]
        except OSError:
            return [f"(no log yet at {path})"]
    out = _run(["journalctl", "--user", "-u", "numpad-control", "-n", str(LOG_LINES), "--no-pager", "-o", "cat"])
    return out.splitlines() or ["(the journal has nothing for numpad-control)"]


def usb_errors():
    """Linux: how often the kernel failed to set the numpad up (a cable, port or hardware problem)."""
    if IS_WINDOWS:
        return None
    lines = _run(["journalctl", "-k", "-b", "--no-pager"]).splitlines()
    bad = [line for line in lines if "unable to enumerate USB device" in line or "device descriptor read" in line]
    return bad[-3:], len(bad)


def collect(cfg, status):
    """status: the service's last "status" message ({"running", "connected", "devices"})."""
    device = cfg.get("device", {})
    out = [f"NumpadPilot {version()} · {platform.platform()} · Python {sys.version.split()[0]}",
           f"Config: {config.CONFIG_PATH}", ""]
    out.append("Service: " + ("not running" if not status.get("running")
                              else "running, numpad connected" if status.get("connected")
                              else "running, numpad NOT connected"))
    out.append(f"Configured numpad: {device.get('vendor', '?')}:{device.get('product', '?')} "
               f"(keys {'grabbed' if cfg.get('grab') else 'also type'})")
    out += ["", "Keyboards the system sees (→ = the configured numpad):", *devices()]
    usb = usb_errors()
    if usb and usb[1]:
        out += ["", f"USB: the kernel failed {usb[1]} times to set up a device this boot (cable, port or hardware?):",
                *usb[0]]
    problems = binding_problems(cfg)
    out += ["", f"Key problems: {len(problems)}" if problems else "Key problems: none", *problems]
    out += ["", f"Last {LOG_LINES} log lines:", *log_tail()]
    return "\n".join(out)
