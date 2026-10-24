# Numpad Control

Turns a cheap USB numpad into a control pad (like a Stream Deck) on Linux.
Each key runs an action: open apps and websites, control OBS, media and volume,
manage Hyprland windows, type text, run multi-step macros, and more.
Everything is set up in a GTK4 / libadwaita settings window. No code needed.

Built and tested on Arch Linux + Hyprland (Wayland). Linux only for now.

## How it works
- A **background service** (systemd user service) reads the numpad directly with
  evdev and grabs it, so its keys only trigger actions and never type digits.
  The `000` key (which sends three 0s in a burst) is detected as its own key.
- The **settings window** edits `~/.config/numpad-control/config.json`. The service
  reloads it automatically after Save.
- The service fetches the desktop's display variables on every key press, so
  apps open correctly even if it started before Hyprland at boot.

## Every action
| Group | Actions |
|---|---|
| General | Open default browser · Open a website · Open file or folder · Launch an app (picked from installed apps) · Copy text to clipboard · Show a notification |
| Keyboard | Type text · Press keys (`Enter`, `Down Down`, `ctrl+shift+t`, …), via ydotool |
| Screenshot | Full screen · Select a region (saved to `~/Pictures/Screenshots` and copied) |
| Window (Hyprland) | Go to workspace N · Move window to workspace N · Next / previous workspace · Close window · Toggle fullscreen · Toggle floating · Focus a window (by class) · Show / hide scratchpad |
| OBS | Start / stop / toggle / pause / resume recording · Start / stop / toggle streaming · Start / stop streaming AND recording · Switch scene · Show / hide a source in a scene · Mute / unmute an audio source · Turn a filter on / off (voice changer, camera effect, …) · Toggle virtual camera · Toggle replay buffer · Save replay buffer |
| Media | Play / pause · Stop · Next / previous track · Volume up / down · Set volume to N% · Mute speakers · Mute microphone |
| Per-app audio | App volume up / down · Set app volume to N% · Mute / unmute an app (e.g. Spotify, Firefox) |
| Audio output | Switch audio output to a device · Next audio output (cycles through devices) |
| System | Do not disturb on / off (dunst) · Lock screen · Sleep · Shut down · Restart |
| Mode | Toggle a mode · Turn a mode on · Turn a mode off · If a mode is on… (if / otherwise) |
| Advanced | Macro · Run Python (sandboxed) |

Volume up/down (system and per-app) and next/previous workspace repeat while the
key is held.

**Per-app audio** uses PipeWire (`pactl`). An app only has sound to control while
it's playing something; otherwise the action says "Spotify isn't playing any sound
right now". All of an app's sound streams (e.g. several Firefox tabs) change
together. The list button next to the field shows the apps playing sound right now.

**Switching the audio output** moves sound that's already playing too. Devices are
picked by their readable name (e.g. "Built-in Audio Analog Stereo"), from the list
button or typed; part of the name is enough.

**Picking OBS names:** every OBS scene, source, audio source and filter field has a
list button that fetches the real names from OBS (it must be running). The lists
follow each other: the source list shows the sources in the scene you entered, the
filter list the filters on the source you entered. You can still type names by hand.

**Placeholders:** Type text, Copy text to clipboard and Show a notification fill in
`{time}` (e.g. 14:05), `{date}` (e.g. 2026-10-24) and `{clipboard}` (the clipboard's
text) when the key runs; the insert button next to the field adds them at the cursor.
Only these exact names are replaced; other text in braces stays as written.

**Shut down / Restart need confirming:** the first trigger only shows "Press again
to shut down" (or "Hold again" / "Double-tap again", matching the key); repeating it
within 5 seconds confirms. Repeats under 0.4 s count as key bounce. They can't be
used in macros or run from the window's Test button.

## Per key: Press, Hold, Double tap
Every key (except `000`) has three slots. A key with only a Press action fires
instantly; once Hold or Double tap is set, Press fires on release instead.

## Layer key and profiles
- **Layer key** (Settings): hold it and every other key uses its "Layer" actions,
  doubling the number of actions.
- **Profiles** (top left): different actions while a given app is focused,
  matched by Hyprland window class. Anything a profile leaves unset uses Default.
  The profile menu can create, **duplicate** (copies every key, slot and layer key
  to start from), edit and delete profiles.

