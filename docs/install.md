# Installing in detail

Part of the [NumpadControl docs](../README.md).

## Install in detail

**Install size.** pip installs all of Qt (about 250 MB), but the settings window uses four of its modules.
After installing, `setup.sh` and `setup.ps1` delete the rest (QML, translations, developer tools, plugins for
things NumpadControl never does) with `tools/prune-qt.py`, then open the real window offscreen
(`tools/qt_check.py`) to prove it still works; if that fails they put the full Qt back. Qt ends up around
90 MB on Linux and 45 MB on Windows. `--no-prune` (`setup.sh`) or `-NoPrune` (`setup.ps1`) keeps all of it, and
the Windows installer is slimmed the same way (it is 32 MB instead of 69 MB). Don't run the test suite in a pruned
copy: a few tests use Qt's test module, which the app doesn't need.
### Linux
One command (as your normal user; it asks for your password when it needs sudo):

    curl -fsSL https://raw.githubusercontent.com/youssefahmed2017/numpad-control/main/setup.sh | bash

It shows the NumpadControl logo and a menu: **[1] Install, [2] Uninstall, [3] Reinstall /
Update, [0] Quit**. (`--install`, `--uninstall` and `--update` skip the menu.) Install:
1. installs the system packages (pacman, apt or dnf): Python, python-gobject, git, ydotool, playerctl, PipeWire tools, wl-clipboard, plus the
   extras for each desktop it finds (Hyprland: SwayOSD, grim, slurp, dunst, hyprlock;
   KDE Plasma: Spectacle, and kdotool from the AUR via yay/paru)
   On **Ubuntu** (tested on 24.04 LTS, Python 3.12, in a container: the install path and the whole test suite pass) it
   also installs `python3-evdev` (so nothing has to be compiled) and the xcb libraries Qt's X11 backend loads, which
   the key map overlay needs. Ubuntu's `ydotool` is the old 0.1.8: if **Type text** or **Press keys** doesn't work,
   install ydotool 1.0 or newer and make sure you can write to `/dev/uinput`.
2. clones the code to `~/numpad-control` (or updates it if it's already there)
3. creates the Python environment (`.venv`, with `requirements.txt`)
4. asks you to press a key on your numpad, to find it
5. installs a udev rule so you can read that numpad (and only that one)
6. installs and starts the background service (and ydotool's service)
7. adds the `numpad-control` command, the app-menu entry and KDE autostart
8. optionally installs the boot/sleep re-detect fix (below)

Running `./setup.sh` again from the clone and choosing Update updates everything (the menu entry and icon
are replaced whole (never deleted or left half-written), and only when they changed, so a running launcher keeps showing the app; the
system permission rule is kept when unchanged, so an update does not ask for sudo).
Uninstall removes the service, launcher, menu entry and permission rules, and asks
before deleting your settings. Options:
`--dir PATH` (install somewhere else), `--no-deps` (skip system packages),
`--yes` (no questions), `--dry-run` (only show what it would change).

Then open **NumpadControl** from your launcher, click a key, pick an action, Save.
On Hyprland, add `~/.local/bin/numpad-control --hidden` to your autostart to have the
settings window start hidden at login.

### Windows
Paste this into PowerShell (as your normal user):

    irm https://raw.githubusercontent.com/youssefahmed2017/numpad-control/main/setup.ps1 | iex

It installs Python if needed (winget), downloads NumpadControl (git, or a zip if git
isn't installed), creates the Python environment, adds **NumpadControl** and
**NumpadControl Settings** to the Start menu, and starts it at login with a tray
icon. No driver, no administrator rights and no restart are needed. It shows the same
menu (**[1] Install, [2] Uninstall, [3] Reinstall / Update, [0] Quit**); choose Update
to update everything.
Options (set them before pasting): `$env:NUMPAD_ACTION = "install"` (or `"uninstall"`,
`"update"`) skips the menu; `$env:NUMPAD_DRYRUN = "1"` only shows what it
would do; `$env:NUMPAD_NOAUTOSTART = "1"`; `$env:NUMPAD_UNINSTALL = "1"` removes the
shortcuts and autostart (settings stay); `$env:NUMPAD_INTERCEPTION = "1"` reads the
numpad through the [Interception](https://github.com/oblitum/Interception) driver
instead, the old way (an administrator prompt and a restart; some games' anti-cheat
blocks that driver). From a copy of the project:
`powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun`.

### Numpads that need replugging after boot or sleep
Some cheap numpads aren't detected at boot (the kernel logs `device descriptor
read/64, error -71`) or go silent after waking from sleep until they're replugged.

`install-usb-fix.sh` (offered by the installer) tries a "virtual replug": at boot, if the numpad is
missing, its USB port is switched off and on in software (up to 3 times); after sleep, the numpad is
re-detected. It installs `/usr/local/bin/numpad-control-usb-kick`, `numpad-control-usb.service` and a systemd
sleep hook, and remembers the numpad's port in `/etc/numpad-control/usb.conf`.

**It doesn't help every numpad, and it didn't help the one it was written for.** A software switch isn't a real
unplug. On the author's PC (HP EliteDesk, numpad `c0f4:05f5`, an Intel xHCI controller) the kernel failed at
every boot, the fix ran correctly (its three tries are in the journal) and the numpad was still not detected.
Resetting the whole USB controller didn't help either, and neither did a full shutdown and power-on. Only
physically unplugging and replugging the numpad worked, after which NumpadControl picked it up by itself. So if
you see `-71` errors at every boot, expect the same, and don't count on the fix. (Whether it helps after sleep is
untested.)

What can help instead, roughly in this order:
- **Another USB port**, ideally on the back of the PC.
- **A cheap USB 2.0 hub** between the PC and the numpad. A hub sets up low-speed devices itself and hands the PC
  a normal "device plugged in" event.
- **BIOS settings**: turn off Fast Boot, look at the legacy USB / xHCI hand-off option, and at any option that
  controls USB power while the PC is off (the names differ by maker). Unplugging the PC's power cable for ten
  seconds shows whether the ports stay powered while it is off.
- A different cable or another numpad of the same model, in case the one you have is faulty.

## Starting at login
- The background service starts at login (systemd, `default.target`).
- The settings window starts hidden at login (`numpad-control --hidden`), so it
  opens instantly from the launcher. Closing it only hides it; Ctrl+Q quits it.
  - **KDE Plasma, XFCE and other desktops with a tray** (Cinnamon, MATE, LXQt, LXDE, Budgie...): started by
    `~/.config/autostart/numpad-control.desktop` (installed by `setup.sh`), and shown as a **system tray icon**:
    click it to open the settings; right-click for Open settings / Quit.
  - **Hyprland:** add `numpad-control --hidden` to your Hyprland autostart. No tray
    icon is shown there; instead it writes `$XDG_RUNTIME_DIR/numpad-control-window.pid`
    while running, so a bar module can list it as a hidden app.
