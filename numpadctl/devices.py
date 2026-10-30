"""Finding the keyboards that can be added as extra devices (Linux).

The list comes from /sys, which anyone may read, so a keyboard shows up even before the user may
read its /dev/input files. For those the app can install a udev rule that gives the logged-in user
access to just that one device (like the rule for the numpad), through pkexec.
"""

import re
import shutil
import subprocess
from pathlib import Path

SYS_INPUT = Path("/sys/class/input")
DEV_INPUT = Path("/dev/input")
RULES_DIR = Path("/etc/udev/rules.d")
KEY_A = 30  # a device with this key is a keyboard (mice and media-key pads don't have it)


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _has_key(bitmap, code):
    """Is `code` set in /sys's capabilities/key (hex words, the highest first)?"""
    try:
        bits = int("".join(word.zfill(16) for word in bitmap.split()) or "0", 16)
    except ValueError:
        return False
    return bool(bits >> code & 1)


def keyboards(skip=()):
    """[{"vendor", "product", "name", "nodes": [Path], "readable": bool}] of the keyboards plugged in.

    `skip` is a set of (vendor, product) to leave out (the numpad, devices already added)."""
    found = {}
    for event in sorted(SYS_INPUT.glob("event*")):
        device = event / "device"
        if "/virtual/" in str(device.resolve()):  # ydotool and friends: not a keyboard you can plug in
            continue
        vendor, product = _read(device / "id/vendor"), _read(device / "id/product")
        if not vendor or not product:
            continue
        ids = (vendor.zfill(4), product.zfill(4))
        if ids in skip:
            continue
        item = found.setdefault(ids, {"vendor": ids[0], "product": ids[1], "names": [], "nodes": [], "keyboard": False})
        item["names"].append(_read(device / "name"))
        item["nodes"].append(DEV_INPUT / event.name)
        item["keyboard"] = item["keyboard"] or _has_key(_read(device / "capabilities/key"), KEY_A)
    result = []
    for item in found.values():
        if item["keyboard"]:
            item["name"] = min(item["names"], key=len)
            item["readable"] = all(_can_read(node) for node in item["nodes"])
            result.append({k: item[k] for k in ("vendor", "product", "name", "nodes", "readable")})
    return result


def _can_read(path):
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


def make_id(name, taken):
    """A short id for the config ("hp", "hp2"…): the first word of the name, lower case, letters and digits."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    base = words[0] if words else "kbd"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}{n}", n + 1
    return candidate


def _check_ids(vendor, product):
    if not (re.fullmatch(r"[0-9a-f]{4}", vendor) and re.fullmatch(r"[0-9a-f]{4}", product)):
        raise ValueError("not a USB id")


def rule_path(vendor, product):
    return RULES_DIR / f"70-numpad-control-{vendor}-{product}.rules"


def rule_line(vendor, product):
    return (f'SUBSYSTEM=="input", KERNEL=="event*", ATTRS{{idVendor}}=="{vendor}", '
            f'ATTRS{{idProduct}}=="{product}", TAG+="uaccess"')


def _reload(sudo=""):
    return f"{sudo}udevadm control --reload && {sudo}udevadm trigger --subsystem-match=input --action=change"


def manual_command(vendor, product):
    """What to paste into a terminal when pkexec isn't available."""
    _check_ids(vendor, product)
    return f"echo '{rule_line(vendor, product)}' | sudo tee {rule_path(vendor, product)} && {_reload('sudo ')}"


def install_rule(vendor, product):
    """Ask for the password (pkexec) and install the rule. Raises OSError with a sentence on failure."""
    _check_ids(vendor, product)
    if not shutil.which("pkexec"):
        raise OSError("pkexec isn't installed")
    script = f"echo '{rule_line(vendor, product)}' > {rule_path(vendor, product)} && {_reload()}"
    try:
        done = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise OSError("timed out waiting for the password")
    if done.returncode != 0:
        raise OSError((done.stderr or "").strip() or "the password was not accepted")
