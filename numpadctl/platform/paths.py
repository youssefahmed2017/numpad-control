"""Where settings, state and runtime files live.

Linux: XDG folders (~/.config, ~/.local/state, $XDG_RUNTIME_DIR).
Windows: %APPDATA% for settings, %LOCALAPPDATA% for state and runtime files.
"""

import os
from contextlib import contextmanager
from pathlib import Path

from . import IS_WINDOWS

APP = "numpad-control"


def config_dir():
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP


def state_dir():
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP / "state"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP


def runtime_dir():
    """Files that only matter while running (service connection, PID file)."""
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP / "run"
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


@contextmanager
def file_lock(path):
    """Exclusive lock on path while inside the with block (between processes too)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as handle:
        if IS_WINDOWS:
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield  # released when the file closes
