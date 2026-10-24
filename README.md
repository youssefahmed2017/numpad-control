# Numpad Control

Turns a cheap USB numpad into a control pad (like a Stream Deck) on Linux.
Each key runs an action: open apps and websites, control OBS, media and volume,
manage windows and desktops, type text, run multi-step macros, and more.
Everything is set up in a GTK4 / libadwaita settings window. No code needed.

Built and tested on Arch Linux with **Hyprland** and **KDE Plasma 6** (Wayland).
Linux only for now.

![The settings window: a numpad on the left, the selected key's "Go live" macro on the right](docs/screenshots/macro.png)

## Screenshots
| | |
|---|---|
| ![If a mode is on: different steps depending on "Stream mode"](docs/screenshots/if-mode.png) | ![Hold slot with the rapid-fire switch](docs/screenshots/hold.png) |
| **If a mode is on…** runs one of two step lists | **Press / Hold / Double tap** per key, with rapid-fire |
| ![Settings: device, layer key, modes and OBS](docs/screenshots/settings.png) | ![The on-screen "Recording" popup after pressing the record key](docs/screenshots/popup.png) |
| **Settings**: numpad, layer key, modes, OBS | **On-screen confirmation** when a key runs |

## How it works
- A **background service** (systemd user service) reads the numpad directly with
  evdev and grabs it, so its keys only trigger actions and never type digits.
  The `000` key (which sends three 0s in a burst) is detected as its own key.
- The **settings window** edits `~/.config/numpad-control/config.json`. The service
  reloads it automatically after Save.
- The service fetches the desktop's display variables on every key press, so
  apps open correctly even if it started before the desktop at boot, and it
  switches between Hyprland and KDE tools when you log out of one desktop and
  into the other (no restart needed).

## Hyprland and KDE Plasma
The desktop is detected automatically (`XDG_CURRENT_DESKTOP`) and each feature
uses that desktop's own tools:

| Feature | Hyprland | KDE Plasma |
|---|---|---|
| Window actions, per-app profiles, Wait for window | `hyprctl` | kdotool |
| Workspaces | Hyprland workspaces | virtual desktops |
| Toggle floating, scratchpad | yes | not available (Hyprland only) |
| On-screen popups | SwayOSD | Plasma's own popups |
| Do not disturb | dunst | Plasma's Do Not Disturb |
| Screenshots | grim + slurp | Spectacle |
| Lock screen | hyprlock | KDE's screen locker (`loginctl lock-session`) |
| Settings window at login | Hyprland autostart | KDE autostart (`~/.config/autostart`) |
| Hidden settings window | listed by your bar (PID file) | system tray icon |

## Every action
| Group | Actions |
|---|---|
| General | Open default browser · Open a website · Open file or folder · Launch an app (picked from installed apps) · Copy text to clipboard · Show a notification |
| Keyboard | Type text · Press keys, via ydotool: `+` presses keys together (`super+q`, `Super + Q`, `ctrl+shift+t`), spaces press them one after another (`Down Down Enter`) |
| Screenshot | Full screen · Select a region (saved to `~/Pictures/Screenshots` and copied) |
| Window | Go to workspace N · Move window to workspace N · Next / previous workspace · Close window · Toggle fullscreen · Focus a window (by class) · Toggle floating (Hyprland) · Show / hide scratchpad (Hyprland) |
| OBS | Start / stop / toggle / pause / resume recording · Start / stop / toggle streaming · Start / stop streaming AND recording · Switch scene · Show / hide a source in a scene · Mute / unmute an audio source · Turn a filter on / off (voice changer, camera effect, …) · Toggle virtual camera · Toggle replay buffer · Save replay buffer |
| Media | Play / pause · Stop · Next / previous track · Volume up / down · Set volume to N% · Mute speakers · Mute microphone |
| Per-app audio | App volume up / down · Set app volume to N% · Mute / unmute an app (e.g. Spotify, Firefox) |
| Audio output | Switch audio output to a device · Next audio output (cycles through devices) |
| System | Do not disturb on / off · Lock screen · Sleep · Shut down · Restart |
| Mode | Toggle a mode · Turn a mode on · Turn a mode off · If a mode is on… (if / otherwise) |
| Advanced | Macro · Run Python (sandboxed) |

On a Press slot, volume up/down (system and per-app) and next/previous workspace
repeat while the key is held.

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

**Sleep / Shut down / Restart need confirming:** the first trigger only shows "Press
again to sleep" (or "Hold again" / "Double-tap again", matching the key); repeating it
within 5 seconds confirms. Repeats under 0.4 s count as key bounce. They can't be
used in macros or run from the window's Test button.

## Per key: Press, Hold, Double tap
Every key (except `000`) has three slots. A key with only a Press action fires
instantly; once Hold or Double tap is set, Press fires on release instead.

**Hold** fires its action once after about half a second. If its **"Rapid-fire
after holding 2 s"** switch is on, keeping the key held 2 more seconds makes it fire
repeatedly until you let go. The switch is on by default for actions that are safe
to repeat (volume and app volume, workspaces, next/previous track, Press keys, Type
text) and off for the rest; Sleep / Shut down / Restart never rapid-fire. A slow
action (e.g. a macro) finishes before the next round starts, so runs never pile up.

## Layer key and profiles
- **Layer key** (Settings): hold it and every other key uses its "Layer" actions,
  doubling the number of actions.
- **Profiles** (top left): different actions while a given app is focused,
  matched by window class (e.g. `kitty`, `org.kde.dolphin`). Anything a profile
  leaves unset uses Default.
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
Window steps use `hyprctl` on Hyprland and kdotool on KDE Plasma.

## Feedback
- On-screen confirmations (SwayOSD on Hyprland, Plasma's popups on KDE), e.g.
  "● Recording", "Stream ended", "Scene: Gaming". Can be turned off in Settings.
- The window shows whether the service is running and the numpad is connected
  (with a "Start service" button if it isn't), lights up keys as you press them,
  and has a **learn mode** (keyboard icon): press a numpad key to select it in the
  window without running its action.
- Errors from an action show as a desktop notification.

## Starting at login
- The background service starts at login (systemd, `default.target`).
- The settings window starts hidden at login (`numpad-control --hidden`), so it
  opens instantly from the launcher. Closing it only hides it; Ctrl+Q quits it.
  - **KDE Plasma:** started by `~/.config/autostart/numpad-control.desktop`
    (installed by `install.sh`), and shown as a **system tray icon**: click it to
    open the settings; right-click for Open settings / Quit.
  - **Hyprland:** add `numpad-control --hidden` to your Hyprland autostart. No tray
    icon is shown there; instead it writes `$XDG_RUNTIME_DIR/numpad-control-window.pid`
    while running, so a bar module can list it as a hidden app.

## Install
One command (as your normal user; it asks for your password when it needs sudo):

    curl -fsSL https://raw.githubusercontent.com/youssefahmed2017/numpad-control/main/install.sh | bash

It:
1. installs the system packages (pacman, apt or dnf): Python, GTK 4, libadwaita,
   python-gobject, git, ydotool, playerctl, PipeWire tools, wl-clipboard, plus the
   extras for each desktop it finds (Hyprland: SwayOSD, grim, slurp, dunst, hyprlock;
   KDE Plasma: Spectacle, and kdotool from the AUR via yay/paru)
2. clones the code to `~/numpad-control` (or updates it if it's already there)
3. creates the Python environment (`.venv`, with `requirements.txt`)
4. asks you to press a key on your numpad, to find it
5. installs a udev rule so you can read that numpad (and only that one)
6. installs and starts the background service (and ydotool's service)
7. adds the `numpad-control` command, the app-menu entry and KDE autostart
8. optionally installs the boot/sleep re-detect fix (below)

Running `./install.sh` again from the clone updates everything. Options:
`--dir PATH` (install somewhere else), `--no-deps` (skip system packages),
`--yes` (no questions), `--dry-run` (only show what it would change).

Then open **Numpad Control** from your launcher, click a key, pick an action, Save.
On Hyprland, add `~/.local/bin/numpad-control --hidden` to your autostart to have the
settings window start hidden at login.

### Numpads that need replugging after boot or sleep
Some cheap numpads aren't detected at boot (the kernel logs `device descriptor
read/64, error -71`) or go silent after waking from sleep until they're replugged.
`install-usb-fix.sh` (offered by the installer) adds a "virtual replug": at boot, if
the numpad is missing, its USB port is switched off and on (up to 3 times); after
sleep, the numpad is re-detected. It installs `/usr/local/bin/numpad-control-usb-kick`,
`numpad-control-usb.service` and a systemd sleep hook, and remembers the numpad's port
in `/etc/numpad-control/usb.conf`. (New; not yet confirmed on real hardware.)

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

## Code layout
- `numpadctl/daemon.py`: the background service: key timing (press / hold / double
  tap, repeat, rapid-fire, layer key, `000`), profiles, and the link to the window
- `numpadctl/actions.py`: every action, plus macros and modes logic
- `numpadctl/gui.py`: the settings window; `tray.py`: KDE tray icon
- `numpadctl/desktop.py`: desktop-specific tools (Hyprland vs KDE Plasma)
- `numpadctl/obs.py`, `audio.py`, `modes.py`, `sandbox.py`, `config.py`
- `numpadctl/platform/`: everything that differs between operating systems, so a
  future Windows version only has to add its own versions of these:
  - `paths.py`: file locations and file locking
  - `ipc.py`: the service ↔ window connection
  - `numpad_input.py`: reading the numpad; the service itself only sees key names
    like `"5"`, `"Enter"`, `"000"`. Linux: `linux_numpad.py` (evdev). Windows:
    `windows_numpad.py`, using the [Interception](https://github.com/oblitum/Interception)
    driver to capture only the numpad, even next to a keyboard with its own number pad
    (tested on a real Windows PC)
  - `system.py`: system actions: opening apps, URLs and files, clipboard,
    notifications, typing and key presses, media, volume, power. Linux:
    `linux_system.py`; Windows: `windows_system.py` (SendInput, Windows' own volume
    popup, toast notifications; no extra packages).
    Apps opened from the numpad get their own systemd scope, so they don't count as
    part of the service. "Press keys" stores key names (`LEFTMETA`, `Q`), which each
    OS turns into its own key codes.

  `desktop.py` (Hyprland / KDE), `audio.py` (PipeWire), `sandbox.py` and `tray.py`
  are still Linux-only and sit next to the shared code.

## Tests
    .venv/bin/python -m unittest discover -s tests -t .

## Plans
- A Windows version (with one Qt settings window for both systems) is planned
  for later. It will read the numpad through the Interception driver, so it can
  tell an external numpad apart from a main keyboard that has its own number pad.
  [`tools/windows-poc/`](tools/windows-poc/) has the tests for a Windows PC. Working
  so far: reading the numpad, and the background service with most actions (no
  settings window yet; it's configured by editing the settings file). Not on Windows
  yet: window/workspace actions, per-app profiles, per-app audio, microphone mute,
  screenshots, Run Python, the tray icon and the settings window.
