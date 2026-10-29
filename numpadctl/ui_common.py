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


# One plain sentence per action for the picker (also searched: "mute" finds the mic, the speakers and OBS).
ACTION_HINTS = {
    "none": "Does nothing.",
    "open_browser": "Opens your web browser.",
    "open_url": "Opens a web page you choose.",
    "open_path": "Opens a file or a folder.",
    "launch_app": "Starts an app from your installed apps.",
    "copy_text": "Puts text on the clipboard, ready to paste.",
    "show_notification": "Pops up a message on screen.",
    "type_text": "Types text for you, like a snippet or an email address.",
    "press_keys": "Presses a shortcut such as Ctrl+Shift+M.",
    "screenshot_full": "Takes a screenshot of the whole screen.",
    "screenshot_region": "Takes a screenshot of the part you select.",
    "hypr_workspace": "Switches to a virtual desktop.",
    "hypr_move_to_workspace": "Sends the current window to another desktop.",
    "hypr_next_workspace": "Moves to the next desktop.",
    "hypr_prev_workspace": "Moves to the previous desktop.",
    "hypr_close": "Closes the current window.",
    "hypr_fullscreen": "Makes the current window full screen, or back.",
    "hypr_float": "Makes the current window float, or tile again.",
    "focus_window": "Brings an open app's window to the front.",
    "hypr_scratchpad": "Shows or hides the scratchpad window.",
    "obs_start_recording": "Starts recording in OBS.",
    "obs_stop_recording": "Stops recording in OBS.",
    "obs_toggle_recording": "Starts recording, or stops it if it's running.",
    "obs_pause_recording": "Pauses the OBS recording.",
    "obs_resume_recording": "Continues a paused OBS recording.",
    "obs_start_streaming": "Goes live in OBS.",
    "obs_stop_streaming": "Ends the OBS stream.",
    "obs_toggle_streaming": "Goes live, or ends the stream if it's running.",
    "obs_start_both": "Goes live and starts recording at once.",
    "obs_stop_both": "Ends the stream and stops recording at once.",
    "obs_switch_scene": "Changes the OBS scene.",
    "obs_toggle_source": "Shows or hides one thing in an OBS scene (a camera, an overlay).",
    "obs_toggle_mute": "Mutes or unmutes an OBS audio source.",
    "obs_toggle_filter": "Turns an OBS filter on or off.",
    "obs_toggle_virtual_cam": "Starts or stops OBS's virtual camera.",
    "obs_toggle_replay_buffer": "Starts or stops the OBS replay buffer.",
    "obs_save_replay": "Saves the last moments from the OBS replay buffer.",
    "media_play_pause": "Plays or pauses music and video.",
    "media_stop": "Stops the player.",
    "media_next": "Skips to the next track.",
    "media_previous": "Goes back to the previous track.",
    "volume_up": "Turns the volume up (keeps going while held).",
    "volume_down": "Turns the volume down (keeps going while held).",
    "volume_set": "Sets the volume to an exact level.",
    "volume_mute": "Mutes or unmutes the speakers.",
    "mic_mute": "Mutes or unmutes the microphone.",
    "app_volume_up": "Turns one app's volume up, like Spotify or a game.",
    "app_volume_down": "Turns one app's volume down.",
    "app_volume_set": "Sets one app's volume to an exact level.",
    "app_mute": "Mutes or unmutes one app.",
    "output_switch": "Switches sound to speakers or headphones.",
    "output_next": "Cycles through your sound outputs.",
    "dnd_toggle": "Silences notifications, or turns them back on.",
    "lock_screen": "Locks the computer.",
    "suspend": "Puts the computer to sleep (press twice to confirm).",
    "shutdown": "Turns the computer off (press twice to confirm).",
    "reboot": "Restarts the computer (press twice to confirm).",
    "mode_toggle": "Flips a mode on or off (modes change what keys do).",
    "mode_on": "Turns a mode on.",
    "mode_off": "Turns a mode off.",
    "if_mode": "Does one thing if a mode is on, and another if not.",
    "macro": "Runs several actions one after another.",
    "run_python": "Runs your own Python code in a sandbox.",
    "wait": "Pauses a macro for some seconds.",
    "wait_for_window": "Pauses a macro until a window appears.",
}

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
