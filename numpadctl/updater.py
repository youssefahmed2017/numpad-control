"""Automatic updates: the service installs new releases by itself.

Once a day the service asks GitHub for the latest release (a tag like v0.2.0, made with
release.yml). If it's newer than this copy (numpadctl.__version__), it's installed the
way this copy was installed:

  - a git copy (setup.sh, or setup.ps1 with git): fetch the tag and fast-forward
    to it; a copy with local changes isn't touched (you're told instead);
  - a zip copy (setup.ps1 without git): download the release's zip and swap the
    folders in place, keeping .venv;

then the Python packages are updated and the service restarts itself. Releases only,
never unfinished work on main. Only GitHub is contacted, over HTTPS, and only releases signed
with the author's key (release_key.py) are installed: the signature names the exact commit
(git copies) or the exact source.zip hash (zip copies), and is checked before anything changes.

Settings: "updates": "auto" (the default), "notify" (only say there's an update) or "off".
    python -m numpadctl update    checks and installs right away
"""

import base64
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import __version__, release_key
from .platform import IS_WINDOWS, paths

log = logging.getLogger("numpadctl")

REPO = "youssefahmed2017/numpad-pilot"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
# What tools/sign-release attaches to every release: the source (built from the signed commit) and
# the signature over that commit and that file's hash. Nothing else is ever installed.
ZIP_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/source.zip"
SIGNATURE_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/release.sig"
MAX_SIGNATURE_BYTES = 8192
MAX_ZIP_BYTES = 200 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")  # matched whole and ASCII-only: it goes into a git ref and a download URL
CHECK_EVERY = 24 * 3600
KEEP = {".venv", ".git"}  # never replaced by a zip update
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


PACKAGED_MARKER = ".packaged"  # put there by a distro package (AUR): its package manager does the updating


def packaged(root=ROOT):
    return (root / PACKAGED_MARKER).exists()


class UpdateError(Exception):
    pass


def parse(version):
    """(0, 2, 0) from "v0.2.0" or "0.2.0"; None if it isn't a plain version."""
    match = TAG.fullmatch(version if version.startswith("v") else f"v{version}")
    return tuple(int(n) for n in match.groups()) if match else None


def _state_path():
    return paths.state_dir() / "update.json"


def _state():
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_state(**changes):
    state = {**_state(), **changes}
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state))


def due(now=None):
    """Whether a day has passed since the last check (the service restarts often; GitHub limits asks)."""
    now = time.time() if now is None else now
    return now - _state().get("checked", 0) >= CHECK_EVERY


def latest_release():
    """The latest release's tag, or None (no releases yet, or GitHub can't be reached)."""
    request = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": f"numpad-control/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            tag = json.load(response).get("tag_name", "")
    except urllib.error.HTTPError as e:
        if e.code != 404:  # 404: no release published yet
            log.info("update check: GitHub answered %s", e.code)
        return None
    except (OSError, ValueError) as e:
        log.info("update check failed: %s", e)
        return None
    return tag if parse(tag) else None


def check():
    """The newer release's tag, or None. Remembers that it checked."""
    _save_state(checked=time.time())
    tag = latest_release()
    if tag and parse(tag) > parse(__version__):
        return tag
    return None


