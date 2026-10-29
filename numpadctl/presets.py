"""Starter setups: keys filled in for a common job, so a new pad isn't 17 empty keys.

Only actions that work the same on Linux and Windows without further set-up are used
(OBS ones need OBS' WebSocket turned on, but no scene or source names). Applying a
preset never replaces a key that already has something.
"""

import copy
from dataclasses import dataclass

from . import actions


@dataclass
class Preset:
    name: str
    description: str
    keys: dict  # key -> {slot: (action id, {param: value})}


def _k(action, **params):
    return {"tap": (action, params)}


PRESETS = [
    Preset("Streaming (OBS)", "Go live, record, clip and mute. Needs OBS with its WebSocket server on (Settings → OBS).", {
        "7": _k("obs_toggle_streaming"), "8": _k("obs_toggle_recording"), "9": _k("obs_save_replay"),
        "4": _k("obs_toggle_replay_buffer"), "5": _k("mic_mute"), "6": _k("obs_toggle_virtual_cam"),
        "1": _k("volume_down"), "2": _k("volume_mute"), "3": _k("volume_up"),
        "+": _k("obs_toggle_pause_recording"),
    }),
    Preset("Media and volume", "Play, skip, volume and the microphone.", {
        "7": _k("media_previous"), "8": _k("media_play_pause"), "9": _k("media_next"),
        "4": _k("volume_down"), "5": _k("volume_mute"), "6": _k("volume_up"),
        "1": _k("mic_mute"), "2": _k("output_next"), "3": _k("media_stop"),
        "+": _k("volume_up"), "-": _k("volume_down"), "Enter": _k("media_play_pause"),
    }),
    Preset("Editing", "Copy, paste, cut, undo, redo, save, select all, screenshots.", {
        "1": _k("press_keys", keys="ctrl+c"), "2": _k("press_keys", keys="ctrl+v"), "3": _k("press_keys", keys="ctrl+x"),
        "4": _k("press_keys", keys="ctrl+z"), "5": _k("press_keys", keys="ctrl+shift+z"),
        "6": _k("press_keys", keys="ctrl+s"), "7": _k("press_keys", keys="ctrl+a"),
        "8": _k("screenshot_region"), "9": _k("screenshot_full"),
        "Enter": _k("press_keys", keys="Enter"),
    }),
    Preset("Windows and desktops", "Switch desktops, maximize and close the focused window (close = hold).", {
        "4": _k("hypr_prev_workspace"), "6": _k("hypr_next_workspace"),
        "8": _k("hypr_fullscreen"), "5": _k("lock_screen"),
        "2": {"hold": ("hypr_close", {})},
        "7": _k("screenshot_region"), "9": _k("screenshot_full"),
    }),
]
BY_NAME = {p.name: p for p in PRESETS}


def binding(action_id, params):
    action = actions.BY_ID[action_id]
    full = {p.name: copy.deepcopy(p.default) for p in action.params}
    full.update(params)
    return {"action": action_id, "params": full}


def apply(preset, keymap):
    """Add the preset's keys to keymap ({key: {slot: binding}}) wherever nothing is set yet.

    Returns (added, kept): slots filled, and slots skipped because they already had an action."""
    added = kept = 0
    for key, slots in preset.keys.items():
        mine = keymap.setdefault(key, {})
        for slot, (action_id, params) in slots.items():
            if actions.is_set(mine.get(slot, {"action": "none"})):
                kept += 1
            else:
                mine[slot] = binding(action_id, params)
                added += 1
    return added, kept
