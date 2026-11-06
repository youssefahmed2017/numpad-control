"""Stickers: a picture for a key, shown on the key in the settings window and on the key map overlay.

A sticker belongs to a key of one profile: profile["stickers"] is {key: file name}. A profile that has no sticker for
a key uses the Default profile's, like it does for actions. The pictures themselves are small PNGs in the
`stickers` folder of the settings directory, named after their content (so the same picture is stored once, and a name
tells nothing a program could use to reach another file). The settings window makes them (numpadctl_ui/sticker_image.py);
this module only knows the names and where they live, so the service can pass them to the overlay without Qt.

Stickers stay on this computer: exporting a profile leaves them out (a shared profile must not carry pictures).
"""

import re

from .platform import paths

# the only file names ever read: 16 hex digits and .png, never a path
NAME = re.compile(r"[0-9a-f]{16}\.png")
SIZE = 128            # a sticker is stored at most this many pixels wide and high
MAX_SOURCE_BYTES = 20_000_000   # the biggest picture file we agree to open


def folder():
    return paths.config_dir() / "stickers"


def path_for(name):
    """Full path of a sticker, or None when `name` isn't a name we made."""
    return folder() / name if isinstance(name, str) and NAME.fullmatch(name) else None


def clean(profile):
    """profile["stickers"] as {key: valid name}, repaired if hand-edited (the profile is changed in place).

    A profile with no stickers is left without the field, so old configs and profiles read back unchanged."""
    found = profile.get("stickers")
    if found is None:
        return {}
    good = {k: v for k, v in found.items() if isinstance(k, str) and path_for(v)} if isinstance(found, dict) else {}
    if good:
        profile["stickers"] = good
    else:
        profile.pop("stickers", None)
    return good


def lookup(profiles, key, window_class=None, index=None):
    """The sticker name for `key`, or "".

    `profiles` is cfg["profiles"]. With `index`, that profile (then Default); otherwise the profiles that apply to
    `window_class`, most specific first, then Default: the order actions use (config.resolve)."""
    from . import config
    if index is not None:
        order = [profiles[index]] + ([profiles[0]] if index else [])
    else:
        order = [p for p in profiles[1:] if config.profile_matches(p, window_class)] + [profiles[0]]
    for profile in order:
        name = (profile.get("stickers") or {}).get(key)
        if path_for(name):
            return name
    return ""


def used(cfg):
    """Every sticker name any profile of any set refers to."""
    names = set()
    sets = cfg.get("sets") or [{"profiles": cfg.get("profiles", [])}]
    for item in sets:
        for profile in item.get("profiles", []):
            names |= {v for v in (profile.get("stickers") or {}).values() if path_for(v)}
    return names | {v for p in cfg.get("profiles", []) for v in (p.get("stickers") or {}).values() if path_for(v)}


def prune(cfg):
    """Delete the sticker files nothing refers to any more (called when the settings are saved)."""
    keep = used(cfg)
    try:
        files = list(folder().iterdir())
    except OSError:
        return
    for file in files:
        if NAME.fullmatch(file.name) and file.name not in keep:
            try:
                file.unlink()
            except OSError:
                pass
