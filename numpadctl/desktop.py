"""Desktop-specific parts, for Hyprland, KDE Plasma and any X11 desktop (XFCE, Cinnamon, MATE, i3...).

current() looks at XDG_CURRENT_DESKTOP, which the service refreshes before each
key press (see actions.refresh_session_env), so logging out of one desktop and
into the other switches backends without restarting anything.
"""

import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from .platform import IS_WINDOWS

HYPRLAND, KDE, X11, WINDOWS, OTHER = "hyprland", "kde", "x11", "windows", "other"
NAMES = {HYPRLAND: "Hyprland", KDE: "KDE Plasma", X11: "an X11 desktop", WINDOWS: "Windows"}


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
    if os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return X11   # XFCE, Cinnamon, MATE, GNOME or any other desktop on Xorg: the standard X11 window calls
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


def _x11():
    """The X11 backend when this is an X11 session (everything but Hyprland and KDE), else None."""
    if current() != X11:
        return None
    from .platform import x11_desktop
    return x11_desktop


def _supported(what):
    _only(what, HYPRLAND, KDE)
    return current()


# ---------------------------------------------------------------- windows

def active_window_class():
    """Class of the focused window (e.g. "kitty", "firefox"), or "" if unknown."""
    if x11 := _x11():
        return x11.active_window_class()
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
    if x11 := _x11():
        return x11.open_windows()
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
    if x11 := _x11():
        return x11.focus_window(cls)
    if _supported("Focusing a window") == HYPRLAND:
        _hyprctl(f'hl.dsp.focus({{ window = "class:{cls}" }})')
    else:
        found = _kdotool("search", "--class", f"^{re.escape(cls)}$").split()
        if not found:
            raise DesktopError(f"no {cls} window is open")
        _kdotool("windowactivate", found[0])


def close_window():
    if x11 := _x11():
        return x11.close_window()
    if _supported("Closing a window") == HYPRLAND:
        _hyprctl("hl.dsp.window.close()")
    else:
        _kdotool("getactivewindow", "windowclose")


def toggle_fullscreen():
    if x11 := _x11():
        return x11.toggle_fullscreen()
    if _supported("Fullscreen") == HYPRLAND:
        _hyprctl('hl.dsp.window.fullscreen({ mode = "fullscreen" })')
    else:
        _kdotool("getactivewindow", "windowstate", "--toggle", "FULLSCREEN")


def toggle_floating():
    if x11 := _x11():
        return x11.toggle_floating()
    _only("Floating windows", HYPRLAND)  # KDE windows always float
    _hyprctl('hl.dsp.window.float({ action = "toggle" })')


def toggle_scratchpad():
    if x11 := _x11():
        return x11.toggle_scratchpad()
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
    if x11 := _x11():
        return x11.go_to_workspace(number)
    if _supported("Workspaces") == HYPRLAND:
        _hyprctl(f"hl.dsp.focus({{ workspace = {number} }})")
    else:
        _kde_check_desktop(number)
        _kdotool("set_desktop", str(number))


def move_window_to_workspace(number):
    if x11 := _x11():
        return x11.move_window_to_workspace(number)
    if _supported("Workspaces") == HYPRLAND:
        _hyprctl(f"hl.dsp.window.move({{ workspace = {number} }})")
    else:
        _kde_check_desktop(number)
        _kdotool("getactivewindow", "set_desktop_for_window", str(number))


def step_workspace(step):
    """step = +1 (next) or -1 (previous)."""
    if x11 := _x11():
        return x11.step_workspace(step)
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


def show_volume():
    """X11 desktops have no volume popup of their own (SwayOSD and Plasma have one): show the level as a
    notification that replaces the previous one, with a level bar if the notification daemon draws one."""
    if current() != X11 or not shutil.which("wpctl") or not shutil.which("notify-send"):
        return
    out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).stdout   # "Volume: 0.55" or "Volume: 0.55 [MUTED]"
    found = re.search(r"([0-9]+(?:\.[0-9]+)?)", out)
    if not found:
        return
    percent, muted = round(float(found.group(1)) * 100), "[MUTED]" in out
    icon = ("audio-volume-muted-symbolic" if muted or percent == 0 else "audio-volume-low-symbolic" if percent < 34
            else "audio-volume-medium-symbolic" if percent < 67 else "audio-volume-high-symbolic")
    _run(["notify-send", "-a", "NumpadControl", "-u", "low", "-t", "1500", "-i", icon,
          "-h", "string:x-canonical-private-synchronous:numpadcontrol-volume", "-h", f"int:value:{min(percent, 100)}",
          "Volume", f"{percent}%" + (" (muted)" if muted else "")])


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
        reply = call("Inhibit", GLib.Variant("(ssa{sv})", ("numpad-control", "Do not disturb (NumpadControl)", {})), "(u)")
        _dnd["cookie"] = reply.unpack()[0]
        return True
    if not _running("dunst") and "xfce" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() \
            and shutil.which("xfconf-query"):
        return _toggle_xfce_dnd()
    out = _run(["dunstctl", "set-paused", "toggle"])
    if out.returncode != 0:
        raise DesktopError("dunstctl failed - is dunst running?")
    return _run(["dunstctl", "is-paused"]).stdout.strip() == "true"


