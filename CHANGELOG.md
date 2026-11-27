# Changelog

All notable changes to NumpadControl. The format follows [Keep a Changelog](https://keepachangelog.com), and the
versions are `major.minor.patch`. The longer write-ups of each release are in [docs/updates.md](docs/updates.md);
what is planned is in [ROADMAP.md](ROADMAP.md). Dates are the day the release was made.

## [Unreleased]

### Added
- **Experimental low-level keyboard hook on Windows** (`"windows_blocking": "lowlevel"` in `config.json`, default `"dll"`).
  It keeps the numpad's keys from typing with a `WH_KEYBOARD_LL` hook in the service instead of the hook DLL, so nothing is
  loaded into other programs and 32-bit apps are covered. A key whose keyboard isn't known in time is never swallowed, and a
  hook Windows silently drops is put back. `python -m numpadctl.platform.windows_rawinput --ll-probe` measures a PC without
  blocking anything. Administrator apps are still not covered, and the games' step-aside list works the same in both modes.

## [1.0.3] - 2026-11-27

### Changed
- **Crash reports go to our own Issues page, with no GitHub account.** The crash dialog shows what would be sent and Yes
  sends it to numpad.ahmedabdou.net (`api/`, a small Vercel function with a Neon database). Each crash is listed once, with
  a count, on the new [Issues page](https://numpad.ahmedabdou.net/issues.html). Offline, the report waits and you are asked
  again at the next start. Your IP address is never stored.

- **A form for problems and ideas, no GitHub account needed.** The new [Issues page](https://numpad.ahmedabdou.net/issues.html) has a
  "Report a problem" form (a bug, an idea or a question; title and text are public, an optional contact line is private) and lists
  what people reported next to the crashes. Spam is held back by a hidden field, a minimum time on the page, a limit of 3 a
  hour and 2 links per report; the maintainer can hide or close a report.

- **Filters, closing and reopening on the Issues page.** Filter by Open / Closed / All, by type (bugs, ideas, questions,
  crashes) and by a search. The person who wrote a report can close and reopen it from the same browser (a private key
  kept in the browser, only its hash on the server). The maintainer has a "Maintainer" mode (the admin token, kept for the
  tab only) to set any item to open, closed, fixed (with the version), won't fix, duplicate or hidden, and to see the
  contact lines; hidden items are only visible there.

- **Pictures with a report.** The form takes up to 3 PNG, JPG, GIF or WEBP pictures of 4 MB each. They are checked by their real
  contents (not their name), kept under random names (`numpad.ahmedabdou.net/issues-attachments/<hash>.png`), and stay hidden
  until the maintainer approves them in Maintainer mode (which lists the waiting ones with Approve and Delete). Limits keep the
  database from filling: 20 MB a day per address, 30 waiting in total, 300 MB overall. No videos: a single upload can't be
  larger than about 4.5 MB on this host.
- **Maintainer mode stays on for 30 days** in the browser where you entered the token (it used to end when the tab closed);
  "Leave maintainer mode" ends it at once.

### Fixed
- **Crash reports no longer get lost.** Pressing Yes used to mark the crash as reported even if nothing was delivered
  (no browser running). Now a crash counts as reported only once the website confirmed it; otherwise it stays waiting,
  its text is saved in a `.report.txt` file next to the crash file, and you are asked again at the next start.
- **A slow notification daemon can no longer crash the service.** `notify-send` taking more than 5 seconds (for
  example for "Numpad not found") raised `TimeoutExpired` and took the service down. The notification is now skipped
  instead, in the service and in the Run Python sandbox.

## [1.0.2] - 2026-11-21

### Changed
- **Numpad keys while the settings window is in front:** a key still selects its key in the editor (so setting things up is
  safe), but pressing the same key again within 1.5 seconds now runs it. A hint in the top bar ("Keys select here: press
  twice to run") says what is going on while it is on, and a click on it makes keys run at once. Before, keys did nothing at
  all there, which looked exactly like a broken numpad in a demo. Learn mode and Pause still never run keys.
- The log says what happened to a key the window took: `key 1: selected in the settings window, not run: press it again
  within 1.5 s to run it`, `Learn mode is on ...` or `NumpadControl is paused`.

## [1.0.1] - 2026-11-20

### Added
- **A log file on every system** (Linux too, not only the journal), with the level in every line, cut at 1 MB. **Tools →
  Copy the log** puts the last 200 lines on the clipboard; Diagnostics shows the file's path and its last 50 lines.
- **Log lines that say what happened:** every press logs its result and how long it took (`key 1 tap: open_browser ->
  ok (12 ms)`), a failure adds a first clue when its error has none (timeout, permission, missing file, refused
  connection), a key that isn't on the pad is explained once, and an unbound key says which profile and layer it looked in.
- **A key the settings window or Pause takes is logged,** with the reason. Before, it was silent, which looks like a numpad that does nothing.
- **Debug level** (`NUMPADCTL_LOG=debug` or `"log_level": "debug"`): one line per raw key event, to tell a key that never
  arrived (hardware) from one the program ignored (settings).
- **A numpad that keeps dropping off USB** (3 times in 10 minutes, Linux) is called out in the log as a connection
  problem, with what to try.

### Changed
- **Top bar:** Settings and Save are Material 3 extended FABs, like Gmail's Compose button. They are flat at rest, a
  shadow grows in while the pointer is over them, and in a window narrower than 900 px they shrink to icon-only squares.
  Learn and Tools stay in the top bar, without the shadow.
- **Save changes? dialog:** Save and Don't save are FABs too (Cancel stays a text button).
- **Same sizes as the website:** buttons, fields (48 px tall), chips, menus, list rows, tabs and the three shadow levels
  use the numbers of BeerCSS, the library the website is built on. The app's dialogs have BeerCSS's 24 px of padding and
  are at least 320 px wide (the Settings dialog opens wider to fit). Body text has BeerCSS's letter spacing (not on the keys).

### Project and website
- The website is rebuilt on BeerCSS (served from the site itself, with a 5 KB icon font), with a Docs page, Install
  buttons and the demo video on the home page. It is served at numpad.ahmedabdou.net and at the GitHub Pages address.
- `tools/release` makes a release in one command (checks CI, tags, waits for the build, signs). The release workflow
  can submit the winget update with Komac and update the AUR package when their secrets are set.
- The app's pictures in the README and on the Docs page are drawn by `tools/docs-screenshots.py` and refreshed by CI.

## [1.0.0] - 2026-11-19

### Added
- **More Linux desktops:** XFCE and other X11 desktops, and GNOME on Wayland (through GNOME's own shortcuts), next to
  Hyprland and KDE Plasma, with volume popups on each.
- **Stickers and sticker packs:** a picture for each key, on the pad and on the key map; a whole pad from one zip.
  **Action icon packs** restyle every action's icon the same way.
- **Profile library:** browse shared profiles from the profile menu; a download is checked against its checksum.
- **Your own templates in Python**, written and tried inside the app, that fill a profile's keys.
- **Appearance tab in Settings:** Material 3 on or off, shapes, your own colours (any colour, wallpaper, pywal, Material
  Theme Builder / matugen files), scheme styles, motion, ripples, window transparency, font and text size.
- **Icons for actions** on the keys and on the key map.

### Changed
- **Key map overlay** opens with Layer + Enter (configurable) and shows the normal keys next to the layer keys (#12).
- The settings window looks more like a Google app: Material Symbols icons, pill buttons that squeeze, Material 3
  switches and drop-down fields, a flat app bar.

### Fixed
- Save, Discard and Cancel buttons missing in message boxes on Windows: the Save prompt is now the app's own dialog.
- The key map overlay failed to start from a Windows startup (#13).
- A picture file stayed open after it was read, so Windows could not delete the temporary copy.

## [0.3.1] - 2026-11-03

### Added
- Import and export a single profile as a small file; the import is checked strictly and shows what it will do.
- **Numpad layout** setting (Backspace below `+`), for numpads that have it there.

### Changed
- Honest advice for USB numpads that are not detected at boot (the "virtual replug" does not revive every numpad).
- The Windows installer's keyboard hook DLL is built from source in CI, and the Setup carries a product name and company.

## [0.3.0] - 2026-11-03

### Changed
- **Renamed back to NumpadControl** (the name NumpadPilot was already taken). Settings, the service and the command are
  unchanged; installed copies update as usual.
- **Much smaller install:** about 94 MB on Linux and 45 MB on Windows (was about 250 MB); the Windows installer is 32 MB.
- Checkboxes draw their tick; the Windows taskbar shows NumpadControl's own icon.

## [0.2.7] - 2026-11-03

### Added
- Windows copies update themselves: the newer Setup is downloaded, checked against the signed release and run silently.

### Changed
- Every animation uses Material 3's easing curves, durations and springs; messages appear in a Material 3 snackbar.
- `setup.sh` and `setup.ps1` draw the logo with a light sweep.

## [0.2.6] - 2026-11-01

### Added
- **Signed updates:** installed copies update only to releases signed with the author's offline key.
- **Profile sets:** whole separate setups, with Switch / Next / Previous profile set actions.

### Security
- Hardening found by attacking the project: Run Python can no longer flood the service, the service survives malformed
  messages, notification text and URLs can't be read as options, release tags are checked strictly.
- The installers install the newest release, not unfinished work.

## [0.2.5] - 2026-10-31

### Added
- A whole second keyboard as an extra pad (Linux); the key map overlay (Ghost HUD); Privacy panic and its undo;
  Force-quit; a soundboard; Turbo (repeat while held); a voice changer (EasyEffects, Linux); tools for a live
  microphone meter and a voice demo.

### Changed
- OBS pause checks that OBS really paused, and refusals read plainly.

## [0.2.4] - 2026-10-29
### Added
- A welcome tour on first launch; the Linux launcher entry matches "Numpad Control" and shows its logo.

## [0.2.3] - 2026-10-29
### Changed
- The settings window ships its own fonts (Google Sans and JetBrains Mono), so Windows no longer falls back to pixelated ones.

## [0.2.2] - 2026-10-29
### Added
- A nicer Windows installer (light and dark artwork), a menu in `setup.sh` / `setup.ps1`, a searchable action picker,
  one Pause / resume recording key, press-a-key to select it, and an AUR recipe.

## [0.2.1] - 2026-10-29
### Added
- The Windows installer (for winget), built and smoke-tested in CI, and the AUR package.

## [0.2.0] - 2026-10-29
### Changed
- Renamed to NumpadPilot, under the GPL-3.0 with the settings window included; a Material You settings window.
### Added
- Learn any key, a Key tester and Diagnostics, starter presets, and Windows fixes (the `000` key, dropping out until replugged).

## [0.1.0] - 2026-10-27
- First release.

[Unreleased]: https://github.com/youssefahmed2017/numpad-control/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/youssefahmed2017/numpad-control/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/youssefahmed2017/numpad-control/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/youssefahmed2017/numpad-control/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/youssefahmed2017/numpad-control/compare/v0.3.1...v1.0.0
[0.3.1]: https://github.com/youssefahmed2017/numpad-control/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.7...v0.3.0
[0.2.7]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/youssefahmed2017/numpad-control/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/youssefahmed2017/numpad-control/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/youssefahmed2017/numpad-control/releases/tag/v0.1.0
