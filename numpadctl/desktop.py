"""Desktop-specific parts, for Hyprland and KDE Plasma.

current() looks at XDG_CURRENT_DESKTOP, which the service refreshes before each
key press (see actions.refresh_session_env), so logging out of one desktop and
into the other switches backends without restarting anything.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .platform import IS_WINDOWS

HYPRLAND, KDE, WINDOWS, OTHER = "hyprland", "kde", "windows", "other"
NAMES = {HYPRLAND: "Hyprland", KDE: "KDE Plasma", WINDOWS: "Windows"}


class DesktopError(Exception):
    pass


def current():
    if IS_WINDOWS:
        return WINDOWS
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "hyprland" in desktop:
        return HYPRLAND
    if "kde" in desktop:
        return KDE
    if not desktop and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return HYPRLAND
    return OTHER


def _run(argv, timeout=5):
    if not shutil.which(argv[0]):
        raise DesktopError(f"'{argv[0]}' is not installed")
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _only(what, *desktops):
    if current() not in desktops:
        names = " or ".join(NAMES[d] for d in desktops)
        raise DesktopError(f"{what} only works on {names}")


def _hyprctl(lua):
    out = _run(["hyprctl", "dispatch", lua])
    if out.stdout.strip() != "ok":
        raise DesktopError(out.stdout.strip() or out.stderr.strip() or "hyprctl failed")


def _kdotool(*args):
    out = _run(["kdotool", *args])
    if out.returncode != 0:
        raise DesktopError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "kdotool failed")
    return out.stdout.strip()


def _supported(what):
    _only(what, HYPRLAND, KDE)
    return current()


# ---------------------------------------------------------------- windows

def active_window_class():
    """Class of the focused window (e.g. "kitty", "firefox"), or "" if unknown."""
    try:
        if current() == HYPRLAND:
            out = _run(["hyprctl", "activewindow", "-j"], timeout=1).stdout
            return json.loads(out).get("class", "") if out.lstrip().startswith("{") else ""
        if current() == KDE:
            return _kdotool("getactivewindow", "getwindowclassname")
    except (DesktopError, subprocess.SubprocessError, ValueError):
        pass
    return ""


def open_windows():
    """[(class, title)] of open windows, one per class, for picking a profile's app."""
    result, seen = [], set()
    try:
        if current() == HYPRLAND:
            windows = [(c.get("class", ""), c.get("title", ""))
                       for c in json.loads(_run(["hyprctl", "clients", "-j"], timeout=2).stdout)]
        elif current() == KDE:
            windows = [(_kdotool("getwindowclassname", w), _kdotool("getwindowname", w))
                       for w in _kdotool("search", "--class", ".").split()]
        else:
            windows = []
    except (DesktopError, subprocess.SubprocessError, ValueError):
        windows = []
    for cls, title in windows:
        if cls and cls not in seen:
            seen.add(cls)
            result.append((cls, title))
    return result


def focus_window(cls):
    """cls must already be validated (letters, digits, . _ - only)."""
    if _supported("Focusing a window") == HYPRLAND:
        _hyprctl(f'hl.dsp.focus({{ window = "class:{cls}" }})')
    else:
        found = _kdotool("search", "--class", f"^{re.escape(cls)}$").split()
        if not found:
            raise DesktopError(f"no {cls} window is open")
        _kdotool("windowactivate", found[0])


def close_window():
    if _supported("Closing a window") == HYPRLAND:
        _hyprctl("hl.dsp.window.close()")
    else:
        _kdotool("getactivewindow", "windowclose")


def toggle_fullscreen():
    if _supported("Fullscreen") == HYPRLAND:
        _hyprctl('hl.dsp.window.fullscreen({ mode = "fullscreen" })')
    else:
        _kdotool("getactivewindow", "windowstate", "--toggle", "FULLSCREEN")


def toggle_floating():
    _only("Floating windows", HYPRLAND)  # KDE windows always float
    _hyprctl('hl.dsp.window.float({ action = "toggle" })')


def toggle_scratchpad():
    _only("The scratchpad", HYPRLAND)
    _hyprctl('hl.dsp.workspace.toggle_special("magic")')


# Workspaces on Hyprland are virtual desktops on KDE.

def _kde_desktops():
    return int(_kdotool("get_num_desktops"))


def _kde_check_desktop(number):
    total = _kde_desktops()
    if number > total:
        raise DesktopError(f"you have {total} virtual desktops; add more in "
                           "System Settings → Virtual Desktops")


