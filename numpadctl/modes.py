"""On/off state of the user's modes (e.g. "Stream mode").

The mode names live in the config; their current state lives here, in a small
file shared by the service and the settings window, so both always agree and
the state survives restarts. A lock keeps two key presses at once from
overwriting each other.
"""

import json
import os

from .platform import paths

STATE_DIR = paths.state_dir()
STATE_PATH = STATE_DIR / "modes.json"


def _locked():
    return paths.file_lock(STATE_DIR / "modes.lock")


def _read():
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _write(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def states():
    with _locked():
        return _read()


def is_on(name):
    return bool(states().get(name, False))


def set_mode(name, on):
    with _locked():
        state = _read()
        state[name] = bool(on)
        _write(state)
    return bool(on)


def toggle(name):
    with _locked():
        state = _read()
        state[name] = not state.get(name, False)
        _write(state)
        return state[name]