def _running(program):
    try:
        return subprocess.run(["pgrep", "-x", program], capture_output=True, timeout=2).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _toggle_xfce_dnd():
    """XFCE's notification daemon keeps do-not-disturb as a setting; returns True if it is now on."""
    query = ["xfconf-query", "-c", "xfce4-notifyd", "-p", "/do-not-disturb"]
    now = _run(query).stdout.strip() == "true"
    done = _run([*query, "-n", "-t", "bool", "-s", "false" if now else "true"])
    if done.returncode != 0:
        raise DesktopError("couldn't change XFCE's do-not-disturb setting")
    return not now


def screenshot(path: Path, region=False):
    """Save a screenshot to path. Returns False if the user cancelled the selection."""
    if current() == X11:
        return _x11_screenshot(path, region)
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


# X11 screenshot tools, the first one installed is used: (program, whole screen, a region you select)
X11_SCREENSHOT_TOOLS = (
    ("maim", lambda p: ["maim", p], lambda p: ["maim", "-s", p]),
    ("scrot", lambda p: ["scrot", p], lambda p: ["scrot", "-s", p]),
    ("xfce4-screenshooter", lambda p: ["xfce4-screenshooter", "-f", "-s", p],
     lambda p: ["xfce4-screenshooter", "-r", "-s", p]),
    ("gnome-screenshot", lambda p: ["gnome-screenshot", "-f", p], lambda p: ["gnome-screenshot", "-a", "-f", p]),
    ("spectacle", lambda p: ["spectacle", "--background", "--nonotify", "--fullscreen", "--output", p],
     lambda p: ["spectacle", "--background", "--nonotify", "--region", "--output", p]),
)


def _x11_screenshot(path, region):
    for program, whole, area in X11_SCREENSHOT_TOOLS:
        if shutil.which(program):
            out = _run((area if region else whole)(str(path)), timeout=120)
            return out.returncode == 0 and path.exists()
    raise DesktopError("no screenshot tool found: install maim, scrot or xfce4-screenshooter")


def lock_screen():
    if current() == HYPRLAND and shutil.which("hyprlock"):
        subprocess.Popen(["hyprlock"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif current() == X11 and shutil.which("xflock4"):   # XFCE's own: it picks the screensaver that is installed
        subprocess.Popen(["xflock4"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        _run(["loginctl", "lock-session"])  # KDE's (and most desktops') screen locker listens


# Never force-killed, whatever is focused: the desktop itself and NumpadControl.
PROTECTED = {"hyprland", "plasmashell", "kwin_wayland", "kwin_x11", "krunner", "sddm", "waybar", "hyprpaper",
             "xfwm4", "xfdesktop", "xfce4-panel", "xfce4-session", "gnome-shell", "mutter", "marco", "cinnamon",
             "mate-panel", "lxqt-panel", "openbox", "i3", "xorg",
             "dev.numpadctl.numpadcontrol", "explorer", "dwm", "winlogon", "csrss", "python", "pythonw"}


def hide_windows():
    """Get everything off the screen at once: an empty workspace (Hyprland), every window minimised (KDE).

    Returns what restore_windows() needs to bring it all back (JSON-friendly)."""
    if x11 := _x11():
        return x11.hide_windows()
    if _supported("Hiding the windows") == HYPRLAND:
        info = json.loads(_run(["hyprctl", "activeworkspace", "-j"], timeout=2).stdout or "{}")
        _hyprctl('hl.dsp.focus({ workspace = "empty" })')
        return {"workspace": info.get("id")}
    windows = _kdotool("search", "--class", ".").split()
    for window in windows:
        _kdotool("windowminimize", window)
    return {"windows": windows}


def restore_windows(token):
    """Undo hide_windows(): back to the workspace you were on, or every minimised window shown again."""
    if x11 := _x11():
        return x11.restore_windows(token)
    if _supported("Showing the windows again") == HYPRLAND:
        if token.get("workspace") is not None:
            _hyprctl(f"hl.dsp.focus({{ workspace = {int(token['workspace'])} }})")
    else:
        for window in token.get("windows", []):
            _kdotool("windowactivate", window)


def force_close_window():
    """Kill the focused window's program at once (SIGKILL) and return its name. Unsaved work in it is lost."""
    if x11 := _x11():
        return x11.force_close_window()
    if _supported("Force-quitting a window") == HYPRLAND:
        info = json.loads(_run(["hyprctl", "activewindow", "-j"], timeout=2).stdout or "{}")
        name, pid = info.get("class", ""), info.get("pid", 0)
    else:
        name, pid = _kdotool("getactivewindow", "getwindowclassname"), int(_kdotool("getactivewindow", "getwindowpid") or 0)
    if not pid or pid <= 1:
        raise DesktopError("no window is focused")
    if name.lower() in PROTECTED or pid in (os.getpid(), os.getppid()):
        raise DesktopError(f"{name or 'that window'} is protected, it is not force-quit")
    os.kill(pid, signal.SIGKILL)
    return name or str(pid)


def focus_app_window(app_id):
    """Bring this app's own (already shown) window to the front."""
    if x11 := _x11():
        return x11.focus_app_window(app_id)
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
                  "step_workspace", "show_osd", "toggle_dnd", "screenshot", "lock_screen", "focus_app_window",
                  "hide_windows", "restore_windows", "force_close_window"):
        globals()[_name] = getattr(_windows, _name)

