"""Window and workspace actions on GNOME (Wayland), through GNOME's own keyboard shortcuts.

GNOME doesn't let programs ask which window is focused, list windows or switch workspaces (Shell.Introspect and
Shell.Eval are refused), and nothing here installs a shell extension. What a program can do is press the shortcuts
GNOME already has, so this reads YOUR shortcuts from gsettings (org.gnome.desktop.wm.keybindings, so custom ones work)
and presses them with ydotool, the same way "Press keys" does.

Works: next / previous workspace, go to / move a window to workspace N (when you have a shortcut set for it: GNOME
ships some, not all), close window, fullscreen, show desktop (when a shortcut is set). Not possible on GNOME without
an extension: the focused window's class (so no per-app profiles), focusing a window by name, force-quit.
"""

import ast
import re
import subprocess

from ..desktop import DesktopError

SCHEMA = "org.gnome.desktop.wm.keybindings"
MODIFIERS = {"<super>": "LEFTMETA", "<mod4>": "LEFTMETA", "<control>": "LEFTCTRL", "<primary>": "LEFTCTRL",
             "<alt>": "LEFTALT", "<mod1>": "LEFTALT", "<shift>": "LEFTSHIFT"}
KEYSYMS = {"page_up": "PAGEUP", "page_down": "PAGEDOWN", "home": "HOME", "end": "END", "left": "LEFT",
           "right": "RIGHT", "up": "UP", "down": "DOWN", "tab": "TAB", "space": "SPACE", "return": "ENTER",
           "escape": "ESC", "delete": "DELETE", "backspace": "BACKSPACE", "insert": "INSERT", "grave": "GRAVE",
           "minus": "MINUS", "equal": "EQUAL", "comma": "COMMA", "period": "DOT", "slash": "SLASH"}
FUNCTION_KEY = re.compile(r"f([1-9]|1[0-9]|2[0-4])", re.I)


def _gsettings(key):
    """The list of accelerators set for a window-manager shortcut, e.g. ["<Alt>F4"]. Empty if none is set."""
    try:
        out = subprocess.run(["gsettings", "get", SCHEMA, key], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        raise DesktopError("can't read GNOME's shortcuts (is gsettings installed?)") from None
    if out.returncode != 0:
        raise DesktopError(f"GNOME has no shortcut called {key!r}")
    try:
        value = ast.literal_eval(out.stdout.strip().removeprefix("@as ").strip())
    except (ValueError, SyntaxError):
        return []
    return [v for v in value if isinstance(v, str)]


def keys_for(accelerator):
    """["LEFTMETA", "PAGEUP"] for "<Super>Page_Up", or None when a part isn't a key this can press."""
    held = []
    rest = accelerator
    while rest.startswith("<"):
        end = rest.find(">")
        name = MODIFIERS.get(rest[:end + 1].lower()) if end > 0 else None
        if name is None:
            return None
        held.append(name)
        rest = rest[end + 1:]
    sym = rest.lower()
    if sym in KEYSYMS:
        key = KEYSYMS[sym]
    elif FUNCTION_KEY.fullmatch(rest):
        key = rest.upper()
    elif len(rest) == 1 and rest.isalnum():
        key = rest.upper()
    else:
        return None
    return held + [key]


def _press(shortcut, what, hint=""):
    """Press the first shortcut GNOME has for `shortcut` that can be pressed."""
    accelerators = _gsettings(shortcut)
    for accelerator in accelerators:
        keys = keys_for(accelerator)
        if keys:
            from . import linux_system
            try:
                linux_system.press_keys([keys])
            except linux_system.SystemActionError as e:
                raise DesktopError(str(e)) from None
            return
    if accelerators:
        raise DesktopError(f"{what}: none of GNOME's shortcuts for it ({', '.join(accelerators)}) can be pressed from here")
    raise DesktopError(f"{what}: GNOME has no shortcut set for it. Set one in Settings → Keyboard → Keyboard Shortcuts"
                       + (f" ({hint})" if hint else ""))


# ---------------------------------------------------------------- windows

def active_window_class():
    return ""   # GNOME doesn't tell programs which window is focused: per-app profiles can't switch here


def open_windows():
    return []


def focus_window(cls):
    raise DesktopError("GNOME doesn't let programs focus a window by name")


def focus_app_window(app_id):
    pass


def close_window():
    _press("close", "Closing a window", "Windows → Close window")


def toggle_fullscreen():
    _press("toggle-fullscreen", "Fullscreen", "Windows → Toggle fullscreen mode")


def toggle_floating():
    raise DesktopError("Floating windows only work on Hyprland")


def toggle_scratchpad():
    raise DesktopError("The scratchpad only works on Hyprland")


def force_close_window():
    raise DesktopError("GNOME doesn't tell programs which window is focused, so it can't be force-quit from here")


# ---------------------------------------------------------------- workspaces

def go_to_workspace(number):
    _press(f"switch-to-workspace-{number}", f"Going to workspace {number}",
           f"Navigation → Switch to workspace {number}; or use Next / Previous workspace")


def move_window_to_workspace(number):
    _press(f"move-to-workspace-{number}", f"Moving a window to workspace {number}",
           f"Navigation → Move window to workspace {number}")


def step_workspace(step):
    """step = +1 (next) or -1 (previous). GNOME's workspaces run left to right and don't wrap."""
    _press("switch-to-workspace-right" if step > 0 else "switch-to-workspace-left", "Switching workspace")


# ---------------------------------------------------------------- hiding windows

def hide_windows():
    """GNOME's Show desktop shortcut (it is not set by default). Pressing it again brings the windows back."""
    _press("show-desktop", "Hiding the windows", "Navigation → Hide all normal windows")
    return {"show_desktop": True}


def restore_windows(token):
    if token.get("show_desktop"):
        _press("show-desktop", "Showing the windows again")
