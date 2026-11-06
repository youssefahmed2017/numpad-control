"""Window and workspace actions on X11 desktops: XFCE, Cinnamon, MATE, LXQt, GNOME or KDE on Xorg, i3, openbox...

The same functions as desktop.py offers for Hyprland and KDE Plasma; desktop.py uses these when the session is X11
(see desktop.current()). They talk to the window manager the standard way (EWMH: the _NET_* properties and client
messages every X11 window manager has), through python-xlib, so no extra programs are needed.

A window's "class" is its WM_CLASS class name (e.g. "Firefox", "kitty"); profiles and "Focus a window" compare it
ignoring case. What a window manager doesn't support (checked in _NET_SUPPORTED) says so instead of doing nothing.
"""

import os
import signal
from contextlib import contextmanager

from ..desktop import DesktopError

SUBSTRUCTURE = 1 << 20 | 1 << 19            # SubstructureRedirectMask | SubstructureNotifyMask
FROM_PAGER = 2                              # "source indication": a pager / tool, which window managers obey


class _Session:
    """One connection to the X server, with the few EWMH calls the actions need."""

    def __init__(self):
        try:
            from Xlib import display
        except ImportError:
            raise DesktopError("python-xlib is not installed (pip install python-xlib)") from None
        try:
            self.display = display.Display()
        except Exception as e:  # noqa: BLE001  (Xlib raises several kinds; all mean "no X server here")
            raise DesktopError(f"can't reach the X server ({e})") from None
        self.root = self.display.screen().root
        self._atoms = {}

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = self.display.intern_atom(name)
        return self._atoms[name]

    def window(self, window_id):
        return self.display.create_resource_object("window", window_id)

    def prop(self, window, name):
        """The values of a window property as a list, or [] when it isn't set."""
        found = window.get_full_property(self.atom(name), 0)
        if found is None:
            return []
        value = found.value
        return list(value) if not isinstance(value, (bytes, str)) else [value]

    def supports(self, name):
        return self.atom(name) in self.prop(self.root, "_NET_SUPPORTED")

    def need(self, name, what):
        if not self.supports(name):
            raise DesktopError(f"{what} isn't supported by this window manager")

    def send(self, window, name, data):
        """A client message to the window manager (about `window`), the way pagers and taskbars do it."""
        from Xlib import protocol
        event = protocol.event.ClientMessage(window=window, client_type=self.atom(name),
                                             data=(32, (list(data) + [0] * 5)[:5]))
        self.root.send_event(event, event_mask=SUBSTRUCTURE)
        self.display.sync()

    # -- windows
    def active(self):
        found = self.prop(self.root, "_NET_ACTIVE_WINDOW")
        return self.window(found[0]) if found and found[0] else None

    def clients(self):
        return [self.window(w) for w in self.prop(self.root, "_NET_CLIENT_LIST")]

    def is_app_window(self, window):
        """False for the panel and the desktop itself (docks and desktop windows are not programs to pick)."""
        types = self.prop(window, "_NET_WM_WINDOW_TYPE")
        return not {self.atom("_NET_WM_WINDOW_TYPE_DOCK"), self.atom("_NET_WM_WINDOW_TYPE_DESKTOP")} & set(types)

    def wm_class(self, window):
        """(instance, class) of a window, or ("", "")."""
        try:
            return window.get_wm_class() or ("", "")
        except Exception:  # noqa: BLE001  (a window that closed meanwhile)
            return ("", "")

    def title(self, window):
        try:
            raw = self.prop(window, "_NET_WM_NAME")
            if raw and isinstance(raw[0], bytes):
                return raw[0].decode("utf-8", "replace")
            return window.get_wm_name() or ""
        except Exception:  # noqa: BLE001
            return ""

    def pid(self, window):
        found = self.prop(window, "_NET_WM_PID")
        return int(found[0]) if found else 0

    def close(self):
        try:
            self.display.close()
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def _x():
    """A session that is closed afterwards, and X errors reported as DesktopError."""
    session = _Session()
    try:
        yield session
    except DesktopError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DesktopError(f"the X server refused ({type(e).__name__}: {e})") from None
    finally:
        session.close()


def _need_active(x):
    window = x.active()
    if window is None:
        raise DesktopError("no window is focused")
    return window


def _protected(x, window):
    from ..desktop import PROTECTED
    instance, cls = x.wm_class(window)
    return (cls or instance).lower() in PROTECTED or instance.lower() in PROTECTED


# ---------------------------------------------------------------- windows

def active_window_class():
    """Class of the focused window (e.g. "kitty", "Firefox"), or "" if unknown."""
    try:
        with _x() as x:
            window = x.active()
            if window is None:
                return ""
            instance, cls = x.wm_class(window)
            return cls or instance
    except DesktopError:
        return ""


