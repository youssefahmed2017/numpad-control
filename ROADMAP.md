# Roadmap

What is planned for NumpadControl, and what it is waiting on. There are no dates: this is a one-person project, and some of
this depends on other people (reviewers, a certificate authority). What already shipped is in the
[changelog](CHANGELOG.md). The same list is on the website: <https://numpad.ahmedabdou.net/roadmap.html>.

Something missing, or something you need first? [Open an issue](https://github.com/youssefahmed2017/numpad-control/issues).

## Waiting on someone else

- **winget.** The package `YoussefAhmed.NumpadControl` is submitted
  ([microsoft/winget-pkgs#472365](https://github.com/microsoft/winget-pkgs/pull/472365)) and is waiting for a moderator.
  After it is merged, `winget install YoussefAhmed.NumpadControl` works, and every later release is submitted
  automatically (the release workflow already has the step; it needs a token in the repository's secrets).
- **A code-signed Windows installer.** The application to SignPath Foundation (free signing for open source) is pending.
  Until then Windows SmartScreen may warn about the installer; releases themselves are already signed with the author's
  own key, which the updater checks. The plan for it is on the [code signing page](https://numpad.ahmedabdou.net/code-signing.html).

## Next

- **The AUR package updates itself on each release.** The workflow step exists; it needs the maintainer's AUR key in the
  repository's secrets.
- **A fix for the Windows keyboard hook at exit.** The Windows test run on CI crashes when Windows unloads the hook DLL at
  the very end, after every test has passed (the run is ended without that step to work around it). It has not been seen
  in normal use, but it deserves a real fix, and that needs a Windows machine.
- **Discord actions:** mute, deafen and push-to-talk on real keys.

## Later, maybe

- **Other Wayland compositors** (the window and workspace actions need a backend for each desktop; Hyprland, KDE, X11
  desktops and GNOME have one today).
- **macOS,** after Windows and Linux are polished.

## Known limits (not planned to change soon)

- **GNOME on Wayland** does not let programs read the focused window, so per-app profiles, Focus a window and Force-quit
  are not possible there; the other window actions go through GNOME's own shortcuts.
- **32-bit programs and programs running as administrator** do not load the Windows keyboard hook, so the numpad's keys still
  type there (its actions still run). NumLock on the numpad still switches NumLock.
- **Games with strict anti-cheat:** NumpadControl lets go of the numpad completely while such a game runs. It does not
  promise anything beyond that.
- **Window frames:** the settings window and its dialogs sit in the desktop's own window frame, so their outer corners
  and shadow are the desktop's, not the website's. Everything inside the frame uses the website's sizes.
- **Windows is the newer side:** its installer and some actions are tested less than Linux's.
- **Some cheap numpads drop off USB** on a weak port or cable; the kernel log shows it, and another port helps.
