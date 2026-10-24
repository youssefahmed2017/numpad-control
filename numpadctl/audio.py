"""Per-app volume and output switching, via PipeWire's PulseAudio interface (pactl).

An app only has a sound stream while it's playing something, so per-app
actions say so instead of silently doing nothing when the app is quiet.
"""

import json
import shutil
import subprocess


class AudioError(Exception):
    pass


def _pactl(*args):
    if not shutil.which("pactl"):
        raise AudioError("pactl is not installed (sudo pacman -S libpulse)")
    done = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5)
    if done.returncode != 0:
        raise AudioError(done.stderr.strip() or f"pactl {args[0]} failed")
    return done.stdout


def _list(kind):
    return json.loads(_pactl("-f", "json", "list", kind) or "[]")


# ---------------------------------------------------------------- apps

def app_name(stream):
    p = stream.get("properties", {})
    return p.get("application.name") or p.get("application.process.binary") or "Unknown app"


def _matches(stream, app):
    p = stream.get("properties", {})
    names = {(p.get("application.name") or "").lower(),
             (p.get("application.process.binary") or "").lower()}
    return app.strip().lower() in names


def playing_apps():
    return sorted({app_name(s) for s in _list("sink-inputs")}, key=str.lower)


def _streams(app):
    if not app.strip():
        raise AudioError("no app set")
    found = [s for s in _list("sink-inputs") if _matches(s, app)]
    if not found:
        raise AudioError(f"{app.strip()} isn't playing any sound right now")
    return found


def _percent(stream):
    return max(int(ch["value_percent"].rstrip("%")) for ch in stream["volume"].values())


def _set_level(streams, level_for):
    """Set each stream to level_for(stream) (clamped to 0-100); returns the first one's level."""
    levels = []
    for s in streams:
        level = max(0, min(100, level_for(s)))
        _pactl("set-sink-input-volume", str(s["index"]), f"{level}%")
        levels.append(level)
    return f"{app_name(streams[0])} {levels[0]}%"


def change_app_volume(app, delta):
    return _set_level(_streams(app), lambda s: _percent(s) + delta)


def set_app_volume(app, percent):
    return _set_level(_streams(app), lambda s: percent)


def toggle_app_mute(app):
    streams = _streams(app)
    mute = not streams[0]["mute"]  # every stream follows the first one
    for s in streams:
        _pactl("set-sink-input-mute", str(s["index"]), "1" if mute else "0")
    return f"{app_name(streams[0])} {'muted' if mute else 'unmuted'}"


# ---------------------------------------------------------------- outputs

def outputs():
    """Output devices by their readable name, e.g. "Built-in Audio Analog Stereo"."""
    return [s["description"] for s in _list("sinks")]


def _simple(name):
    return name.replace("_", " ").strip().lower()


def _find_output(sinks, wanted):
    if not wanted.strip():
        raise AudioError("no output device set")
    want = _simple(wanted)
    for s in sinks:  # exact readable or internal name first
        if want in (_simple(s["description"]), _simple(s["name"])):
            return s
    for s in sinks:
        if want in _simple(s["description"]):
            return s
    raise AudioError(f"no output device called {wanted.strip()!r} is connected")


def _use_output(sink):
    _pactl("set-default-sink", sink["name"])
    for stream in _list("sink-inputs"):  # move what's already playing too
        _pactl("move-sink-input", str(stream["index"]), sink["name"])
    return sink["description"]


def switch_output(wanted):
    return _use_output(_find_output(_list("sinks"), wanted))


def next_output():
    sinks = sorted(_list("sinks"), key=lambda s: s["index"])
    if not sinks:
        raise AudioError("no output devices found")
    current = _pactl("get-default-sink").strip()
    names = [s["name"] for s in sinks]
    after = (names.index(current) + 1) % len(sinks) if current in names else 0
    return _use_output(sinks[after])
