"""Sticker packs: a zip (or a folder) of pictures named after the keys, applied to a profile in one go.

A pack is plain: `7.png`, `8.png`, `plus.png`, `enter.png`... (the names are in KEY_FILE_NAMES), and an optional
`pack.json` with the pack's `name`, `author` and `license`. Any common picture type works (png, jpg, gif, webp, bmp,
svg); the settings window shrinks each one into a normal sticker (numpadctl_ui/sticker_image.py), so a pack is only a
shortcut for choosing 19 pictures by hand, and nothing in it can do more than a picture chosen by hand could.

A pack comes from outside, so it is read carefully: only the names above are looked at (folders inside a zip are
ignored and never extracted, so a name like `../x` goes nowhere), at most MAX_ENTRIES entries are looked at, and a
picture or the whole pack over its size limit is refused, whatever the zip claims about its own size.
"""

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import profile_io

# the file name (without its extension, in lower case) -> the key it is for
KEY_FILE_NAMES = {
    **{str(n): str(n) for n in range(10)}, "000": "000",
    "dot": ".", "period": ".", "plus": "+", "minus": "-", "star": "*", "slash": "/",
    "enter": "Enter", "numlock": "NumLock", "backspace": "Backspace",
}
ALL_KEYS = sorted(set(KEY_FILE_NAMES.values()), key=lambda k: (not k.isdigit(), k))   # the 19 keys a full pack covers
EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
MAX_ENTRIES = 64                 # entries looked at in a zip, or files in a folder
MAX_PICTURE_BYTES = 5_000_000    # one picture (a sticker ends up at most 128 pixels wide)
MAX_TOTAL_BYTES = 40_000_000     # all the pictures together
MAX_INFO_BYTES = 10_000          # pack.json
MAX_TEXT = 60
INFO_NAME = "pack.json"


class PackError(Exception):
    """The pack can't be used; the message says why, in plain words."""


@dataclass
class Pack:
    name: str = ""
    author: str = ""
    license: str = ""
    files: dict = field(default_factory=dict)      # key -> (extension, picture bytes)
    ignored: list = field(default_factory=list)    # what was left out, in words


def _text(value):
    return profile_io._CONTROL.sub(" ", value).strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _key_for(filename):
    """(key, extension) for a file name like `Plus.PNG`, or None when it isn't a picture for a key."""
    path = PurePosixPath(filename)
    extension = path.suffix.lower()
    key = KEY_FILE_NAMES.get(path.stem.lower().strip())
    return (key, extension) if key and extension in EXTENSIONS else None


def _read_info(raw, pack):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        pack.ignored.append("pack.json isn't valid, so the pack has no name")
        return
    if isinstance(data, dict):
        pack.name, pack.author, pack.license = _text(data.get("name")), _text(data.get("author")), _text(data.get("license"))


def _collect(entries, pack):
    """`entries` yields (file name, size claimed, opener). Fills pack.files, enforcing the limits on what is really read."""
    total = 0
    for count, (filename, claimed, opener) in enumerate(entries):
        if count >= MAX_ENTRIES:
            pack.ignored.append(f"only the first {MAX_ENTRIES} files were looked at")
            break
        base = PurePosixPath(filename).name
        if not base or base.startswith(".") or "__MACOSX" in PurePosixPath(filename).parts:
            continue
        if base.lower() == INFO_NAME:
            raw = opener(MAX_INFO_BYTES + 1)
            if len(raw) > MAX_INFO_BYTES:
                pack.ignored.append("pack.json is too big, so the pack has no name")
            else:
                _read_info(raw, pack)
            continue
        found = _key_for(base)
        if found is None:
            pack.ignored.append(f"{base[:40]}: not a name for a key")
            continue
        key, extension = found
        if key in pack.files:
            pack.ignored.append(f"{base[:40]}: another picture is already used for key {key}")
            continue
        if claimed > MAX_PICTURE_BYTES:
            raise PackError(f"{base[:40]} is bigger than {MAX_PICTURE_BYTES // 1_000_000} MB")
        data = opener(MAX_PICTURE_BYTES + 1)          # what is really there, whatever the zip says about its size
        if len(data) > MAX_PICTURE_BYTES:
            raise PackError(f"{base[:40]} is bigger than {MAX_PICTURE_BYTES // 1_000_000} MB")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise PackError(f"the pictures together are bigger than {MAX_TOTAL_BYTES // 1_000_000} MB")
        pack.files[key] = (extension, data)


def read_pack(path):
    """The Pack in the zip or folder at `path`. Raises PackError (never anything else) when it can't be used."""
    path = Path(path)
    pack = Pack()
    try:
        if path.is_dir():
            files = sorted(p for p in path.iterdir() if p.is_file())

            def entries():
                for p in files:
                    def opener(limit, p=p):
                        with open(p, "rb") as f:
                            return f.read(limit)
                    yield p.name, p.stat().st_size, opener
            _collect(entries(), pack)
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                infos = sorted((i for i in archive.infolist() if not i.is_dir()), key=lambda i: i.filename)

                def entries():
                    for info in infos:
                        def opener(limit, info=info):
                            with archive.open(info) as f:
                                return f.read(limit)
                        yield info.filename, info.file_size, opener
                _collect(entries(), pack)
        else:
            raise PackError("that isn't a zip file or a folder")
    except PackError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as e:   # unreadable, encrypted, broken
        raise PackError(f"it couldn't be read ({getattr(e, 'strerror', None) or e})") from None
    if not pack.files:
        raise PackError("it has no pictures named after keys (7.png, plus.png, enter.png ...)")
    return pack
