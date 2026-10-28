"""Loading and saving ~/.config/numpad-control/config.json.

Layout:
    profiles[0] is "Default" and always applies; later profiles apply while a
    window whose class is listed in their "match" is focused, and fall back to
    Default for anything they don't set.

    profile["bindings"]        key -> {"tap": b, "hold": b, "double": b}
    profile["layer_bindings"]  same, used while the layer key is held
    b = {"action": id, "params": {...}}
"""

import json
import os

from .platform import paths

CONFIG_DIR = paths.config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"

# Key names: "NumLock", "/", "*", "Backspace", "0"-"9", "-", "+", "Enter", ".",
# and "000" (sent as three quick "0"s; the service recognises the burst).
# Each OS's input backend in platform/ maps its key codes to these names.

SLOTS = ("tap", "hold", "double")
TAP_ONLY_KEYS = {"000", "00"}  # a burst of 0s can't be held or double-tapped

DEFAULT_CONFIG = {
    "device": {"vendor": "c0f4", "product": "05f5"},
    "grab": True,       # stop the numpad from also typing digits
    "extra_keys": [],   # keys added in Learn mode: [{"id": "KEY_TAB", "label": "Tab"}] (see keys.py)
    "feedback": True,   # on-screen confirmations
    "accent": "Orchid",    # the app's settings window colour (Orchid, Blue, Green, …)
    "contrast": "standard",  # settings window: "standard", "medium" or "high" (Material 3 contrast levels)
    "appearance": "auto",  # settings window: "auto" (follow the system), "light" or "dark"
    "updates": "auto",          # install new releases by themselves; "notify" only says so; "off"
    "pause_for_games": "auto",  # let go of the numpad while a game with anti-cheat runs (auto: on Windows)
    "protected_games": [],      # more program names for that, e.g. ["MyGame.exe"] (games.py has the list)
    "layer_key": None,  # hold this key for the second set of actions
    "modes": [],        # names of on/off modes (their state is in modes.py)
    "obs": {"host": "localhost", "port": 4455, "password": ""},
    "profiles": [
        {"name": "Default", "match": "",
         "bindings": {"1": {"tap": {"action": "open_browser", "params": {}}}},
         "layer_bindings": {}},
    ],
}


def _migrate(data):
    """Upgrade older config files in place."""
    if "profiles" not in data:
        data["profiles"] = [{"name": "Default", "match": "",
                             "bindings": data.pop("bindings", {}), "layer_bindings": {}}]
    for profile in data["profiles"]:
        for kind in ("bindings", "layer_bindings"):
            keys = profile.setdefault(kind, {})
            for key, value in list(keys.items()):
                if "action" in value:  # old single-action binding
                    keys[key] = {"tap": value}
    return data


def load():
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    _migrate(data)  # before defaults, or the default profile would hide old bindings
    for key, value in DEFAULT_CONFIG.items():
        data.setdefault(key, json.loads(json.dumps(value)))
    return data


def save(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    # 0600: the file may contain the OBS websocket password.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def mtime():
    try:
        return CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def profile_matches(profile, window_class):
    classes = {c.strip().lower() for c in profile.get("match", "").split(",") if c.strip()}
    return bool(window_class) and window_class.lower() in classes


def resolve(cfg, key, layer, window_class):
    """The bindings that apply to `key` right now: {slot: binding} (set slots only)."""
    kind = "layer_bindings" if layer else "bindings"
    profiles = [p for p in cfg["profiles"][1:] if profile_matches(p, window_class)]
    profiles.append(cfg["profiles"][0])
    slots = {}
    for slot in SLOTS:
        for profile in profiles:
            binding = profile[kind].get(key, {}).get(slot)
            if binding and binding.get("action", "none") != "none":
                slots[slot] = binding
                break
    return slots
