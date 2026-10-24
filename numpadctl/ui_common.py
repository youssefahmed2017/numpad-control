"""What every settings window needs, independent of the GUI toolkit."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from . import actions, config, sandbox
from .platform import IS_WINDOWS, ipc

APP_ID = "dev.numpadctl.NumpadControl"

LAYOUT = [  # (key, row, column, rowspan)
    ("NumLock", 0, 0, 1), ("/", 0, 1, 1), ("*", 0, 2, 1), ("Backspace", 0, 3, 1),
    ("7", 1, 0, 1), ("8", 1, 1, 1), ("9", 1, 2, 1), ("-", 1, 3, 1),
    ("4", 2, 0, 1), ("5", 2, 1, 1), ("6", 2, 2, 1), ("+", 2, 3, 1),
    ("1", 3, 0, 1), ("2", 3, 1, 1), ("3", 3, 2, 1), ("Enter", 3, 3, 2),
    ("0", 4, 0, 1), ("000", 4, 1, 1), (".", 4, 2, 1),
]
KEY_LABELS = {"NumLock": "Num", "Backspace": "⌫", "Enter": "⏎"}
LAYER_KEY_CHOICES = [k for k, *_ in LAYOUT if k not in config.TAP_ONLY_KEYS]

SLOT_TITLES = {"tap": "Press", "hold": "Hold", "double": "Double tap"}
NONE_BINDING = {"action": "none", "params": {}}


def action_name(action):
    return f"{action.group} · {action.label}" if action.group not in ("General", "Macro") else action.label


ACTION_NAMES = [action_name(a) for a in actions.ACTIONS]
STEP_NAMES = [action_name(a) for a in actions.STEP_ACTIONS]

PYTHON_HELP = (
    "Allowed imports: " + ", ".join(sorted(sandbox.ALLOWED_MODULES)) + ".\n"
    "Helpers: open_url(url), notify(title, body). print() output goes to the log.\n"
    "Banned: eval, exec, open, os, sys, subprocess, any other import, names starting with _."
)


def slot_description(slot, has_extra):
    return {
        "tap": "Runs when released, because this key also has Hold or Double tap"
               if has_extra else "Runs instantly",
        "hold": "Runs after holding the key for about half a second",
        "double": "Runs on two quick presses",
    }[slot]


def new_binding(action):
    """A fresh binding for an action, with its default settings."""
    import copy
    return {"action": action.id, "params": {p.name: copy.deepcopy(p.default) for p in action.params}}


def step_summary(step, action):
    params = step.get("params", {})
    if action.id == "wait":
        return f"Wait {params.get('seconds', '1')} s"
    values = [str(params.get(p.name, p.default)).removesuffix(".desktop")
              for p in action.params if params.get(p.name, p.default) and p.kind != "macro"]
    return ", ".join(values)


def run_in_background(work, done, dispatch):
    """work() in a thread; then dispatch(done, result, error) back on the UI thread."""
    def runner():
        try:
            result, error = work(), None
        except Exception as e:
            result, error = None, e
        dispatch(done, result, error)
    threading.Thread(target=runner, daemon=True).start()


class ServiceLink:
    """Talks to the background service (reconnects forever).

    on_message(message) is called through dispatch on the UI thread; a lost or
    missing service shows up as {"event": "status", "running": False}."""

    def __init__(self, on_message, dispatch):
        self.on_message, self.dispatch = on_message, dispatch
        self.sock = None
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def connected(self):
        return self.sock is not None

    def _loop(self):
        while True:
            try:
                sock = ipc.connect()
            except OSError:
                self.dispatch(self.on_message, {"event": "status", "running": False})
                time.sleep(2)
                continue
            self.sock = sock
            try:
                for line in sock.makefile("r"):
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    message.setdefault("running", True)
                    self.dispatch(self.on_message, message)
            except OSError:
                pass
            self.sock = None
            sock.close()

    def send(self, message):
        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall((json.dumps(message) + "\n").encode())
                except OSError:
                    pass


def start_service():
    """Start the background service (systemd on Linux, the tray app on Windows)."""
    if IS_WINDOWS:
        from .platform.windows_tray import autostart_command
        subprocess.Popen(autostart_command(), creationflags=0x00000008)  # DETACHED_PROCESS
    else:
        subprocess.run(["systemctl", "--user", "start", "numpad-control"], check=False)


def installed_apps():
    """[(display name, app id)] for "Launch an app", sorted by name.

    Linux: .desktop ids (e.g. "kitty.desktop"); Windows: Start-menu shortcuts (.lnk paths)."""
    if IS_WINDOWS:
        roots = [Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs"]
        apps = {}
        for root in roots:
            for link in root.rglob("*.lnk") if root.exists() else []:
                name = link.stem
                if not any(w in name.lower() for w in ("uninstall", "readme", "help")):
                    apps.setdefault(name, str(link))
        return sorted(apps.items(), key=lambda a: a[0].lower())
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio
    except (ImportError, ValueError):
        return []
    apps = [(a.get_display_name(), a.get_id()) for a in Gio.AppInfo.get_all() if a.should_show()]
    return sorted(apps, key=lambda a: a[0].lower())
