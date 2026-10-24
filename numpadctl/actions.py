"""Everything a key can be bound to."""

import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from . import obs, sandbox


@dataclass
class Param:
    name: str
    label: str
    kind: str = "text"  # "text", "code", "app" (a .desktop id) or "macro" (a list of steps)
    default: object = ""


@dataclass
class Action:
    id: str
    label: str
    run: callable  # run(config, **params)
    params: list = field(default_factory=list)
    group: str = "General"
    osd_icon: str = ""     # if set, the returned message is shown on screen
    repeat: bool = False   # keeps running while the key is held
    confirm: bool = False  # needs a second press; never run by "Test now" or macros
    check: callable = None # check(**params) raises ActionError for bad settings


class ActionError(Exception):
    pass


def notify(title, body=""):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Numpad Control", title, body],
                       check=False, timeout=5)


def show_osd(cfg, message, icon="dialog-information-symbolic", force=False):
    """Short on-screen confirmation (SwayOSD if available, else a notification)."""
    if not force and not cfg.get("feedback", True):
        return
    if shutil.which("swayosd-client"):
        done = subprocess.run(["swayosd-client", "--custom-message", message,
                               "--custom-icon", icon], capture_output=True, timeout=5)
        if done.returncode == 0:
            return
    notify(message)


def _command(*argv):
    if not shutil.which(argv[0]):
        raise ActionError(f"'{argv[0]}' is not installed")
    subprocess.run(argv, check=False, timeout=10)


def _detached(*argv):
    if not shutil.which(argv[0]):
        raise ActionError(f"'{argv[0]}' is not installed")
    subprocess.Popen(argv, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_browser(cfg, url=""):
    webbrowser.open(url.strip() or "about:blank")


def _open_url(cfg, url):
    if not url.strip():
        raise ActionError("no URL set")
    webbrowser.open(url.strip())


def _open_path(cfg, path):
    if not path.strip():
        raise ActionError("no file or folder set")
    _detached("xdg-open", path.strip())


def _run_python(cfg, code):
    ok, output = sandbox.run(code)
    if not ok:
        raise ActionError(output or "snippet failed")
    return output


def _launch_app(cfg, app):
    import gi
    try:
        gi.require_version("GioUnix", "2.0")
        from gi.repository.GioUnix import DesktopAppInfo
    except (ValueError, ImportError):
        from gi.repository.Gio import DesktopAppInfo
    try:
        info = DesktopAppInfo.new(app)
    except TypeError:
        info = None
    if info is None:
        raise ActionError(f"app {app!r} is not installed")
    _detached("gio", "launch", info.get_filename())


def _copy_text(cfg, text):
    _command("wl-copy", "--", text)
    return "Copied"


def _toggle_dnd(cfg):
    _command("dunstctl", "set-paused", "toggle")
    paused = subprocess.run(["dunstctl", "is-paused"], capture_output=True, text=True).stdout.strip()
    return "Do not disturb on" if paused == "true" else "Do not disturb off"


def _show_notification(cfg, title, body):
    notify(title or "Numpad", body)


def _lock_screen(cfg):
    if shutil.which("hyprlock"):
        _detached("hyprlock")
    else:
        _command("loginctl", "lock-session")


def _screenshot(cfg, region=False):
    folder = Path.home() / "Pictures" / "Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("%Y-%m-%d_%H-%M-%S.png")
    argv = ["grim"]
    if region:
        pick = subprocess.run(["slurp"], capture_output=True, text=True)
        if pick.returncode != 0:
            return "cancelled"
        argv += ["-g", pick.stdout.strip()]
    _command(*argv, str(path))
    with open(path, "rb") as image:
        subprocess.run(["wl-copy", "--type", "image/png"], stdin=image, check=False, timeout=5)
    notify("Screenshot saved", f"{path} (also copied)")


def _hyprctl(lua):
    if not shutil.which("hyprctl"):
        raise ActionError("Hyprland is not running")
    out = subprocess.run(["hyprctl", "dispatch", lua], capture_output=True, text=True, timeout=5)
    if out.stdout.strip() != "ok":
        raise ActionError(out.stdout.strip() or out.stderr.strip())


def _hypr(lua):
    return lambda cfg: _hyprctl(lua)


def active_window_class():
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or not shutil.which("hyprctl"):
        return ""
    try:
        out = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True,
                             text=True, timeout=1).stdout
        return json.loads(out).get("class", "") if out.lstrip().startswith("{") else ""
    except (subprocess.SubprocessError, ValueError):
        return ""


