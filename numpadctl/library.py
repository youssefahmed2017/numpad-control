"""The profile library: ready-made profiles to browse and import (github.com/youssefahmed2017/numpad-controllib).

The library has an index.json listing every profile, and the profile files themselves (the same format as
Export profile…). This module fetches and checks them; the settings window shows them (Profile ⋯ → Browse
library…), and a chosen profile is imported exactly like a file someone sent you: profile_io.parse checks it
and the import dialog shows what it will do. Nothing in the index (official or not, its list of ⚠ actions)
is trusted to skip that.

Nothing is fetched until the library window is opened. NUMPADCTL_LIBRARY points it elsewhere: another
https:// address, or a folder with a copy of the library (for trying profiles before they are published).
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, profile_io
from .platform import IS_WINDOWS
from .updater import parse as parse_version

DEFAULT_SOURCE = "https://raw.githubusercontent.com/youssefahmed2017/numpad-controllib/main/"
INDEX_FORMAT = "numpadcontrol-library-index"
INDEX_VERSION = 1
MAX_INDEX_BYTES = 2_000_000
MAX_ENTRIES = 5000
TIMEOUT = 15
# where a profile may be: nothing else is ever fetched, whatever the index says
PATH = re.compile(r"profiles/(official|community/[A-Za-z0-9-]{1,39})/[a-z0-9]+(?:-[a-z0-9]+)*\.json")
SHA256 = re.compile(r"[0-9a-f]{64}")
PLATFORMS = {"windows": "Windows", "linux": "Linux", "hyprland": "Hyprland"}


class LibraryError(Exception):
    """The library can't be used right now; the message says why, in plain words."""


@dataclass
class Entry:
    """One profile in the index. Shown in the list; only `path` is used to fetch it."""
    path: str
    name: str
    tier: str                 # "official" or "community"
    author: str = ""
    description: str = ""
    match: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    platforms: list = field(default_factory=list)
    requires: list = field(default_factory=list)
    min_app_version: str = ""
    keys: int = 0
    risky_actions: list = field(default_factory=list)
    sha256: str = ""          # checksum of the profile file; empty when the index has none (a local draft)

    @property
    def needs_newer_app(self):
        """True when the profile is for a newer NumpadControl than this one."""
        need, have = parse_version(self.min_app_version or "0.0.0"), parse_version(__version__)
        return bool(need and have and need > have)

    @property
    def fits_this_computer(self):
        return not self.platforms or bool(set(self.platforms) & current_platforms())

    def matches(self, text):
        """Whether a search for `text` finds this profile (name, description, author, tags, apps)."""
        words = text.lower().split()
        hay = " ".join([self.name, self.description, self.author, *self.tags, *self.match]).lower()
        return all(w in hay for w in words)


def current_platforms():
    if IS_WINDOWS:
        return {"windows"}
    found = {"linux"}
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        found.add("hyprland")
    return found


def source():
    """Where the library is: an https:// address ending in /, or a local folder (a Path)."""
    custom = os.environ.get("NUMPADCTL_LIBRARY", "").strip()
    if not custom:
        return DEFAULT_SOURCE
    if custom.startswith("https://"):
        return custom if custom.endswith("/") else custom + "/"
    if "://" in custom:
        raise LibraryError("NUMPADCTL_LIBRARY must be an https:// address or a folder")
    return Path(custom).expanduser()


