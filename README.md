# Numpad Control

Turns a USB numpad into a control pad on Linux: each key runs an action
(open browser/URL, OBS record/stream/scenes, media & volume, sandboxed Python).

## Install
    ./install.sh          # udev rule (sudo), user service, app-menu entry

Then open **Numpad Control** from your launcher, click a key, pick an action, Save.
The service reloads the config automatically (~/.config/numpad-control/config.json).

## Commands
    .venv/bin/python -m numpadctl gui      # settings window
    .venv/bin/python -m numpadctl run      # the daemon (normally via systemd)
    .venv/bin/python -m numpadctl detect   # find your numpad's USB id
    journalctl --user -u numpad-control -f # logs (incl. print() from snippets)

## Per key: Press, Hold, Double tap
Every key (except 000) has three slots. A key with only a Press action fires
instantly; once Hold or Double tap is set, Press fires on release instead.
Volume up/down and next/previous workspace repeat while held.

## Layer key and profiles
- **Layer key** (Settings): hold it and every other key uses its "Layer" actions.
- **Profiles** (top-left): different actions while a given app is focused
  (matched by Hyprland window class). Anything a profile leaves unset uses Default.

## Macros
The "Macro" action runs several actions in a row, with optional waits
(e.g. switch scene → wait 3 s → start streaming + recording). It stops at the
first step that fails. Steps can't be Run Python, another macro, or
shutdown/restart.

Building blocks for automating apps:
- **Type text** / **Press keys** (via ydotool): e.g. `Enter`, `Down Down`, `ctrl+shift+t`.
  Text is typed literally (no `$VARS` or `\n` escapes).
- **Focus a window** and **Wait for window** (Hyprland window class, e.g. `kitty`):
  wait for an app you just launched before typing into it.

Example: Launch kitty → Wait for window `kitty` → Type `claude -r` → Press `Enter`.
(kdotool is KDE-only, so window control uses Hyprland's own `hyprctl` instead.)

## Starting at login
The background service (systemd) makes the keys work and starts at login.
The settings window also starts hidden at login (`numpad-control --hidden`,
from Hyprland's autostart), so it opens instantly; closing it only hides it.
Ctrl+Q quits it for real.

## Feedback
- On-screen confirmations (via SwayOSD), e.g. "Recording" / "Stream ended".
- The window shows whether the service is running and the numpad is connected,
  lights up keys as you press them, and has a **learn mode** (keyboard icon):
  press a numpad key to select it without running its action.

## Tests
    .venv/bin/python -m unittest discover -s tests -t .

## OBS
OBS → Tools → WebSocket Server Settings → Enable. Put the password in "OBS settings…".

## Run Python sandbox
Snippets are checked before saving and before running. Allowed imports:
webbrowser, time, datetime, math, random, json, re, statistics; helpers
`open_url(url)` and `notify(title, body)`. eval/exec/compile/open, os/sys/subprocess
and every other import, `_`-names and introspection attributes are rejected.
Snippets run in a separate process limited to 30 s CPU and 512 MB of memory, with no
file writes and no process spawning. Opening URLs (http/https only) and notifications
are carried out by the trusted parent process.
This is a solid guardrail, not a perfect jail. Don't run snippets from people you don't trust.

## Different numpad?
Use "Detect numpad…" in the window, and change the IDs in dist/70-numpad-control.rules.