def _window_class(value):
    value = value.strip()
    if not re.fullmatch(r"[\w.\-]+", value):
        raise ActionError(f"window class must be a name like kitty or firefox, not {value!r}")
    return value


def _focus_window(cfg, window):
    _hyprctl(f'hl.dsp.focus({{ window = "class:{_window_class(window)}" }})')


MAX_WINDOW_WAIT = 60


def _wait_for_window(cfg, window, seconds):
    """Wait until a window of this class is focused (e.g. an app just launched)."""
    wanted, limit = _window_class(window).lower(), _wait_seconds(seconds)
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if active_window_class().lower() == wanted:
            return
        time.sleep(0.1)
    raise ActionError(f"no {wanted} window was focused within {limit:g} s")


# ---------------------------------------------------------------- keyboard (ydotool)

KEY_ALIASES = {
    "ctrl": "LEFTCTRL", "control": "LEFTCTRL", "shift": "LEFTSHIFT", "alt": "LEFTALT",
    "altgr": "RIGHTALT", "super": "LEFTMETA", "win": "LEFTMETA", "meta": "LEFTMETA",
    "return": "ENTER", "esc": "ESC", "escape": "ESC", "del": "DELETE", "ins": "INSERT",
    "pgup": "PAGEUP", "pgdn": "PAGEDOWN", "bksp": "BACKSPACE", "caps": "CAPSLOCK",
    "print": "SYSRQ", "printscreen": "SYSRQ", "menu": "COMPOSE",
}
MAX_KEY_PRESSES = 50


def parse_keys(text):
    """'ctrl+shift+t Down Enter' -> [[codes of one combination], ...]"""
    from evdev import ecodes
    combos = []
    for chunk in text.replace(",", " ").split():
        codes = []
        for name in chunk.split("+"):
            code = ecodes.ecodes.get("KEY_" + KEY_ALIASES.get(name.lower(), name.upper())) if name else None
            if code is None:
                raise ActionError(f"unknown key {name or chunk!r} (examples: ctrl+c, Down, Enter, F5)")
            codes.append(code)
        combos.append(codes)
    if not combos:
        raise ActionError("no keys set")
    if len(combos) > MAX_KEY_PRESSES:
        raise ActionError(f"at most {MAX_KEY_PRESSES} key presses")
    return combos


