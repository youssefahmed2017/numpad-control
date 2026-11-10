"""Loading and saving ~/.config/numpad-control/config.json.

Layout:
    sets is a list of {"name", "profiles"}: separate setups ("Streaming", "Coding")
    you switch between by hand. Which one is active is saved in profile_sets.py.
    load() puts the active set's profiles in cfg["profiles"], so everything else
    only deals with one list; save() writes them back into their set.

    In a set, profiles[0] is "Default" and always applies; later profiles apply while a
    window whose class is listed in their "match" is focused, and fall back to
    Default for anything they don't set.

    profile["bindings"]        key -> {"tap": b, "hold": b, "double": b}
    profile["layer_bindings"]  same, used while the layer key is held
    profile["stickers"]        key -> picture file name (stickers.py): the picture shown on that key
    b = {"action": id, "params": {...}}
"""

import json
import os

from . import profile_sets, stickers
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
    "devices": [],      # more devices, every key a pad key: [{"id": "hp", "vendor": "03f0", "product": "0024", "name": "HP keyboard", "grab": true}]
    "grab": True,       # stop the numpad from also typing digits
    "numpad_layout": "standard",  # where the keys are drawn: "standard" or "backspace_below" (ui_common.LAYOUTS)
    "extra_keys": [],   # keys added in Learn mode: [{"id": "KEY_TAB", "label": "Tab"}] (see keys.py)
    "feedback": True,   # on-screen confirmations
    "accent": "Orchid",    # the app's settings window colour (Orchid, Blue, Green, …)
    "contrast": "standard",  # settings window: "standard", "medium" or "high" (Material 3 contrast levels)
    "appearance": "auto",  # settings window: "auto" (follow the system), "light" or "dark"
    "updates": "auto",          # install new releases by themselves; "notify" only says so; "off"
    "pause_for_games": "auto",  # with a game with anti-cheat running: "hook" = drop only the keyboard hook, "full" = let go of the numpad (auto: hook on Windows)
    "protected_games": [],      # more program names for that, e.g. ["MyGame.exe"] (games.py has the list)
    "welcomed": False,  # the first-run welcome has been seen
    "hud": {"enabled": True, "opacity": 90},  # the key map shown while the layer key is held (opacity in %)
    "layer_key": None,  # hold this key for the second set of actions
    "modes": [],        # names of on/off modes (their state is in modes.py)
    "obs": {"host": "localhost", "port": 4455, "password": ""},
    "profiles": [
        {"name": "Default", "match": "",
         "bindings": {"1": {"tap": {"action": "open_browser", "params": {}}}},
         "layer_bindings": {}},
    ],
}


def _clean_sets(data):
    """The "sets" list, repaired if hand-edited: named, unique, each with profiles."""
    sets, seen = [], set()
    for item in data.get("sets") if isinstance(data.get("sets"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"].strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        profiles = item.get("profiles") if isinstance(item.get("profiles"), list) else []
        sets.append({"name": name, "profiles": profiles})
    if not sets:
        sets = [{"name": "Default", "profiles": []}]
    for item in sets:
        if not item["profiles"]:
            item["profiles"].append({"name": "Default", "match": "", "bindings": {}, "layer_bindings": {}})
        for profile in item["profiles"]:
            stickers.clean(profile)
            for kind in ("bindings", "layer_bindings"):
                keys = profile.setdefault(kind, {})
                for key, value in list(keys.items()):
                    if "action" in value:  # old single-action binding
                        keys[key] = {"tap": value}
    return sets


def _migrate(data):
    """Upgrade older config files in place.

    Files from before profile sets have a "profiles" list: it becomes the one set,
    "Default", so nothing changes for anyone who never makes a second set."""
    if "sets" not in data:
        if "profiles" not in data:
            data["profiles"] = [{"name": "Default", "match": "",
                                 "bindings": data.pop("bindings", {}), "layer_bindings": {}}]
        data["sets"] = [{"name": "Default", "profiles": data["profiles"]}]
    data.pop("profiles", None)  # the sets are the truth; "profiles" is rebuilt below
    data["sets"] = _clean_sets(data)
    active = profile_sets.pick(data["sets"], profile_sets.active_name())
    data["active_set"] = active["name"]
    data["profiles"] = active["profiles"]  # the same list, so edits reach the set
    return data


def load():
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return _migrate(json.loads(json.dumps(DEFAULT_CONFIG)))
    _migrate(data)  # before defaults, or the default profile would hide old bindings
    for key, value in DEFAULT_CONFIG.items():
        data.setdefault(key, json.loads(json.dumps(value)))
    return data


def _for_disk(data):
    """The config as saved: the working "profiles" go back into their set."""
    out = {k: v for k, v in data.items() if k not in ("profiles", "active_set")}
    sets = [dict(item) for item in data.get("sets") or []]
    if not sets:
        sets = [{"name": "Default", "profiles": data.get("profiles", [])}]
    mine = profile_sets.pick(sets, data.get("active_set"))
    mine["profiles"] = data.get("profiles", mine["profiles"])
    out["sets"] = sets
    return out


def save(data):
    data = _for_disk(data)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    # 0600: the file may contain the OBS websocket password.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def mtime():
    """(config file time, active-set file time): differs after either changes, and the service reloads then."""
    try:
        config_time = CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        config_time = 0.0
    return (config_time, profile_sets.mtime())


def profile_matches(profile, window_class):
    classes = {c.strip().lower() for c in profile.get("match", "").split(",") if c.strip()}
    return bool(window_class) and window_class.lower() in classes


HUD_TRIGGERS = ("combo", "hold")
HUD_DEFAULT_KEY = "Enter"   # Layer + Enter: the biggest key, easy to find without looking


def hud_settings(cfg):
    """The key map overlay settings, always complete:
    {"enabled": bool, "opacity": 30..100, "trigger": "combo" | "hold", "key": a numpad key}.

    trigger "combo" (the default since issue #12): Layer + `key` opens the overlay and pressing it again, or
    letting go of the layer key, closes it, so Layer + 1 and friends no longer flash it up every time.
    "hold" is the old way: it shows for as long as the layer key is held. `key` only matters for "combo"."""
    hud = cfg.get("hud") if isinstance(cfg.get("hud"), dict) else {}
    try:
        opacity = max(30, min(100, int(hud.get("opacity", 90))))
    except (TypeError, ValueError):
        opacity = 90
    trigger = hud.get("trigger") if hud.get("trigger") in HUD_TRIGGERS else "combo"
    key = hud.get("key") if isinstance(hud.get("key"), str) and hud.get("key") else HUD_DEFAULT_KEY
    return {"enabled": bool(hud.get("enabled", True)), "opacity": opacity, "trigger": trigger, "key": key}


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
