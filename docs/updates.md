# Updates and release notes

Part of the [NumpadControl docs](../README.md).

## Updates
NumpadControl updates itself: once a day the service asks GitHub for the latest
release, and if it's newer, installs it the way it was installed (git: fast-forward to the
release; zip: swap the folders, keeping `.venv`), updates the Python packages and restarts,
with a notification. On Windows (installed with the installer) the app downloads the newer
installer, checks it against the signature and runs it silently: the installer closes
NumpadControl, replaces the files (a plain file swap can't replace ones that are in use) and starts
it again, and your settings stay. Copies from the AUR are updated by `yay -Syu` instead. Only
releases are installed, never unfinished work. A copy with local
changes isn't touched. Settings: `"updates"`: `"auto"` (default), `"notify"` (only tell
you) or `"off"`; `python -m numpadctl update` checks right away.

**Releases are signed.** The updater installs only releases signed with the author's offline
key (its public half is in `numpadctl/release_key.py`): the signature names the exact commit
(git copies), the exact `source.zip` hash (zip copies) or the exact Windows installer's hash
and is checked before anything on disk changes or anything is run. A tag moved after signing, a swapped download or an unsigned release is refused
with the reason. [`SECURITY.md`](../SECURITY.md) says what that does and doesn't protect.

To publish a release: set `__version__` in `numpadctl/__init__.py`, commit, push the
matching tag (`git tag v0.3.0 && git push --tags`; the Release workflow makes the release and
the Windows installer), then **sign it on your own computer**:
`tools/sign-release sign v0.3.0 --key <your key file>`. Wait for the Release workflow to finish first
(it attaches the Windows installer). The tool checks the tag is the same commit on GitHub, builds
`source.zip` from that commit, hashes the installer CI built, shows you what it will sign, and
uploads `source.zip` and `release.sig` to the release. Until then, installed copies see the release
but refuse to install it.