def _read(src, path, limit):
    """The bytes of `path` in the library at `src`, refusing more than `limit`."""
    if isinstance(src, Path):
        root = src.resolve()
        target = (root / path).resolve()
        if root not in target.parents:
            raise LibraryError(f"{path} is outside the library folder")
        try:
            with open(target, "rb") as f:
                data = f.read(limit + 1)
        except OSError as e:
            raise LibraryError(f"couldn't read {path} from {root}: {e.strerror or e}") from None
    else:
        url = urllib.parse.urljoin(src, path)
        request = urllib.request.Request(url, headers={"User-Agent": f"numpad-control/{__version__}"})
        try:
            with _opener.open(request, timeout=TIMEOUT) as response:
                data = response.read(limit + 1)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise LibraryError("the library isn't available there yet (not found)") from None
            raise LibraryError(f"the library answered with an error ({e.code})") from None
        except (OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            raise LibraryError(f"couldn't reach the library ({reason}). Are you online?") from None
    if len(data) > limit:
        raise LibraryError(f"{path} is bigger than expected, so it was refused")
    return data


def _clean(value, length):
    """A text field of the index with control and text-direction characters taken out, cut to `length`."""
    return profile_io._CONTROL.sub(" ", value).strip()[:length] if isinstance(value, str) else ""


def _strings(value, limit=50, length=200):
    if not isinstance(value, list):
        return []
    return [_clean(v, length) for v in value[:limit] if isinstance(v, str)]


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to https:// addresses (a library never needs to be fetched in the clear)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("redirected to a connection that isn't https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnly)


def parse_index(data):
    """[Entry] from the bytes of index.json; raises LibraryError if it can't be used.

    Entries that don't make sense (most importantly a path outside profiles/) are skipped."""
    try:
        index = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise LibraryError("the library's list of profiles is damaged (not valid JSON)") from None
    if not isinstance(index, dict) or index.get("format") != INDEX_FORMAT:
        raise LibraryError("that isn't a NumpadControl profile library")
    version = index.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise LibraryError("the library's list of profiles has no usable version")
    if version > INDEX_VERSION:
        raise LibraryError("the library needs a newer NumpadControl: update it, then try again")
    raw = index.get("profiles")
    if not isinstance(raw, list):
        raise LibraryError("the library's list of profiles is damaged")
    entries, seen = [], set()
    for item in raw[:MAX_ENTRIES]:
        if not isinstance(item, dict):
            continue
        path, name = item.get("path"), item.get("name")
        if not (isinstance(path, str) and PATH.fullmatch(path)) or path in seen:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        seen.add(path)
        tier = "official" if path.startswith("profiles/official/") else "community"  # from the path, not the claim
        keys = item.get("keys")
        mav = item.get("min_app_version")
        entries.append(Entry(
            path=path, name=profile_io._CONTROL.sub(" ", name).strip()[:profile_io.MAX_NAME], tier=tier,
            author=_clean(item.get("author"), 40), description=_clean(item.get("description"), 500),
            match=_strings(item.get("match")), tags=_strings(item.get("tags"), 8, 40),
            platforms=[p for p in _strings(item.get("platforms"), 5) if p in PLATFORMS],
            requires=_strings(item.get("requires"), 10, 80),
            min_app_version=mav if isinstance(mav, str) and parse_version(mav) else "",
            keys=keys if isinstance(keys, int) and not isinstance(keys, bool) and keys >= 0 else 0,
            risky_actions=_strings(item.get("risky_actions"), 100, 40),
            sha256=item["sha256"].lower() if isinstance(item.get("sha256"), str) and SHA256.fullmatch(item["sha256"].lower()) else ""))
    entries.sort(key=lambda e: (e.tier != "official", e.name.lower()))
    return entries


def fetch_index(src=None):
    """The profiles in the library, official ones first."""
    return parse_index(_read(source() if src is None else src, "index.json", MAX_INDEX_BYTES))


def fetch_profile(entry, src=None):
    """The text of `entry`'s profile file, to hand to the importer (profile_io.parse checks it)."""
    if not PATH.fullmatch(entry.path):
        raise LibraryError("that profile's address isn't one the library uses")
    data = _read(source() if src is None else src, entry.path, profile_io.MAX_BYTES)
    if entry.sha256 and hashlib.sha256(data).hexdigest() != entry.sha256:
        # most often the online copy is mid-update (the list and the file are cached separately)
        raise LibraryError("that profile doesn't match the library's list (it may be updating): "
                           "try again in a few minutes")
    return data.decode("utf-8", "replace")


def describe_source(src=None):
    """Where the library is, for people: "the online library" or the folder / address set in NUMPADCTL_LIBRARY."""
    try:
        src = source() if src is None else src
    except LibraryError as e:
        return str(e)
    if src == DEFAULT_SOURCE:
        return "the online library"
    return str(src)
