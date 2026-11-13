"""Action icon packs: a style for the icon of every action.

A pack is a zip (or folder) with one picture per action, named after it (`volume_up.png`, `mic_mute.png`, `obs_start_recording.png`...;
the names are the action ids in numpadctl/actions.py) and an optional `pack.json` with the pack's `name`, `author` and `license`.
It is read as strictly as a sticker pack (sticker_packs.py: only those names, size limits, nothing from the zip reaches the file
system), then each picture is shrunk to at most SIDE pixels and kept in the `icon-packs/<slug>/` folder of the settings directory.

Settings -> Appearance -> "Icon pack" picks the one in use (config look["icon_pack"], "" = the built-in icons). Where the pack has a
picture for a key's action, that picture is drawn instead of the built-in icon, in the window and on the key map overlay; for an action
the pack doesn't cover, the built-in icon stays. A sticker you chose for a key always wins over both.

This module knows names and files only (no Qt), so the service and the overlay can use it.
"""

import json
import re
import shutil
from pathlib import PurePosixPath

from . import sticker_packs
from .platform import paths

PackError = sticker_packs.PackError
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")      # a pack's folder name: what the settings file and the folder both use
ACTION_ID = re.compile(r"[a-z0-9_]{1,60}")
MAX_ENTRIES = 160                                    # entries looked at in a pack (there are about 80 actions)
MAX_PACKS = 20                                       # installed at once
SIDE = 128                                           # a stored picture is at most this many pixels wide and high
INFO = "pack.json"


def folder():
    return paths.config_dir() / "icon-packs"


def valid_slug(value):
    return isinstance(value, str) and SLUG.fullmatch(value) is not None


def path_for(slug, action_id):
    """The picture of `action_id` in the installed pack `slug`, or None (no such pack, no picture, or a name we didn't make)."""
    if not valid_slug(slug) or not isinstance(action_id, str) or not ACTION_ID.fullmatch(action_id):
        return None
    path = folder() / slug / f"{action_id}.png"
    return path if path.is_file() else None


def read_pack(path, valid_ids):
    """The sticker_packs.Pack in the zip or folder at `path`: pictures named after an id in `valid_ids`. Raises PackError."""
    ids = set(valid_ids)

    def key_for(filename):
        entry = PurePosixPath(filename)
        stem, extension = entry.stem.lower().strip(), entry.suffix.lower()
        return (stem, extension) if stem in ids and extension in sticker_packs.EXTENSIONS else None

    return sticker_packs.read_pack(path, key_for=key_for, max_entries=MAX_ENTRIES, what="an action",
                                   empty="it has no pictures named after actions (volume_up.png, mic_mute.png ...)")


def _info(directory):
    try:
        data = json.loads((directory / INFO).read_text(encoding="utf-8")[:sticker_packs.MAX_INFO_BYTES])
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    return {k: sticker_packs._text(data.get(k)) for k in ("name", "author", "license")}


def installed():
    """The installed packs, by name: [{"slug", "name", "author", "license", "count"}]."""
    found = []
    try:
        entries = sorted(p for p in folder().iterdir() if p.is_dir() and not p.is_symlink() and valid_slug(p.name))
    except OSError:
        return []
    for directory in entries[:MAX_PACKS * 2]:
        info = _info(directory)
        count = sum(1 for p in directory.glob("*.png") if ACTION_ID.fullmatch(p.stem))
        found.append({"slug": directory.name, **info, "name": info["name"] or directory.name, "count": count})
    return sorted(found, key=lambda pack: pack["name"].lower())


def slug_for(name):
    """The folder for a pack called `name`: the installed pack with that name (installing again replaces it), else a new,
    unused slug made from the name. Raises PackError when MAX_PACKS are installed already."""
    have = installed()
    for pack in have:
        if pack["name"].lower() == name.strip().lower():
            return pack["slug"]
    if len(have) >= MAX_PACKS:
        raise PackError(f"{MAX_PACKS} icon packs are installed already: remove one first")
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-") or "pack"
    slug, n, taken = base, 2, {pack["slug"] for pack in have}
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def save(slug, info, pictures):
    """Write the pack `slug`: `pictures` is {action id: PNG bytes}. Replaces an installed pack with the same slug, all at once."""
    if not valid_slug(slug):
        raise PackError("that isn't a usable pack name")
    root = folder()
    temp, final = root / f".new-{slug}", root / slug
    try:
        root.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(temp, ignore_errors=True)
        temp.mkdir()
        for action_id, data in pictures.items():
            if not ACTION_ID.fullmatch(action_id):
                continue
            (temp / f"{action_id}.png").write_bytes(data)
        clean = {k: sticker_packs._text(info.get(k)) for k in ("name", "author", "license")}
        (temp / INFO).write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.rmtree(final, ignore_errors=True)
        temp.rename(final)
    except OSError as e:
        shutil.rmtree(temp, ignore_errors=True)
        raise PackError(f"it couldn't be kept ({e.strerror or e})") from None


def remove(slug):
    """Delete the installed pack `slug` (never anything outside the icon-packs folder). True when there was one."""
    if not valid_slug(slug):
        return False
    target = folder() / slug
    if target.is_symlink() or not target.is_dir() or target.parent != folder():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()