def _ydotool(*args, stdin=None):
    if not shutil.which("ydotool"):
        raise ActionError("ydotool is not installed (sudo pacman -S ydotool)")
    done = subprocess.run(["ydotool", *args], input=stdin, capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise ActionError("ydotool failed - is its service running? "
                          "(systemctl --user enable --now ydotool)")


def _press_keys(cfg, keys):
    events = []
    for combo in parse_keys(keys):
        events += [f"{code}:1" for code in combo]            # hold them down in order
        events += [f"{code}:0" for code in reversed(combo)]  # let go in reverse
    _ydotool("key", *events)


def _type_text(cfg, text):
    if not text:
        raise ActionError("no text set")
    _ydotool("type", "--escape", "0", "--file", "-", stdin=text)


def _workspace_number(value):
    try:
        number = int(value)
    except ValueError:
        raise ActionError(f"workspace must be a number, not {value!r}")
    if not 1 <= number <= 99:
        raise ActionError("workspace must be between 1 and 99")
    return number


def _go_to_workspace(cfg, workspace):
    _hyprctl(f"hl.dsp.focus({{ workspace = {_workspace_number(workspace)} }})")


def _move_to_workspace(cfg, workspace):
    _hyprctl(f"hl.dsp.window.move({{ workspace = {_workspace_number(workspace)} }})")


def _volume(osd_args, wpctl_args):
    """Use SwayOSD (shows the volume popup) when it's running, else wpctl."""
    def run(cfg):
        if shutil.which("swayosd-client"):
            osd = subprocess.run(["swayosd-client", *osd_args], capture_output=True, timeout=5)
            if osd.returncode == 0:
                return
        _command("wpctl", *wpctl_args)
    return run


def _set_volume(cfg, percent):
    try:
        level = int(percent.strip().rstrip("%"))
    except ValueError:
        raise ActionError(f"volume must be a number, not {percent!r}")
    _command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{max(0, min(level, 100))}%")
    if shutil.which("swayosd-client"):
        # swayosd treats a bare number as "raise by", so set with wpctl and
        # just show the popup with +0.
        subprocess.run(["swayosd-client", "--output-volume", "+0"], capture_output=True, timeout=5)


# Shutdown / restart: the second press must come within this window. Presses
# closer together than the minimum count as a bounce and just re-arm.
CONFIRM_MIN_SECONDS = 0.4
CONFIRM_MAX_SECONDS = 5.0
_armed = {}
_armed_lock = threading.Lock()


def _confirmed(action_id):
    """True on a deliberate second press; otherwise arms and returns False."""
    now = time.monotonic()
    with _armed_lock:
        armed_at = _armed.pop(action_id, None)
        if armed_at is not None and CONFIRM_MIN_SECONDS <= now - armed_at <= CONFIRM_MAX_SECONDS:
            return True
        _armed[action_id] = now
        return False


AGAIN = {"tap": "Press again", "hold": "Hold again", "double": "Double-tap again"}


def _power(action_id, verb, question, doing, icon):
    def run(cfg, trigger="tap"):
        if not _confirmed(action_id):
            show_osd(cfg, f"{AGAIN.get(trigger, AGAIN['tap'])} {question}", icon, force=True)
            return
        show_osd(cfg, doing, icon, force=True)
        _command("systemctl", verb)
    return run


MAX_WAIT_SECONDS = 60
MAX_MACRO_STEPS = 30


def _wait_seconds(value):
    try:
        seconds = float(str(value).strip().rstrip("s"))
    except ValueError:
        raise ActionError(f"wait must be a number of seconds, not {value!r}")
    if not 0 <= seconds <= MAX_WAIT_SECONDS:
        raise ActionError(f"wait must be between 0 and {MAX_WAIT_SECONDS} seconds")
    return seconds


def _wait(cfg, seconds):
    time.sleep(_wait_seconds(seconds))


def _raise(message):
    raise ActionError(message)


def binding_problems(binding):
    """Problems with a binding's settings, found before it ever runs."""
    action = BY_ID.get(binding.get("action"))
    if action is None:
        return [f"unknown action {binding.get('action')!r}"]
    if action.id == "macro":
        return macro_problems(binding.get("params", {}).get("steps", []))
    if action.check:
        given = binding.get("params", {})
        try:
            action.check(**{p.name: given.get(p.name, p.default) for p in action.params})
        except ActionError as e:
            return [str(e)]
    return []


def macro_problems(steps):
    """Problems that would stop a macro from running; empty list means OK."""
    if not steps:
        return ["the macro has no steps"]
    if len(steps) > MAX_MACRO_STEPS:
        return [f"a macro can have at most {MAX_MACRO_STEPS} steps"]
    problems = []
    for i, step in enumerate(steps, 1):
        if step.get("action") not in STEP_IDS:
            problems.append(f"step {i}: {step.get('action')!r} can't be used in a macro")
        else:
            problems += [f"step {i}: {p}" for p in binding_problems(step)]
    return problems


def _macro(cfg, steps):
    problems = macro_problems(steps)
    if problems:
        raise ActionError("; ".join(problems))
    for i, step in enumerate(steps, 1):
        try:
            run(cfg, step)
        except Exception as e:
            raise ActionError(f"step {i} ({BY_ID[step['action']].label}) failed: {e}")


def _obs(fn):
    return lambda cfg, **p: fn(cfg["obs"], **p)


def _playerctl(arg):
    """Use SwayOSD's player popup when it's running, else plain playerctl."""
    def run(cfg):
        if shutil.which("swayosd-client"):
            osd = subprocess.run(["swayosd-client", "--playerctl", arg], capture_output=True, timeout=5)
            if osd.returncode == 0:
                return
        _command("playerctl", "previous" if arg == "prev" else arg)
    return run


SINK, SOURCE = "@DEFAULT_AUDIO_SINK@", "@DEFAULT_AUDIO_SOURCE@"

ACTIONS = [
    Action("none", "(nothing)", lambda cfg: None),
    Action("open_browser", "Open default browser", _open_browser,
           [Param("url", "Start page (optional)")]),
    Action("open_url", "Open a website", _open_url, [Param("url", "URL")]),
    Action("open_path", "Open file or folder", _open_path,
           [Param("path", "Path")]),
    Action("launch_app", "Launch an app", _launch_app,
           [Param("app", "App", kind="app")]),
    Action("copy_text", "Copy text to clipboard", _copy_text,
           [Param("text", "Text")], osd_icon="edit-copy-symbolic"),
    Action("show_notification", "Show a notification", _show_notification,
           [Param("title", "Title"), Param("body", "Message")]),

    Action("type_text", "Type text", _type_text, [Param("text", "Text to type")],
           group="Keyboard", check=lambda text: None if text else _raise("no text set")),
    Action("press_keys", "Press keys", _press_keys,
           [Param("keys", "Keys (e.g. Enter, Down Down, ctrl+shift+t)", default="Enter")],
           group="Keyboard", check=lambda keys: parse_keys(keys)),

    Action("screenshot_full", "Full screen", lambda cfg: _screenshot(cfg), group="Screenshot"),
    Action("screenshot_region", "Select a region", lambda cfg: _screenshot(cfg, region=True),
           group="Screenshot"),

    Action("hypr_workspace", "Go to workspace", _go_to_workspace,
           [Param("workspace", "Workspace number", default="1")], group="Window"),
    Action("hypr_move_to_workspace", "Move window to workspace", _move_to_workspace,
           [Param("workspace", "Workspace number", default="2")], group="Window"),
    Action("hypr_next_workspace", "Next workspace",
           _hypr('hl.dsp.focus({ workspace = "e+1" })'), group="Window", repeat=True),
    Action("hypr_prev_workspace", "Previous workspace",
           _hypr('hl.dsp.focus({ workspace = "e-1" })'), group="Window", repeat=True),
    Action("hypr_close", "Close window", _hypr("hl.dsp.window.close()"), group="Window"),
    Action("hypr_fullscreen", "Toggle fullscreen",
           _hypr('hl.dsp.window.fullscreen({ mode = "fullscreen" })'), group="Window"),
    Action("hypr_float", "Toggle floating",
           _hypr('hl.dsp.window.float({ action = "toggle" })'), group="Window"),
    Action("focus_window", "Focus a window", _focus_window,
           [Param("window", "Window class (e.g. kitty, firefox)", default="kitty")], group="Window",
           check=lambda window: _window_class(window)),
    Action("hypr_scratchpad", "Show / hide scratchpad",
           _hypr('hl.dsp.workspace.toggle_special("magic")'), group="Window"),

    Action("obs_start_recording", "Start recording", _obs(obs.start_recording), group="OBS", osd_icon="media-record-symbolic"),
    Action("obs_stop_recording", "Stop recording", _obs(obs.stop_recording), group="OBS", osd_icon="media-playback-stop-symbolic"),
    Action("obs_toggle_recording", "Toggle recording", _obs(obs.toggle_recording), group="OBS", osd_icon="media-record-symbolic"),
    Action("obs_pause_recording", "Pause recording", _obs(obs.pause_recording), group="OBS", osd_icon="media-playback-pause-symbolic"),
    Action("obs_resume_recording", "Resume recording", _obs(obs.resume_recording), group="OBS", osd_icon="media-record-symbolic"),
    Action("obs_start_streaming", "Start streaming", _obs(obs.start_streaming), group="OBS", osd_icon="camera-video-symbolic"),
    Action("obs_stop_streaming", "Stop streaming", _obs(obs.stop_streaming), group="OBS", osd_icon="media-playback-stop-symbolic"),
    Action("obs_toggle_streaming", "Toggle streaming", _obs(obs.toggle_streaming), group="OBS", osd_icon="camera-video-symbolic"),
    Action("obs_start_both", "Start streaming AND recording", _obs(obs.start_both), group="OBS", osd_icon="media-record-symbolic"),
    Action("obs_stop_both", "Stop streaming AND recording", _obs(obs.stop_both), group="OBS", osd_icon="media-playback-stop-symbolic"),
    Action("obs_switch_scene", "Switch scene", _obs(obs.switch_scene),
           [Param("scene", "Scene name")], group="OBS", osd_icon="view-grid-symbolic"),
    Action("obs_toggle_source", "Show / hide a source", _obs(obs.toggle_source),
           [Param("scene", "Scene name"), Param("source", "Source name")], group="OBS", osd_icon="view-reveal-symbolic"),
    Action("obs_toggle_mute", "Mute / unmute audio source", _obs(obs.toggle_mute),
           [Param("source", "Source name", default="Mic/Aux")], group="OBS", osd_icon="audio-input-microphone-symbolic"),
    Action("obs_toggle_virtual_cam", "Toggle virtual camera", _obs(obs.toggle_virtual_cam), group="OBS", osd_icon="camera-web-symbolic"),
    Action("obs_toggle_replay_buffer", "Toggle replay buffer", _obs(obs.toggle_replay_buffer), group="OBS", osd_icon="media-playlist-repeat-symbolic"),
    Action("obs_save_replay", "Save replay buffer", _obs(obs.save_replay), group="OBS", osd_icon="document-save-symbolic"),

    Action("media_play_pause", "Play / pause", _playerctl("play-pause"), group="Media"),
    Action("media_stop", "Stop", _playerctl("stop"), group="Media"),
    Action("media_next", "Next track", _playerctl("next"), group="Media"),
    Action("media_previous", "Previous track", _playerctl("prev"), group="Media"),
    Action("volume_up", "Volume up",
           _volume(["--max-volume", "100", "--output-volume", "+5"],
                   ["set-volume", "-l", "1.0", SINK, "5%+"]), group="Media", repeat=True),
    Action("volume_down", "Volume down",
           _volume(["--output-volume", "-5"], ["set-volume", SINK, "5%-"]), group="Media", repeat=True),
    Action("volume_set", "Set volume to…", _set_volume,
           [Param("percent", "Volume %", default="50")], group="Media"),
    Action("volume_mute", "Mute / unmute speakers",
           _volume(["--output-volume", "mute-toggle"], ["set-mute", SINK, "toggle"]), group="Media"),
    Action("mic_mute", "Mute / unmute microphone",
           _volume(["--input-volume", "mute-toggle"], ["set-mute", SOURCE, "toggle"]), group="Media"),

    Action("dnd_toggle", "Do not disturb on / off", _toggle_dnd, group="System",
           osd_icon="notifications-disabled-symbolic"),
    Action("lock_screen", "Lock screen", _lock_screen, group="System"),
    Action("suspend", "Sleep (suspend)", lambda cfg: _command("systemctl", "suspend"), group="System"),
    Action("shutdown", "Shut down (press twice)",
           _power("shutdown", "poweroff", "to shut down", "Shutting down…",
                  "system-shutdown-symbolic"), group="System", confirm=True),
    Action("reboot", "Restart (press twice)",
           _power("reboot", "reboot", "to restart", "Restarting…",
                  "system-reboot-symbolic"), group="System", confirm=True),

    Action("macro", "Macro", _macro,
           [Param("steps", "Steps", kind="macro", default=[])], group="Advanced"),
    Action("run_python", "Run Python (sandboxed)", _run_python,
           [Param("code", "Python code", kind="code",
                  default='import webbrowser\nwebbrowser.open("https://example.com")\n')],
           group="Advanced"),
]

# Only used as a macro step.
WAIT = Action("wait", "Wait", _wait, [Param("seconds", "Seconds", default="1")],
              group="Macro", check=lambda seconds: _wait_seconds(seconds))
WAIT_FOR_WINDOW = Action(
    "wait_for_window", "Wait for window", _wait_for_window,
    [Param("window", "Window class (e.g. kitty)", default="kitty"),
     Param("seconds", "Give up after (seconds)", default="10")],
    group="Macro", check=lambda window, seconds: (_window_class(window), _wait_seconds(seconds)))

# What a macro step can be: no nested macros, no Python (it has its own editor),
# and nothing that needs a confirming second press (shutdown / restart).
STEP_ACTIONS = [WAIT, WAIT_FOR_WINDOW] + [a for a in ACTIONS
                         if a.id not in ("none", "macro", "run_python") and not a.confirm]
STEP_IDS = {a.id for a in STEP_ACTIONS}

BY_ID = {a.id: a for a in ACTIONS + [WAIT, WAIT_FOR_WINDOW]}


def perform(cfg, binding, trigger="tap"):
    """Run a binding dict {"action": id, "params": {...}}. Raises on failure."""
    action = BY_ID.get(binding.get("action", "none"))
    if action is None:
        raise ActionError(f"unknown action {binding.get('action')!r}")
    given = binding.get("params", {})
    params = {p.name: given.get(p.name, copy.deepcopy(p.default)) for p in action.params}
    try:
        if action.confirm:  # the prompt says how to confirm: press / hold / double-tap
            params["trigger"] = trigger
        return action.run(cfg, **params)
    except obs.OBSError as e:
        raise ActionError(str(e))


def run(cfg, binding, trigger="tap"):
    """perform() plus the on-screen confirmation. Returns any text output.

    trigger is the slot that fired it ("tap", "hold" or "double").
    """
    output = perform(cfg, binding, trigger)
    action = BY_ID[binding.get("action", "none")]
    if action.osd_icon and isinstance(output, str) and output:
        show_osd(cfg, output, action.osd_icon)
    return output


def is_set(binding):
    return bool(binding) and binding.get("action", "none") != "none"
