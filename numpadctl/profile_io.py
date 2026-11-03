"""Share a profile as a file: export one, import one someone sent you.

A profile file is JSON:

    {"format": "numpadcontrol-profile", "version": 1, "app_version": "0.3.0",
     "profile": {"name": "Streaming", "match": "obs", "bindings": {...}, "layer_bindings": {...}}}

It holds only the profile (which keys do what, and which windows it applies to), never settings such as the
OBS password. Importing is careful on purpose: a profile's actions run on your computer as you, so the file is
treated as untrusted. It must be small, plain JSON of the expected shape; keys, slots and actions it
doesn't understand are dropped (and reported), and an action with bad settings is dropped too. The program
then shows what the profile will do before anything is added (see `summary`).
"""

import copy
import json
import re

from . import actions, config

FORMAT = "numpadcontrol-profile"
VERSION = 1
MAX_BYTES = 1_000_000        # a profile file is a few KB; this only stops silly ones
MAX_DEPTH = 8                # nesting of macro steps and if-branches
MAX_STRING = 20_000          # one value (a macro's Python code is the longest)
MAX_KEYS = 200               # keys with actions, per layer
MAX_NAME = 60
BINDING_FIELDS = ("action", "params", "rapid", "turbo")
RISKY_GROUPS = ("Advanced", "System", "Keyboard")   # run code, press keys for you, or power off the PC
RISKY_IDS = ("open_path", "launch_app", "open_url")           # open a file or program, or a web page
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ProfileFileError(Exception):
    """The file can't be used; the message says why, in plain words."""


# ---------------------------------------------------------------- export
def export_profile(profile, app_version=""):
    """The dict to save for `profile` (a deep copy: the profile itself is not touched)."""
    return {"format": FORMAT, "version": VERSION, "app_version": app_version,
            "profile": {"name": profile.get("name", ""), "match": profile.get("match", ""),
                        "bindings": copy.deepcopy(profile.get("bindings", {})),
                        "layer_bindings": copy.deepcopy(profile.get("layer_bindings", {}))}}


def dumps(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- import
def _plain_json(value, depth=0):
    """value if it is only strings, numbers, booleans, None, lists and string-keyed dicts (not too deep or long)."""
    if depth > MAX_DEPTH:
        raise ValueError("nested too deeply")
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise ValueError("a value is too long")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_plain_json(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) and len(k) <= 200 for k in value):
            raise ValueError("odd field names")
        return {k: _plain_json(v, depth + 1) for k, v in value.items()}
    raise ValueError("an unexpected kind of value")


def _clean_binding(binding):
    """The binding cut down to the fields we know, or a reason it was dropped (as a str)."""
    if not isinstance(binding, dict) or not isinstance(binding.get("action"), str):
        return "it is not an action"
    if binding["action"] not in actions.BY_ID:
        return f"unknown action “{binding['action'][:40]}” (made by a newer version?)"
    clean = {"action": binding["action"], "params": {}}
    try:
        params = _plain_json(binding.get("params", {}))
    except ValueError as e:
        return f"its settings are not usable ({e})"
    if not isinstance(params, dict):
        return "its settings are not usable"
    clean["params"] = params
    if isinstance(binding.get("rapid"), bool):
        clean["rapid"] = binding["rapid"]
    turbo = binding.get("turbo")
    if isinstance(turbo, int) and not isinstance(turbo, bool) and 1 <= turbo <= actions.TURBO_MAX:
        clean["turbo"] = turbo
    problems = actions.binding_problems(clean)
    if problems:
        return problems[0]
    return clean


def _clean_layer(layer, label, dropped):
    if not isinstance(layer, dict):
        raise ProfileFileError(f"“{label}” in the file isn't a list of keys")
    if len(layer) > MAX_KEYS:
        raise ProfileFileError(f"“{label}” has {len(layer)} keys; that is more than a numpad has")
    clean = {}
    for key, slots in layer.items():
        if not isinstance(key, str) or not key or len(key) > 64 or _CONTROL.search(key):
            dropped.append(f"a key with a strange name in {label}")
            continue
        if not isinstance(slots, dict):
            dropped.append(f"key {key} in {label}: not a set of actions")
            continue
        kept = {}
        for slot, binding in slots.items():
            if slot not in config.SLOTS:
                dropped.append(f"key {key} in {label}: unknown slot “{str(slot)[:20]}”")
                continue
            result = _clean_binding(binding)
            if isinstance(result, str):
                dropped.append(f"key {key} ({slot}) in {label}: {result}")
            else:
                kept[slot] = result
        if kept:
            clean[key] = kept
    return clean


def _clean_name(value, what):
    if not isinstance(value, str):
        raise ProfileFileError(f"the profile's {what} is missing")
    return _CONTROL.sub(" ", value).strip()


def parse(text):
    """(profile, dropped) from the text of a profile file; raises ProfileFileError if it can't be used.

    `profile` is {"name", "match", "bindings", "layer_bindings"} with every action checked; `dropped` lists, in
    words, what was left out and why (empty when everything was understood)."""
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise ProfileFileError("the file is too big to be a profile")
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise ProfileFileError("this isn't a NumpadControl profile file (it isn't valid JSON)") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ProfileFileError("this isn't a NumpadControl profile file")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ProfileFileError("the file has no usable version number")
    if version > VERSION:
        raise ProfileFileError("this profile was made by a newer NumpadControl: update it, then import again")
    raw = data.get("profile")
    if not isinstance(raw, dict):
        raise ProfileFileError("the file has no profile in it")
    name = _clean_name(raw.get("name"), "name")[:MAX_NAME].strip()
    if not name:
        raise ProfileFileError("the profile has no name")
    match = _clean_name(raw.get("match", ""), "match")[:200]
    dropped = []
    profile = {"name": name, "match": match,
               "bindings": _clean_layer(raw.get("bindings", {}), "its keys", dropped),
               "layer_bindings": _clean_layer(raw.get("layer_bindings", {}), "its layer keys", dropped)}
    return profile, dropped


def unique_name(name, existing):
    """`name`, or "name (2)", "name (3)", … if a profile already has it (case doesn't matter)."""
    taken = {n.lower() for n in existing}
    if name.lower() not in taken:
        return name
    n = 2
    while f"{name} ({n})".lower() in taken:
        n += 1
    return f"{name} ({n})"


def _walk(binding):
    """Every action in a binding, including the ones inside macros and if-branches."""
    yield binding
    params = binding.get("params", {})
    steps = list(params.get("steps", [])) + list(params.get("then", [])) + list(params.get("otherwise", []))
    for step in steps:
        if isinstance(step, dict):
            yield from _walk(step)


def summary(profile):
    """What a profile will do: [(action label, how many times, risky?)], the risky ones first."""
    counts = {}
    for layer in ("bindings", "layer_bindings"):
        for slots in profile.get(layer, {}).values():
            for binding in slots.values():
                for step in _walk(binding):
                    action = actions.BY_ID.get(step.get("action"))
                    if action and action.id != "none":
                        counts[action.id] = counts.get(action.id, 0) + 1
    rows = []
    for action_id, n in counts.items():
        action = actions.BY_ID[action_id]
        rows.append((action.label, n, action.group in RISKY_GROUPS or action.id in RISKY_IDS))
    return sorted(rows, key=lambda r: (not r[2], r[0]))


def key_count(profile):
    return sum(len(profile.get(layer, {})) for layer in ("bindings", "layer_bindings"))
