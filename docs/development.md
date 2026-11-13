# Development

Part of the [NumpadControl docs](../README.md).

## Code layout
- `numpadctl/daemon.py`: the background service: key timing (press / hold / double
  tap, repeat, rapid-fire, layer key, `000`), profiles, and the link to the window
- `numpadctl/keys.py`: key ids and names for the standard keys, learned extra keys and the keys of extra keyboards (`hp:KEY_A`)
- `numpadctl_ui/motion.py`: Material 3 motion for the whole window: the easing curves, the duration steps and the springs
  (M3 Expressive), as `Tween` and `Spring`; every animation takes its feel from here
- `numpadctl_ui/snackbar.py`: the Material 3 snackbar that confirms what you did (arrives with emphasized-decelerate, 4 px
  corners, inverse surface); `MainWindow.toast()` shows one
- `numpadctl_ui/hud.py`: the key map overlay, a separate small process the service starts (`Daemon.manage_hud`)
- `numpadctl/devices.py`: finds the keyboards that can be added as extra pads, and installs the udev rule that lets you read one (Linux)
- `numpadctl/actions.py`: every action, plus macros and modes logic
- `numpadctl_ui/`: the settings window and its dialogs (Qt for Python, Material 3 look;
  `tools/generate_m3_palettes.py` makes its colour palettes)
- `numpadctl/gui.py`: opens the settings: the window (`numpadctl_ui`) if Qt for Python
  is installed, otherwise the settings file. `numpadctl/ui_common.py` holds what any
  settings window needs (the link to the service, the key layout, action names): the
  interface the window builds on.
- `numpadctl/desktop.py`: desktop-specific tools (Hyprland, KDE Plasma, GNOME, X11); `numpadctl/platform/x11_desktop.py` and `gnome_desktop.py` are the last two
- `numpadctl/release_key.py`: the public key releases must be signed with; `tools/sign-release` makes the key and signs releases
- `numpadctl/profile_sets.py`: which profile set is active (a small state file, like `modes.py`)
- `numpadctl/stickers.py`: key pictures: their names, where they live, which one a profile shows (`numpadctl_ui/sticker_image.py` makes them from a picture file)
- `numpadctl/sticker_packs.py`: reads a sticker pack (a zip or folder of key pictures) strictly; `tools/make-sticker-pack.py` checks and zips one
- `numpadctl/library.py`: the profile library (Browse library…): reads its index and fetches a profile to import
- `numpadctl/obs.py`, `audio.py`, `modes.py`, `sandbox.py`, `config.py`
- `numpadctl/platform/`: everything that differs between operating systems, so a
  future Windows version only has to add its own versions of these:
  - `paths.py`: file locations and file locking
  - `ipc.py`: the service ↔ window connection
  - `numpad_input.py`: reading the numpad; the service itself only sees key names
    like `"5"`, `"Enter"`, `"000"`. Linux: `linux_numpad.py` (evdev). Windows:
    `windows_rawinput.py`, with no driver: Raw Input tells the service about every key
    and which keyboard it came from, and a small hook DLL (`numpadhook.dll`, built from
    `numpadhook/numpadhook.c`) stops the numpad's keys from reaching apps, so only the
    numpad is captured, even next to a keyboard with its own number pad. The older
    `windows_numpad.py` uses the [Interception](https://github.com/oblitum/Interception)
    driver instead (`NUMPADCTL_WINDOWS_BACKEND=interception`).
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

GitHub runs them on Linux and Windows for every push and pull request
(`.github/workflows/tests.yml`). Pushing a tag such as `v0.2.0` publishes a GitHub
release with generated notes (`release.yml`).

**End-to-end tests with a real OBS** (Linux; not part of the normal run, and not on GitHub):

    .venv/bin/python -m unittest tests.e2e_obs -v      # the OBS actions against a real OBS
    .venv/bin/python -m unittest tests.e2e_voice -v    # the voice changer: EasyEffects + OBS, pitch measured

`e2e_obs` starts its own OBS in a headless compositor (`cage`), with its own empty config folder and its own
WebSocket port (4466), so your OBS, its scenes and settings are never touched and nothing appears on screen.
It switches scenes, shows and hides sources, mutes, toggles a filter, records, pauses, resumes and stops (and
checks the video file with `ffprobe`), saves a replay clip, and runs Privacy panic's OBS step. `e2e_voice` plays
a 440 Hz tone into a silent virtual microphone, lets EasyEffects change it with NumpadControl's voice keys,
records the result in OBS and measures the pitch (440 Hz normal, 349 Hz with a voice four semitones down). It
never uses your real microphone, refuses to run while EasyEffects is running, and puts back your default
microphone, EasyEffects and its preset file even if it fails. They need `obs`, `cage`, `ffmpeg`, `pw-play`,
`numpy` and (for the voice test) `easyeffects`; without them they skip.

## Plans
- A Windows version (with one Qt settings window for both systems) is planned
  for later. It reads the numpad with Raw Input and a keyboard hook DLL (no driver),
  so it can tell an external numpad apart from a main keyboard that has its own number
  pad. Known limits: 32-bit apps and apps running as administrator don't load the
  DLL, so the numpad's keys still type there (their actions still run), and NumLock on
  the numpad still switches NumLock.
  [`tools/windows-poc/`](../tools/windows-poc/) has the tests for a Windows PC.
  Working: reading the numpad, the background service, a tray app
  (`numpad-control.pyw`: Settings…, Edit settings file, Pause, Start at login, Show
  log, Quit), the same Qt settings window, and the actions: per-app profiles and
  Wait for window (by program name, e.g. `obs64`), Focus a window, Close window,
  Toggle fullscreen (maximize / restore on Windows), Next / previous desktop,
  per-app volume and mute, microphone mute, switching the audio output (Core Audio
  via pycaw), full-screen screenshots (region opens Windows' Snipping tool, which
  copies it), and Lock screen. Not on Windows: going to / moving windows to a
  numbered desktop, floating and the scratchpad (Hyprland only), Do not disturb,
  Run Python, and on-screen popups (notifications instead). Install with
  `setup.ps1` (see Install → Windows).

## Logo and brand files
The icon and banner are in [`assets/`](../assets/): `icon.svg`, PNGs from 16 to 512 px
(used by the settings window, the tray and the Linux launcher), `numpad-control.ico`
(Windows), `banner.png` and `social-preview.png` (1280x640, for GitHub's link preview).
`banner.txt` is the picture `setup.sh` and `setup.ps1` draw when they start (plain letters: `p` tile, `w` key,
`l` lettering; the header in the file says so), so the installers' logo can be edited as text.
The UI fonts (Google Sans, JetBrains Mono) and the icons (Material Symbols Rounded, Apache 2.0, cut down with
`tools/subset-icons.py`) are in `assets/fonts/`.
The website uses the same icon as its favicon and `site/img/og.png` as its link preview.
