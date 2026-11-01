"""Which profile set is active ("Streaming", "Coding", …).

The set names and their profiles live in the config (config.json, "sets"); the
active one lives here, in a small file shared by the service and the settings
window (like modes.py), so switching never rewrites the config and the choice
survives restarts. A lock keeps two switches at once from overwriting each other.
"""

import json
import os

from .platform import paths

STATE_DIR = paths.state_dir()
STATE_PATH = STATE_DIR / "profile_set.json"


def _locked():
    return paths.file_lock(STATE_DIR / "profile_set.lock")


def _read():
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def mtime():
    try:
        return STATE_PATH.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def active_name():
    """The saved active set's name (may not exist any more; see pick)."""
    name = _read().get("active")
    return name if isinstance(name, str) else ""


def set_active(name):
    with _locked():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"active": name}, f)
        os.replace(tmp, STATE_PATH)
    return name


def pick(sets, name):
    """The set called `name` (ignoring case), else the first one."""
    wanted = (name or "").strip().lower()
    for item in sets:
        if item["name"].lower() == wanted:
            return item
    return sets[0]