def _download(url, limit, timeout=120):
    """The bytes at url, refusing more than `limit`."""
    request = urllib.request.Request(url, headers={"User-Agent": f"numpad-control/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError(f"{url} is bigger than expected, so it was refused")
    return data


def verify_signature(tag, blob, public_key=None):
    """The signed statement {"tag", "commit", "zip_sha256"} if `blob` (release.sig) was signed by the
    release key for this tag; otherwise raises UpdateError. Nothing is trusted before this passes."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise UpdateError("the 'cryptography' package is missing, so the release's signature can't be "
                          "checked (run the installer once to add it)") from None
    key = release_key.PUBLIC_KEY if public_key is None else public_key
    unsigned = UpdateError(f"{tag} isn't signed with the NumpadPilot release key, so it wasn't installed")
    try:
        document = json.loads(blob)
        statement = document["statement"]
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True)).verify(
            base64.b64decode(document["signature"], validate=True), statement.encode())
        signed = json.loads(statement)
    except (ValueError, KeyError, TypeError, InvalidSignature):  # also an empty key: nothing is trusted yet
        raise unsigned from None
    if not isinstance(signed, dict) or signed.get("app") != "numpad-pilot" or signed.get("tag") != tag:
        raise UpdateError(f"the signature is for a different release than {tag}, so it wasn't installed")
    if not re.fullmatch(r"[0-9a-f]{40}", str(signed.get("commit"))) or \
            not re.fullmatch(r"[0-9a-f]{64}", str(signed.get("zip_sha256"))):
        raise unsigned
    return signed


def _git(*args, cwd=ROOT):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120,
                          creationflags=NO_WINDOW)
    if done.returncode != 0:
        raise UpdateError(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout


def _update_git(tag, commit, root=ROOT):
    """Move to `tag`, but only if it is the signed commit."""
    if shutil.which("git") is None:
        raise UpdateError("this is a git copy, but git isn't installed")
    if _git("status", "--porcelain", "--untracked-files=no", cwd=root).strip():
        raise UpdateError(f"{root} has local changes, so it wasn't updated (run the installer to update it)")
    _git("fetch", "--quiet", "origin", f"refs/tags/{tag}:refs/tags/{tag}", cwd=root)
    if _git("rev-parse", f"refs/tags/{tag}^{{commit}}", cwd=root).strip() != commit:
        raise UpdateError(f"the {tag} on GitHub isn't the commit that was signed, so it wasn't installed")
    try:
        _git("merge", "--ff-only", "--quiet", commit, cwd=root)
    except UpdateError as e:
        raise UpdateError(f"couldn't move to {tag} (local commits?): {e}") from None


def _update_zip(tag, sha256, root=ROOT):
    """Swap in the release's source.zip, but only if it is the signed file."""
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "release.zip"
        data = _download(ZIP_URL.format(tag=tag), MAX_ZIP_BYTES)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise UpdateError(f"the download for {tag} isn't the file that was signed, so it wasn't installed")
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():  # a zip entry must not point outside the folder
                if name.startswith("/") or ".." in Path(name).parts:
                    raise UpdateError(f"the download has an unsafe path: {name}")
            z.extractall(temp)
        unpacked = [p for p in Path(temp).iterdir() if p.is_dir()]
        if len(unpacked) != 1 or not (unpacked[0] / "numpadctl").is_dir():
            raise UpdateError("the download doesn't look like NumpadPilot")
        new = unpacked[0]
        for item in new.iterdir():
            if item.name in KEEP:
                continue
            target = root / item.name
            if item.is_dir():
                staged, old = root / f"{item.name}.new", root / f"{item.name}.old"
                for leftover in (staged, old):
                    shutil.rmtree(leftover, ignore_errors=True)
                shutil.copytree(item, staged)
                if target.exists():
                    target.rename(old)
                staged.rename(target)  # the folder is swapped in one step: never half old, half new
                shutil.rmtree(old, ignore_errors=True)
            else:
                shutil.copy2(item, target)


def _update_packages(root=ROOT):
    requirements = root / "requirements.txt"
    if not requirements.exists():
        return
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "-r", str(requirements)],
                          capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
    if done.returncode != 0:
        raise UpdateError(f"updating the Python packages failed: {(done.stderr or done.stdout).strip()[-500:]}")


def install(tag, root=ROOT):
    """Install release `tag` over this copy. Raises UpdateError with a reason the user can act on."""
    if not parse(tag):
        raise UpdateError(f"not a release tag: {tag}")
    if packaged(root):
        raise UpdateError("NumpadPilot was installed by your package manager: update it with that (for example yay -Syu or winget upgrade)")
    log.info("updating to %s", tag)
    try:
        blob = _download(SIGNATURE_URL.format(tag=tag), MAX_SIGNATURE_BYTES, timeout=30)
    except (OSError, ValueError) as e:  # a release made before signing, or GitHub unreachable
        raise UpdateError(f"{tag} has no signature to check ({e}), so it wasn't installed") from None
    signed = verify_signature(tag, blob)
    if (root / ".git").exists():
        _update_git(tag, signed["commit"], root)
    else:
        _update_zip(tag, signed["zip_sha256"], root)
    _update_packages(root)
    _save_state(installed=tag, installed_at=time.time())
    log.info("updated to %s", tag)


def main():
    """python -m numpadctl update: check now and install a newer release."""
    print(f"This copy: {__version__}")
    tag = check()
    if not tag:
        latest = latest_release()
        print(f"Up to date (latest release: {latest})." if latest else "No release published yet.")
        return 0
    print(f"Installing {tag}…")
    try:
        install(tag)
    except (UpdateError, OSError) as e:
        print(f"Couldn't update: {e}")
        return 1
    print(f"Updated to {tag}. Restart NumpadPilot to use it "
          "(Linux: systemctl --user restart numpad-control; Windows: Quit in the tray, then start it).")
    return 0