def open_windows():
    """[(class, title)] of open windows, one per class, for picking a profile's app."""
    result, seen = [], set()
    try:
        with _x() as x:
            for window in x.clients():
                if not x.is_app_window(window):
                    continue
                instance, cls = x.wm_class(window)
                cls = cls or instance
                if cls and cls not in seen:
                    seen.add(cls)
                    result.append((cls, x.title(window)))
    except DesktopError:
        pass
    return result


def _find(x, cls):
    wanted = cls.lower()
    for window in x.clients():
        instance, name = x.wm_class(window)
        if x.is_app_window(window) and wanted in (instance.lower(), name.lower()):
            return window
    return None


def focus_window(cls):
    """cls must already be validated (letters, digits, . _ - only)."""
    with _x() as x:
        x.need("_NET_ACTIVE_WINDOW", "Focusing a window")
        window = _find(x, cls)
        if window is None:
            raise DesktopError(f"no {cls} window is open")
        x.send(window, "_NET_ACTIVE_WINDOW", [FROM_PAGER, 0, 0])


def focus_app_window(app_id):
    """Bring this app's own (already shown) window to the front."""
    try:
        focus_window(app_id)
    except DesktopError:
        pass


def close_window():
    with _x() as x:
        x.need("_NET_CLOSE_WINDOW", "Closing a window")
        window = _need_active(x)
        if _protected(x, window):
            raise DesktopError("that is the desktop itself, it isn't closed")
        x.send(window, "_NET_CLOSE_WINDOW", [0, FROM_PAGER])


def toggle_fullscreen():
    with _x() as x:
        x.need("_NET_WM_STATE_FULLSCREEN", "Fullscreen")
        window = _need_active(x)
        if _protected(x, window):
            raise DesktopError("that is the desktop itself")
        x.send(window, "_NET_WM_STATE", [2, x.atom("_NET_WM_STATE_FULLSCREEN"), 0, FROM_PAGER])  # 2 = toggle


def toggle_floating():
    raise DesktopError("Floating windows only work on Hyprland (windows on this desktop already float)")


def toggle_scratchpad():
    raise DesktopError("The scratchpad only works on Hyprland")


# ---------------------------------------------------------------- workspaces

def _desktops(x):
    found = x.prop(x.root, "_NET_NUMBER_OF_DESKTOPS")
    if not found:
        raise DesktopError("this window manager has no workspaces")
    return int(found[0])


def _current(x):
    found = x.prop(x.root, "_NET_CURRENT_DESKTOP")
    return int(found[0]) if found else 0


def _check(x, number):
    total = _desktops(x)
    if number > total:
        raise DesktopError(f"you have {total} workspaces; add more in your desktop's settings")


def go_to_workspace(number):
    with _x() as x:
        x.need("_NET_CURRENT_DESKTOP", "Switching workspace")
        _check(x, number)
        x.send(x.root, "_NET_CURRENT_DESKTOP", [number - 1, 0])


def move_window_to_workspace(number):
    with _x() as x:
        x.need("_NET_WM_DESKTOP", "Moving a window to a workspace")
        _check(x, number)
        window = _need_active(x)
        if _protected(x, window):
            raise DesktopError("that is the desktop itself")
        x.send(window, "_NET_WM_DESKTOP", [number - 1, FROM_PAGER])


def step_workspace(step):
    """step = +1 (next) or -1 (previous); wraps around."""
    with _x() as x:
        x.need("_NET_CURRENT_DESKTOP", "Switching workspace")
        total = _desktops(x)
        x.send(x.root, "_NET_CURRENT_DESKTOP", [(_current(x) + step) % total, 0])


# ---------------------------------------------------------------- hiding windows, force quit

def hide_windows():
    """Show the desktop (every window out of the way). Returns what restore_windows() needs."""
    with _x() as x:
        x.need("_NET_SHOWING_DESKTOP", "Hiding the windows")
        was = bool(x.prop(x.root, "_NET_SHOWING_DESKTOP") and x.prop(x.root, "_NET_SHOWING_DESKTOP")[0])
        x.send(x.root, "_NET_SHOWING_DESKTOP", [1])
        return {"was_showing": was}


def restore_windows(token):
    """Undo hide_windows(): the windows come back (unless the desktop was showing already)."""
    if token.get("was_showing"):
        return
    with _x() as x:
        x.need("_NET_SHOWING_DESKTOP", "Showing the windows again")
        x.send(x.root, "_NET_SHOWING_DESKTOP", [0])


def force_close_window():
    """Kill the focused window's program at once (SIGKILL) and return its name. Unsaved work in it is lost."""
    with _x() as x:
        window = _need_active(x)
        instance, cls = x.wm_class(window)
        name, pid = cls or instance, x.pid(window)
        if not pid or pid <= 1:
            raise DesktopError("no window is focused" if not name else f"{name} doesn't say which program it is")
        if _protected(x, window) or pid in (os.getpid(), os.getppid()):
            raise DesktopError(f"{name or 'that window'} is protected, it is not force-quit")
    os.kill(pid, signal.SIGKILL)
    return name or str(pid)
