# Changelog

All notable changes to NumpadControl. The format follows [Keep a Changelog](https://keepachangelog.com), and the
versions are `major.minor.patch`. The longer write-ups of each release are in [docs/updates.md](docs/updates.md);
what is planned is in [ROADMAP.md](ROADMAP.md). Dates are the day the release was made.

## [Unreleased]

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

[Unreleased]: https://github.com/youssefahmed2017/numpad-control/compare/v1.0.0...HEAD
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
