"""System actions on Linux: apps, browser, clipboard, typing, media, volume, power.

The action list (actions.py) calls these by name; a Windows version provides
the same functions. Errors are raised as SystemActionError with a message
meant for the user.
"""

import os
import shutil
import subprocess
import webbrowser


class SystemActionError(Exception):
    pass


def _run(*argv, timeout=10, **kwargs):
    if not shutil.which(argv[0]):
        raise SystemActionError(f"'{argv[0]}' is not installed")
    return subprocess.run(argv, check=False, timeout=timeout, **kwargs)


def spawn(*argv):
    """Start a program that keeps running on its own (an app, a browser).

    It gets its own systemd scope, so it isn't counted as part of the
    numpad service (its memory, CPU, and restarts)."""
    if not shutil.which(argv[0]):
        raise SystemActionError(f"'{argv[0]}' is not installed")
    if shutil.which("systemd-run"):
        argv = ("systemd-run", "--user", "--scope", "--quiet", "--collect", "--", *argv)
    subprocess.Popen(argv, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- desktop session

# Session variables a desktop app needs. The background service can start
# before the desktop shares them, and they change on every login, so they're
# fetched again before each action instead of trusted from startup.
SESSION_VARS = ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "XDG_SESSION_DESKTOP")


def refresh_session():
    """Copy the desktop session's display variables from systemd into os.environ.

    Returns True if a display is known afterwards."""
    try:
        out = subprocess.run(["systemctl", "--user", "show-environment"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    current = {}
    for line in out.splitlines():
        name, _, value = line.partition("=")
        if name in SESSION_VARS and value:
            current[name] = value
    if current:  # also forget the previous session's (e.g. Hyprland's ID after logging into KDE)
        for name in SESSION_VARS:
            if name in current:
                os.environ[name] = current[name]
            else:
                os.environ.pop(name, None)
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def notify(title, body=""):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Numpad Control", title, body],
                       check=False, timeout=5)


# ---------------------------------------------------------------- opening things

def open_url(url):
    # Not webbrowser.open(): it picks a browser once per process and keeps that
    # choice, so a service started before the desktop never finds a browser.
    if shutil.which("xdg-open"):
        spawn("xdg-open", url)
    else:
        webbrowser.open(url)


def open_default_browser():
    browser = _run("xdg-settings", "get", "default-web-browser", timeout=5,
                   capture_output=True, text=True).stdout.strip() \
        if shutil.which("xdg-settings") else ""
    if browser:
        launch_app(browser)
    else:
        webbrowser.open("about:blank")


def open_path(path):
    spawn("xdg-open", path)


def launch_app(app_id):
    """app_id: a .desktop file id, e.g. "kitty.desktop"."""
    import gi
    try:
        gi.require_version("GioUnix", "2.0")
        from gi.repository.GioUnix import DesktopAppInfo
    except (ValueError, ImportError):
        from gi.repository.Gio import DesktopAppInfo
    try:
        info = DesktopAppInfo.new(app_id)
    except TypeError:
        info = None
    if info is None:
        raise SystemActionError(f"app {app_id!r} is not installed")
    spawn("gio", "launch", info.get_filename())


# ---------------------------------------------------------------- clipboard

def copy_text(text):
    _run("wl-copy", "--", text)


def copy_image(path):
    with open(path, "rb") as image:
        _run("wl-copy", "--type", "image/png", stdin=image, timeout=5)


def clipboard_text():
    if not shutil.which("wl-paste"):
        return ""
    return subprocess.run(["wl-paste", "--no-newline", "--type", "text"],
                          capture_output=True, text=True, timeout=5).stdout


# ---------------------------------------------------------------- keyboard (ydotool)

def is_key(name):
    """name: an upper-case key name like "LEFTCTRL", "Q", "F5", "ENTER"."""
    from evdev import ecodes
    return ("KEY_" + name) in ecodes.ecodes


def _ydotool(*args, stdin=None):
    done = _run("ydotool", *args, input=stdin, capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise SystemActionError("ydotool failed - is its service running? "
                                "(systemctl --user enable --now ydotool)")


def press_keys(combos):
    """combos: [["LEFTCTRL", "C"], ["ENTER"]]: keys in a combo are held together."""
    from evdev import ecodes
    events = []
    for combo in combos:
        codes = [ecodes.ecodes["KEY_" + name] for name in combo]
        events += [f"{code}:1" for code in codes]            # hold them down in order
        events += [f"{code}:0" for code in reversed(codes)]  # let go in reverse
    _ydotool("key", *events)


def type_text(text):
    _ydotool("type", "--escape", "0", "--file", "-", stdin=text)


# ---------------------------------------------------------------- media and volume
# SwayOSD (when its server runs) changes things and shows its popup; otherwise
# playerctl / wpctl do it directly (KDE Plasma shows its own volume popup).

SINK, SOURCE = "@DEFAULT_AUDIO_SINK@", "@DEFAULT_AUDIO_SOURCE@"


def _swayosd(*args):
    if not shutil.which("swayosd-client"):
        return False
    return subprocess.run(["swayosd-client", *args], capture_output=True, timeout=5).returncode == 0


def media(command):
    """command: "play-pause", "stop", "next" or "previous"."""
    if not _swayosd("--playerctl", "prev" if command == "previous" else command):
        _run("playerctl", command)


def change_volume(step):
    """step: percent, e.g. +5 or -5 (never above 100%)."""
    osd = ["--max-volume", "100"] if step > 0 else []
    if not _swayosd(*osd, "--output-volume", f"{step:+d}"):
        limit = ["-l", "1.0"] if step > 0 else []
        _run("wpctl", "set-volume", *limit, SINK, f"{abs(step)}%{'+' if step > 0 else '-'}")


def set_volume(percent):
    _run("wpctl", "set-volume", SINK, f"{percent}%")
    # SwayOSD treats a bare number as "raise by", so the level is set with
    # wpctl and +0 only shows the popup.
    _swayosd("--output-volume", "+0")


def toggle_mute(microphone=False):
    if not _swayosd("--input-volume" if microphone else "--output-volume", "mute-toggle"):
        _run("wpctl", "set-mute", SOURCE if microphone else SINK, "toggle")


# ---------------------------------------------------------------- power

def power(what):
    """what: "suspend", "poweroff" or "reboot"."""
    _run("systemctl", what)