**1.0.0:** a control deck that looks and feels like a finished app.
- **More desktops (Linux):** XFCE and other X11 desktops, and GNOME on Wayland (through GNOME's own shortcuts),
  now work next to Hyprland and KDE Plasma, with volume popups on each. See [Linux desktops](linux-details.md).
- **Stickers and sticker packs:** a picture for each key, on the pad and on the key map; give the whole pad its
  pictures from a zip in one step. **Action icon packs** restyle every action's icon the same way.
- **Profile library:** browse shared profiles from the profile menu; a download is checked against its checksum.
- **Key map overlay, both halves ([#12](https://github.com/youssefahmed2017/numpad-control/issues/12)):** it opens
  with Layer + Enter (configurable) instead of popping up whenever the layer key is held, and shows the normal keys
  next to the layer keys. *Holding the layer key* in Settings brings back the old behaviour.
- **Icons for actions on keys** (Settings → Appearance): every action has one, on the keys and on the key map,
  e.g. the OBS logo with a red dot for Start recording; your stickers still win.
- **Your own templates in Python**, written and tested inside the app (Profile ⋯ → Add a starter preset… →
  New template…): an editor with every action to insert and "Try it"; import and delete templates there too.
  They fill a profile's keys with loops, macros and if/otherwise, run in a limited process and are checked like
  a profile file.
- **Appearance tab in Settings:** Material 3 on/off, shapes, your own colours (any colour, your wallpaper,
  pywal, Material Theme Builder / matugen theme files, followed live), scheme styles, motion speed or none,
  ripples, window transparency, any font and text size; export your theme. Needs the new `materialyoucolor`
  package (the installers add it).
- **Looks more like a Google app:** Material Symbols icons (Google's own, bundled, 12 KB) instead of text symbols;
  buttons are full pills that squeeze when pressed, like Material 3 Expressive; on/off settings are Material 3
  switches; the action fields are Material drop-down fields; the "⋯" buttons are round icon buttons; the
  selected Normal / Layer segment has a tick; the app bar is flat.

**0.3.1:** share profiles, a different key layout, and honest USB advice.
- **Import and export profiles:** *Profile ⋯ → Export profile…* saves one profile (keys, actions and window match,
  nothing else) as a small file; *Import profile…* adds one you were sent. The file is checked strictly, and you
  see what it will do (with ⚠ on actions that run programs, press keys or power off) before anything is added.
- **Numpad layout:** *Settings → Numpad layout* draws Backspace below `+` for numpads that have it there. Only the
  picture changes; what you set on each key stays.
- **USB numpads that aren't detected at boot:** the README and Diagnostics now say plainly that the "virtual replug"
  doesn't revive every numpad (it didn't on the author's PC) and what helps instead: another port, a USB 2.0 hub,
  BIOS settings.
- **Windows installer:** its keyboard hook DLL is compiled from `numpadhook.c` in the build, and the Setup carries a
  product name and company in its file properties; the site has a Code signing policy page (the installer isn't signed yet).

**0.3.0:** NumpadControl again, and a much smaller install.
- **Name:** NumpadPilot (the name from 0.2.0 to 0.2.7) is NumpadControl again, because another project already used
  NumpadPilot. The service, the `numpad-control` command and your settings never changed, so nothing moves. Installed
  copies update as usual (releases are still signed under the old id, and the Windows Setup is also attached under its old
  file name, so copies older than 0.3.0 can still update). On Windows the Start-menu entries and start-at-login entry
  take the new name; on Arch the package is `numpad-control` and replaces `numpad-pilot`. The GitHub address is now
  `youssefahmed2017/numpad-control` (old links redirect; the old website address no longer works).
- **Smaller install:** Qt is cut down to the parts the window uses: about 94 MB on Linux and 45 MB on Windows (it
  was about 250 MB), and the Windows installer is 32 MB instead of 69 MB. `setup.sh` and `setup.ps1` do it after pip,
  check that the window still opens, and put the full Qt back if it doesn't; `--no-prune` / `-NoPrune` keep all of it.
- **Checkboxes** draw their tick (the box fills, then the tick is traced; un-ticking rubs it out faster).
- **Windows taskbar:** the settings window shows NumpadControl's icon, not Python's.
- New banner pictures with the new name.

**0.2.7:** smoother motion, Windows updates and a nicer installer start.
- **Motion:** every animation now uses Material 3's easing curves, durations and springs (buttons squeeze and bounce
  back, popups, fades and scrolling follow the same tokens), and messages appear in a real Material 3 snackbar.
- **Windows updates:** installed Windows copies update themselves again. They download the newer Setup, check its
  SHA-256 against the signed release, run it silently, and NumpadControl starts again with your settings. Copies
  installed before this release need one manual install first.
- **Installers:** `setup.sh` and `setup.ps1` draw the logo from `assets/banner.txt` with a light sweep and sparkles
  (`NUMPAD_NO_ANIM=1` turns the effect off).

**0.2.6:** security and profile sets.
- **Signed updates:** installed copies update only to releases signed with the author's offline key, checked
  before anything changes (see [SECURITY.md](../SECURITY.md)). Older copies install this one on trust, then
  are protected from here on.
- **Profile sets:** whole separate setups (Coding, Streaming, Gaming) you switch between with the new
  Switch / Next / Previous profile set actions. Old settings files become one set called "Default".
- **Hardening found by attacking the project:** Run Python can no longer flood the service with output or
  actions; the service's connection survives floods and malformed messages; notification text and URLs
  can't be read as options; release tags are checked strictly.
- **Installers:** `setup.sh` / `setup.ps1` install the newest release, not unfinished work, and `setup.sh`
  no longer runs this folder's Python as root.
- **Extra keyboards:** Allow access asks first, and removing a keyboard offers to take the permission away.

**0.2.5:** a lot of new keys, mostly Linux:
- **Extra keyboards:** a whole second keyboard can be an extra pad (Ctrl+Alt+Esc gives it back); the settings
  window draws it.
- **Key map overlay (Ghost HUD):** hold the layer key and a see-through copy of the numpad shows what each key does.
- **Privacy panic** (mute, pause and hide everything at once) and **Undo privacy panic**, which puts back exactly
  what it changed; **Force-quit the focused window** (press twice).
- **Soundboard** (Play a sound, Stop all sounds), **Turbo** (repeat a Press action while held, up to 60 a second)
  and a **voice changer** (EasyEffects voices on your microphone, one key; Linux).
- **OBS:** pause now checks that OBS really paused (some recording settings can't), and refusals read plainly.
- **Tools:** `tools/mic-level` (a live microphone meter), `tools/voice-demo` (hear each voice without a microphone),
  and end-to-end tests against a real, private OBS.
- **Fixes:** the voice key waits for EasyEffects to finish starting; the overlay never outlives its service; an
  update no longer deletes the launcher entry.

**0.2.4:** a welcome tour on first launch (find the numpad, pick a starting point, press a key to
see it register), also in Tools → Welcome tour; the Linux launcher entry now matches "Numpad Control"
and shows its logo (including in hyprlauncher); updating with `setup.sh` no longer asks for sudo.

**0.2.3:** the settings window ships its own fonts (Google Sans for text, JetBrains Mono for
code and Diagnostics, in [`assets/fonts/`](../assets/fonts/)), so Windows no longer falls back to
pixelated system fonts (Courier and friends).

**0.2.2:** a nicer Windows installer (artwork, light and dark), `setup.sh` / `setup.ps1` with an
Install / Uninstall / Update menu, one Pause / resume recording key, press a key to select it
and a searchable action picker, and an AUR recipe.

**0.2.0:** renamed to NumpadPilot (GPL-3.0, settings window included); a Material You
settings window (ripples, morphing buttons, colour themes); Learn any key (keys beyond
the standard numpad); a Key tester and Diagnostics; starter presets; Windows fixes (the
`000` key, and dropping out until replugged); the new icon and banner.
