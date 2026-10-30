"""The voice changer: EasyEffects (Linux, PipeWire) runs effects on the microphone; these keys switch its presets.

Everything goes through EasyEffects' own command line (easyeffects -l / -b / -p / -a). Its input presets are the
voices (pitch down, robot, echo...), made in its window; its global bypass is the "normal voice" switch.
Apps hear the effect when they record from "Easy Effects Source" (or EasyEffects is set to process all inputs).
"""

import os
import shutil
import subprocess
import time
from pathlib import Path


class VoiceError(Exception):
    pass


READY_SECONDS = 6   # how long to wait for EasyEffects to come up after starting it
BYPASSED, ACTIVE = "1", "2"  # what `easyeffects -b 3` prints


def _run(*args, timeout=10):
    if not shutil.which("easyeffects"):
        raise VoiceError("EasyEffects isn't installed (Arch: sudo pacman -S easyeffects)")
    try:
        done = subprocess.run(["easyeffects", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise VoiceError("EasyEffects didn't answer")
    return done.stdout.strip()


def running():
    return subprocess.run(["pgrep", "-x", "easyeffects"], capture_output=True).returncode == 0


def ensure_running():
    """Start EasyEffects hidden in the background if it isn't running, and wait until it answers."""
    if running():
        return
    if not shutil.which("easyeffects"):
        raise VoiceError("EasyEffects isn't installed (Arch: sudo pacman -S easyeffects)")
    subprocess.Popen(["easyeffects", "--service-mode"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        if running() and _run("-b", "3", timeout=3) in (BYPASSED, ACTIVE):
            return
        time.sleep(0.3)
    raise VoiceError("EasyEffects didn't start")


def _preset_folders(kind):
    """Where EasyEffects keeps its presets: yours, the system's, and the Flatpak's."""
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    system = [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    return [data / "easyeffects" / kind, *(p / "easyeffects" / kind for p in system),
            home / ".var/app/com.github.wwmm.easyeffects/data/easyeffects" / kind]


def presets(kind="input"):
    """The names of EasyEffects' input (microphone) or output presets, for the settings window's pick list.

    Read from its preset folders (a preset is a .json file), so it works before EasyEffects has even started."""
    names = []
    for folder in _preset_folders(kind):
        try:
            names += sorted(p.stem for p in folder.glob("*.json"))
        except OSError:
            pass
    return list(dict.fromkeys(names))


def bypassed():
    """True while EasyEffects is switched off (global bypass)."""
    ensure_running()
    return _run("-b", "3") == BYPASSED


def set_bypass(on):
    ensure_running()
    _run("-b", "1" if on else "2")


def current_preset():
    """The input preset loaded last (text, "" if none)."""
    return _run("-a", "input")


def load(name):
    """Switch the microphone to the input preset `name` and make sure the effects are on."""
    name = name.strip()
    if not name:
        raise VoiceError("no voice preset set")
    ensure_running()
    answer = _run("-l", name)
    if "does not exist" in answer:  # it still exits normally
        known = ", ".join(presets()) or "none yet: make one in EasyEffects (Microphone tab)"
        raise VoiceError(f"EasyEffects has no preset called {name!r} (it has: {known})")
    _run("-b", "2")
    return f"Voice: {name}"


def off(normal=""):
    """Back to the normal voice: load the `normal` preset if one is named, else switch the effects off."""
    if normal.strip():
        return load(normal).replace("Voice:", "Voice (normal):")
    set_bypass(True)
    return "Voice: normal"


def toggle(preset, normal=""):
    """Voice on, or back to normal when it already is on."""
    ensure_running()
    active = not bypassed() and current_preset() == preset.strip()  # this voice is the one on right now
    return off(normal) if active else load(preset)