def go_to_workspace(number):
    if _supported("Workspaces") == HYPRLAND:
        _hyprctl(f"hl.dsp.focus({{ workspace = {number} }})")
    else:
        _kde_check_desktop(number)
        _kdotool("set_desktop", str(number))


def move_window_to_workspace(number):
    if _supported("Workspaces") == HYPRLAND:
        _hyprctl(f"hl.dsp.window.move({{ workspace = {number} }})")
    else:
        _kde_check_desktop(number)
        _kdotool("getactivewindow", "set_desktop_for_window", str(number))


def step_workspace(step):
    """step = +1 (next) or -1 (previous)."""
    if _supported("Workspaces") == HYPRLAND:
        _hyprctl(f'hl.dsp.focus({{ workspace = "e{step:+d}" }})')
    else:
        total, now = _kde_desktops(), int(_kdotool("get_desktop"))
        _kdotool("set_desktop", str((now - 1 + step) % total + 1))  # wraps around


# ---------------------------------------------------------------- popups, DND, screenshots, lock

def show_osd(message, icon):
    """On-screen popup. Returns False if no popup service is available."""
    if current() == KDE and shutil.which("busctl"):
        done = subprocess.run(["busctl", "--user", "call", "org.kde.plasmashell", "/org/kde/osdService",
                               "org.kde.osdService", "showText", "ss", icon, message],
                              capture_output=True, timeout=5)
        if done.returncode == 0:
            return True
    if shutil.which("swayosd-client"):
        done = subprocess.run(["swayosd-client", "--custom-message", message, "--custom-icon", icon],
                              capture_output=True, timeout=5)
        if done.returncode == 0:
            return True
    return False


_dnd = {"bus": None, "cookie": None}


def toggle_dnd():
    """Returns True if do-not-disturb is now on."""
    if current() == KDE:
        # Plasma's DND for apps: an inhibition that lasts while this process's
        # D-Bus connection lives, so the connection is kept for the process.
        from gi.repository import Gio, GLib
        if _dnd["bus"] is None:
            _dnd["bus"] = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def call(method, args, reply):
            return _dnd["bus"].call_sync(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", method, args, GLib.VariantType(reply),
                Gio.DBusCallFlags.NONE, 5000, None)
        if _dnd["cookie"] is not None:
            call("UnInhibit", GLib.Variant("(u)", (_dnd["cookie"],)), "()")
            _dnd["cookie"] = None
            return False
        reply = call("Inhibit", GLib.Variant("(ssa{sv})", ("numpad-control", "Do not disturb (Numpad Control)", {})), "(u)")
        _dnd["cookie"] = reply.unpack()[0]
        return True
    out = _run(["dunstctl", "set-paused", "toggle"])
    if out.returncode != 0:
        raise DesktopError("dunstctl failed - is dunst running?")
    return _run(["dunstctl", "is-paused"]).stdout.strip() == "true"


def screenshot(path: Path, region=False):
    """Save a screenshot to path. Returns False if the user cancelled the selection."""
    if current() == KDE or (not shutil.which("grim") and shutil.which("spectacle")):
        out = _run(["spectacle", "--background", "--nonotify", "--region" if region else "--fullscreen",
                    "--output", str(path)], timeout=120)
        return out.returncode == 0 and path.exists()
    if region:
        pick = _run(["slurp"], timeout=120)
        if pick.returncode != 0:
            return False
        _run(["grim", "-g", pick.stdout.strip(), str(path)])
    else:
        _run(["grim", str(path)])
    return path.exists()


def lock_screen():
    if current() == HYPRLAND and shutil.which("hyprlock"):
        subprocess.Popen(["hyprlock"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        _run(["loginctl", "lock-session"])  # KDE's (and most desktops') screen locker listens


def focus_app_window(app_id):
    """Bring this app's own (already shown) window to the front."""
    try:
        if current() == HYPRLAND:
            _hyprctl(f'hl.dsp.focus({{ window = "class:{app_id}" }})')
        elif current() == KDE:
            found = _kdotool("search", "--class", f"^{re.escape(app_id)}$").split()
            if found:
                _kdotool("windowactivate", found[0])
    except (DesktopError, subprocess.SubprocessError):
        pass


# On Windows the same functions come from platform/windows_desktop.py.
if IS_WINDOWS:
    from .platform import windows_desktop as _windows
    for _name in ("active_window_class", "open_windows", "focus_window", "close_window", "toggle_fullscreen",
                  "toggle_floating", "toggle_scratchpad", "go_to_workspace", "move_window_to_workspace",
                  "step_workspace", "show_osd", "toggle_dnd", "screenshot", "lock_screen", "focus_app_window"):
        globals()[_name] = getattr(_windows, _name)

