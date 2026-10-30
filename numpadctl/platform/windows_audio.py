"""Per-app volume, microphone mute and output switching on Windows (Core Audio via pycaw).

The same functions as numpadctl/audio.py (PipeWire on Linux). An app is matched by
its program name without ".exe" (e.g. "spotify", "firefox", "Discord"), ignoring
case; it only has a sound session while it's playing something.
"""

from contextlib import contextmanager
from pathlib import Path


class AudioError(Exception):
    pass


@contextmanager
def _audio():
    """Core Audio is COM: every thread (actions run in background threads) needs it set up."""
    try:
        import comtypes
        from pycaw import constants
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        raise AudioError("pycaw isn't installed (python -m pip install -r requirements.txt)")
    comtypes.CoInitialize()
    try:
        yield AudioUtilities, constants
    finally:
        comtypes.CoUninitialize()


# ---------------------------------------------------------------- apps

def app_name(session):
    process = session.Process  # None for Windows' own "System sounds"
    return Path(process.name()).stem if process else ""


def playing_apps():
    with _audio() as (utils, _):
        names = {app_name(s) for s in utils.GetAllSessions()}
    return sorted((n for n in names if n), key=str.lower)


def _sessions(utils, app):
    if not app.strip():
        raise AudioError("no app set")
    found = [s for s in utils.GetAllSessions() if app_name(s).lower() == app.strip().lower()]
    if not found:
        raise AudioError(f"{app.strip()} isn't playing any sound right now")
    return found


def _set_level(sessions, level_for):
    levels = []
    for s in sessions:
        volume = s.SimpleAudioVolume
        level = max(0, min(100, level_for(round(volume.GetMasterVolume() * 100))))
        volume.SetMasterVolume(level / 100, None)
        levels.append(level)
    return f"{app_name(sessions[0])} {levels[0]}%"


def change_app_volume(app, delta):
    with _audio() as (utils, _):
        return _set_level(_sessions(utils, app), lambda now: now + delta)


def set_app_volume(app, percent):
    with _audio() as (utils, _):
        return _set_level(_sessions(utils, app), lambda now: percent)


def toggle_app_mute(app):
    with _audio() as (utils, _):
        sessions = _sessions(utils, app)
        mute = not sessions[0].SimpleAudioVolume.GetMute()  # every session follows the first
        for s in sessions:
            s.SimpleAudioVolume.SetMute(int(mute), None)
        return f"{app_name(sessions[0])} {'muted' if mute else 'unmuted'}"


# ---------------------------------------------------------------- microphone

def toggle_microphone_mute():
    with _audio() as (utils, _):
        microphone = utils.GetMicrophone()
        if microphone is None:
            raise AudioError("no microphone found")
        volume = utils.CreateDevice(microphone).EndpointVolume
        mute = not volume.GetMute()
        volume.SetMute(int(mute), None)
    return "Microphone muted" if mute else "Microphone unmuted"


def set_mute(microphone, muted):
    """Mute (or unmute) the default microphone or speakers, whatever state it is in now."""
    with _audio() as (utils, _):
        device = utils.GetMicrophone() if microphone else utils.GetSpeakers()
        if device is None:
            raise AudioError("no microphone found" if microphone else "no speakers found")
        utils.CreateDevice(device).EndpointVolume.SetMute(int(muted), None)


# ---------------------------------------------------------------- outputs

def _outputs(utils, constants):
    return [d for d in utils.GetAllDevices(constants.EDataFlow.eRender.value, constants.DEVICE_STATE.ACTIVE.value)
            if d.FriendlyName]


def outputs():
    """Output devices by their readable name, e.g. "Speakers (Realtek(R) Audio)"."""
    with _audio() as (utils, constants):
        return [d.FriendlyName for d in _outputs(utils, constants)]


def _simple(name):
    return name.replace("_", " ").strip().lower()


def _use(utils, constants, device):
    roles = [constants.ERole.eConsole, constants.ERole.eMultimedia, constants.ERole.eCommunications]
    utils.SetDefaultDevice(device.id, roles=roles)  # apps playing on the default device move along
    return device.FriendlyName


def switch_output(wanted):
    if not wanted.strip():
        raise AudioError("no output device set")
    want = _simple(wanted)
    with _audio() as (utils, constants):
        devices = _outputs(utils, constants)
        match = next((d for d in devices if _simple(d.FriendlyName) == want), None) \
            or next((d for d in devices if want in _simple(d.FriendlyName)), None)
        if match is None:
            raise AudioError(f"no output device called {wanted.strip()!r} is connected")
        return _use(utils, constants, match)


def next_output():
    with _audio() as (utils, constants):
        devices = _outputs(utils, constants)
        if not devices:
            raise AudioError("no output devices found")
        speakers = utils.GetSpeakers()
        ids = [d.id for d in devices]
        after = (ids.index(speakers.id) + 1) % len(devices) if speakers and speakers.id in ids else 0
        return _use(utils, constants, devices[after])