## Modes and if / otherwise
**Modes** are named on/off switches, e.g. "Stream mode" or "Gaming", created in
Settings → Modes. Each has a live switch there, and the Toggle / Turn on / Turn off
a mode actions flip them from keys or macros (with a popup like "Stream mode on").

**If a mode is on…** checks a mode and runs one of two step lists: "If it's on, run
these steps" and "Otherwise, run these steps". Steps work like macro steps; either
list can be empty (do nothing), but not both. Example: if Stream mode is on, mute
the OBS mic and Spotify; otherwise, mute the system microphone.

Mode states are kept in `~/.local/state/numpad-control/modes.json`, shared by the
service and the window, and survive restarts and reboots. Save reports keys that use
a mode that doesn't exist (e.g. after removing it in Settings).

## Macros
The **Macro** action runs steps top to bottom. A step is any action above, or:
- **Wait** N seconds (up to 60)
- **Wait for window**: wait until an app's window is focused, e.g. after launching it

A macro stops at the first step that fails and says which one. Steps can't be
Run Python, another macro, If a mode is on…, or shut down / restart (mode toggles
can be steps). Problems (unknown key names,
bad window classes, …) are reported when you Save, not when the macro runs.

Example: Launch an app → kitty, Wait for window `kitty`, Type text `claude -r`,
Press keys `Enter`. Text is typed literally (`$HOME` and `\n` stay as written),
apart from the placeholders above.
kdotool is KDE-only, so window control uses Hyprland's `hyprctl` instead.

## Feedback
- On-screen confirmations via SwayOSD, e.g. "● Recording", "Stream ended",
  "Scene: Gaming". Can be turned off in Settings.
- The window shows whether the service is running and the numpad is connected
  (with a "Start service" button if it isn't), lights up keys as you press them,
  and has a **learn mode** (keyboard icon): press a numpad key to select it in the
  window without running its action.
- Errors from an action show as a desktop notification.

## Starting at login
- The background service starts at login (systemd, `default.target`).
- The settings window starts hidden at login (`numpad-control --hidden`, from
  Hyprland's autostart), so it opens instantly from the launcher. Closing it only
  hides it; Ctrl+Q quits it. It writes
  `$XDG_RUNTIME_DIR/numpad-control-window.pid` while running, so bar modules can
  list it as a hidden app.

## Install
Needs Python 3, GTK4 + libadwaita + python-gobject (from the distro), and
optionally OBS 28+, SwayOSD, ydotool, playerctl, wpctl + pactl (PipeWire), grim + slurp,
wl-copy, dunst and Hyprland for the matching actions.

    git clone https://github.com/youssefahmed2017/numpad-control ~/numpad-control
    cd ~/numpad-control
    python -m venv --system-site-packages .venv
    .venv/bin/pip install evdev obsws-python
    ./install.sh          # udev rule (sudo), user service, launcher + app-menu entry

Then open **Numpad Control** from your launcher, click a key, pick an action, Save.

The project currently expects to live in `~/numpad-control`, and the udev rule in
`dist/70-numpad-control.rules` matches one numpad model (USB ID `c0f4:05f5`).
For a different numpad, use "Detect…" in Settings and change the IDs in that rule.

## OBS
In OBS: Tools → WebSocket Server Settings → Enable WebSocket server. Put the
password in the window's Settings (gear icon) → OBS, and use "Test connection".

## Run Python (sandboxed)
An optional advanced action. Snippets are checked before saving and before running.
Allowed imports: webbrowser, time, datetime, math, random, json, re, statistics;
helpers `open_url(url)` and `notify(title, body)`. eval/exec/compile/open,
os/sys/subprocess and every other import, `_` names and introspection attributes
are rejected. Snippets run in a separate process limited to 30 s CPU and 512 MB of
memory, with no file writes and no process spawning. Opening URLs (http/https only)
and notifications are carried out by the trusted parent process.
This is a solid guardrail, not a perfect jail. Don't run snippets from people you
don't trust.

## Commands
    numpad-control                          # open the settings window
    .venv/bin/python -m numpadctl run       # the service (normally via systemd)
    .venv/bin/python -m numpadctl detect    # press a key to find your numpad's USB ID
    .venv/bin/python -m numpadctl list      # list input devices
    journalctl --user -u numpad-control -f  # service log

## Tests
    .venv/bin/python -m unittest discover -s tests -t .

## Plans
- A Windows version (with one Qt settings window for both systems) is planned
  for later.
