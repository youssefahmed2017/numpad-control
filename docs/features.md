# Features and actions

Part of the [NumpadControl docs](../README.md).

## Finding your way around
- **Press a key to select it.** While the settings window is in front, pressing a key on
  the numpad selects it in the editor instead of running its action (so you can't fire
  "Shut down" by accident while setting it up). Turn this off under *Tools ▾ → Select a
  key when I press it*. The moment the window isn't in front, the keys work as usual.
- **Search the actions.** Click an action and type: "mute" finds the microphone, the
  speakers and OBS, "live" finds the streaming actions. Each one has a one-line
  description, and the ones you used last are listed first under *Recently used*.
- **A different key arrangement.** Some numpads put Backspace below `+` instead of at the top right. Pick
  yours under *Settings → Numpad layout*: the window and the key map are drawn that way. Only the picture
  changes; a key keeps the name the numpad sends, so what you set on Backspace stays on Backspace. (In
  `config.json` it is `"numpad_layout": "backspace_below"`; the default is `"standard"`.)
- **First launch tour.** A new install opens a 3-step welcome: it finds your numpad, lets you
  pick a starting point (streaming, media, everyday shortcuts or empty) and has you press a
  key to see it register. Open it again from *Tools ▾ → Welcome tour*.
- **Find it in your launcher.** The menu entry answers to "NumpadControl", "Numpad Control", its old name "NumpadPilot", and "numpad". Its icon is installed in
  your icon theme (`~/.local/share/icons/hicolor`), so launchers that ignore file paths show it too. (The
  setup also adds the theme's `index.theme` there if missing: hyprlauncher skips icon folders without one.)

## How it works
- A **background service** (systemd user service) reads the numpad directly with
  evdev and grabs it, so its keys only trigger actions and never type digits.
  The `000` key (which sends three 0s in a burst) is detected as its own key.
- The **settings window**, or you in a text editor, edits
  `~/.config/numpad-control/config.json`. The service reloads it automatically after
  Save.
- The service fetches the desktop's display variables on every key press, so
  apps open correctly even if it started before the desktop at boot, and it
  switches between the Hyprland, KDE and X11 tools when you log out of one desktop and
  into another (no restart needed).

## Every action
| Group | Actions |
|---|---|
| General | Open default browser · Open a website · Open file or folder · Launch an app (picked from installed apps) · Copy text to clipboard · Show a notification |
| Keyboard | Type text · Press keys, via ydotool: `+` presses keys together (`super+q`, `Super + Q`, `ctrl+shift+t`), spaces press them one after another (`Down Down Enter`) |
| Screenshot | Full screen · Select a region (saved to `~/Pictures/Screenshots` and copied) |
| Window | Go to workspace N · Move window to workspace N · Next / previous workspace · Close window · Toggle fullscreen · Focus a window (by class) · Toggle floating (Hyprland) · Show / hide scratchpad (Hyprland) · Force-quit the focused window (press twice) |
| OBS | Start / stop / toggle recording · Pause / resume recording (one key, flips each press; separate Pause and Resume too) · Start / stop / toggle streaming · Start / stop streaming AND recording · Switch scene · Show / hide a source in a scene · Mute / unmute an audio source · Turn a filter on / off (voice changer, camera effect, …) · Toggle virtual camera · Toggle replay buffer · Save replay buffer |
| Media | Play / pause · Stop · Next / previous track · Volume up / down · Set volume to N% · Mute speakers · Mute microphone · Play a sound (soundboard) · Stop all sounds |
| Voice | Voice changer on / off · Use a voice · Back to normal (EasyEffects, Linux) |
| Per-app audio | App volume up / down · Set app volume to N% · Mute / unmute an app (e.g. Spotify, Firefox) |
| Audio output | Switch audio output to a device · Next audio output (cycles through devices) |
| System | Do not disturb on / off · Lock screen · Privacy panic · Undo privacy panic · Sleep · Shut down · Restart |
| Profile set | Switch to a profile set · Next / previous profile set |
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

**Voice changer** (Linux, needs [EasyEffects](https://github.com/wwmm/easyeffects); Arch: `sudo pacman -S easyeffects`)
switches the effects EasyEffects puts on your microphone, with one key. In EasyEffects' window, on the
**Microphone** tab, add effects (a *Pitch* effect for a deep or high voice, *Echo*, *Reverb*…) and save the
result as a preset (a "voice"). Then in NumpadControl: *Voice changer on / off* flips one voice on and off
(pressing the key of another voice switches to it); *Use a voice* always selects that voice; *Back to normal*
switches the effects off (or loads a "normal" preset, if you name one, so effects you want to keep stay on). The
voice name has a pick list of your presets. Apps hear the effect when they record from **Easy Effects Source**
(choose it as the microphone in OBS or Discord), or when EasyEffects is set to process all inputs. Notes:
"back to normal" uses EasyEffects' global switch, which also bypasses effects on your speakers unless you use the
"normal" preset; and if EasyEffects isn't running yet NumpadControl starts it in the background, which takes a few
seconds the first time (about 0.6 s afterwards), so let EasyEffects start at login if you want the first press to
be instant. A preset name that doesn't exist says so and lists the ones that do.

**Hearing your voices without a microphone:** `tools/voice-demo CLIP` takes any audio or video file (`--start 15
--seconds 8` picks the part), plays it into a silent virtual microphone, lets EasyEffects change it with each of your
microphone voices, and saves one file per voice in `~/Music/voice-demo` (`00-original`, `01-Normal`, `02-...`) to
listen to with `mpv ~/Music/voice-demo/*.wav`. Nothing plays through your speakers while it works, and your default
microphone, EasyEffects and the voice that was loaded are put back afterwards.

**Soundboard:** *Play a sound* plays an audio file you name (`~/Sounds/airhorn.mp3`) at the
volume you choose, on top of whatever else is playing, and returns at once, so sounds can overlap;
*Stop all sounds* cuts them off. One key, one sound: bind it to a Press, Hold or Double tap
slot. On Linux it uses `pw-play` (PipeWire), else `paplay`, else `ffplay`, so mp3, ogg, wav and
more all work. The sound comes out of your normal speakers, which OBS records with "Desktop
audio"; it isn't sent into your microphone. On Windows only `.wav` files play (and there is no
volume setting).

**Privacy panic** is for the moment someone walks in: one press mutes the microphone and the
speakers, pauses the music or video and hides every window (an empty workspace on Hyprland,
every window minimised on KDE, Win+D on Windows). Each of those is a checkbox in the key's
settings, and **Lock the screen too** is off until you turn it on. Name an OBS scene and its
camera source and it hides that as well (OBS must be running). It never stops halfway: if
one step fails (no microphone, OBS not open…) the rest still happen and the on-screen message
says what failed. Mutes are real "mute", not a toggle, so pressing it twice doesn't un-mute
anything; unmute with the normal mute keys. On Windows "pause" is a media Stop, and hiding
windows is Win+D (a second press of it brings them back).

**Undo privacy panic** puts back what the last panic changed, and only that: it un-mutes the microphone and the
speakers it muted (one you had already muted stays muted), brings the windows back (the workspace you were on,
every minimised window, Win+D on Windows), shows the OBS camera again and resumes the music it paused. It
remembers on disk, so it works after a restart, and pressing the panic twice doesn't make it forget the first
time. It can't unlock the screen (you do that) and on Windows it never presses play for you, since Windows can't
say whether something was playing. Bind it next to the panic key, for example on the same key in the layer.

**Force-quit the focused window** (press twice, like Sleep) kills the focused program at once,
with no chance to save: use it on a frozen or raging app, not on work you want to keep. It
ends the whole program, so every window of a browser goes together. It never touches the
desktop itself (Hyprland, Plasma, the Windows desktop) or NumpadControl. Optionally it opens a
page afterwards (your "funny video"). Like Sleep, it can't be used in macros or from the Test
button.

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

**Turbo** (a checkbox on the Press action, with a rate from 1 to 60 per second): hold the key and
the action keeps firing at that rate until you let go, for any action that is safe to repeat. A quick
tap is still one press: turbo starts after 0.2 s. It needs a key with only a Press action (a key
that also has Hold or Double tap waits for you to let go, so there is nothing to repeat), and it
isn't offered for Sleep / Shut down / Restart / Force-quit. In the settings file it is `"turbo": 30`
next to the action. The rate is as fast as the action can run: Press keys and Type text
manage it easily; an action that has to start a program or call OBS each time will hit its own
limit, and a slow action simply finishes before the next one starts.

## Any other key
The standard numpad keys have fixed names: `0`-`9`, `.`, `+`, `-`, `*`, `/`, `Enter`,
`Backspace`, `NumLock`, plus `000` (three `0`s in a burst). A numpad with more keys (a `(`, a
Tab, a macro key, a `00`) works too. Any other key the numpad sends is reported by its code:
`KEY_TAB` on Linux (evdev), `SC_0F` (scan code; `SC_E0_1D` with the E0 prefix) on Windows.
The NumpadControl app adds such a key to the pad when you turn on **Learn** and press it. With
only the settings file:

1. Find the key's id: on Linux the service log says `extra key KEY_TAB` when you press it
   (`journalctl --user -u numpad-control -f`); on Windows, `python -m numpadctl.platform.windows_rawinput --all`
   shows scan codes.
2. List it in `config.json` and bind it like any key:

        "extra_keys": [{"id": "KEY_TAB", "label": "Tab"}],
        "profiles": [{ ..., "bindings": {"KEY_TAB": {"tap": {"action": "media_next", "params": {}}}}}]

On Windows an added key is grabbed (it stops typing) like the standard keys; one that isn't
listed still types as usual. `00` is the two-zeros key (two `0`s within 60 ms): it is
recognised once `{"id": "00"}` is in `extra_keys` (or while the app's Learn mode is on), so
double-tapping `0` is unchanged. Detecting the numpad only finds which keyboard it is (vendor
and product ID); the standard names are fixed, everything else is learned.

## A whole keyboard as an extra pad (Linux)
Any plugged-in keyboard can be a second control pad: every one of its keys can run an action,
with the same Press / Hold / Double tap, layers and profiles as the numpad.

- **Add it:** in the settings window, **Device ⋯ → Add a keyboard…**, pick it, give it a name,
  then **Save**. The window then draws that keyboard (tinted keys already do something). Keys the
  drawing doesn't have (media keys…) are added with **Learn**, below the picture.
- **Stop this keyboard typing** is on by default: its keys only run actions. **Hold Ctrl+Alt+Esc on
  it to give it back** to the system (it types normally again; remove it and add it again, or
  restart NumpadControl, to use it as a pad again). Try that on a spare keyboard first, never on
  the only one you have. If NumpadControl stops, the keyboard is given back by itself.
- **Access:** Linux only lets you read keyboards you're allowed to. The add dialog marks the
  ones that need it, and **Allow access…** installs a small udev rule for that one keyboard
  (through `pkexec`, so it asks for your password). That is the same permission the numpad gets,
  and it means programs you run can read that keyboard's keys, so think twice before allowing a
  keyboard you type passwords on. The app asks you to confirm before it does this, and **Remove this
  keyboard** offers to take the permission away again (the uninstall removes all of them too).
- **While a game with anti-cheat runs** (see below), extra keyboards are let go like the numpad.
- **Not on Windows yet** (the window hides the Device row there).

The settings file keeps them in `devices`, and a key of an extra keyboard is written with
the keyboard's `id` in front (`hp:KEY_A`); the numpad's own keys have no prefix:

        "devices": [{"id": "hp", "vendor": "03f0", "product": "0024", "name": "HP keyboard", "grab": true,
                     "extra_keys": [{"id": "hp:KEY_MUTE", "label": "Mute"}]}],
        "profiles": [{ ..., "bindings": {"hp:KEY_F1": {"tap": {"action": "mic_mute", "params": {}}}}}]

The service picks up a changed `devices` list by itself (within a couple of seconds). Removing a
keyboard in the window also removes the actions set on its keys.

## Layer key and profiles
- **Layer key** (Settings): hold it and every other key uses its "Layer" actions,
  doubling the number of actions.
- **Profiles** (top left): different actions while a given app is focused,
  matched by window class (e.g. `kitty`, `org.kde.dolphin`). Anything a profile
  leaves unset uses Default.
  The profile menu can create, **duplicate** (copies every key, slot and layer key
  to start from), edit and delete profiles.
- **Share a profile.** *Profile ⋯ → Export profile…* saves the selected profile as a small JSON file (only
  its keys, actions and window match: never the OBS password or other settings); *Import profile…* adds one
  you were sent as a new profile (renamed "Name (2)" if the name is taken). Before anything is added you see
  what it will do, with ⚠ on actions that run programs, press keys for you or power the PC off, because an
  imported profile runs on your computer as you: only import files from people you trust. The importer is
  strict: the file must be small, plain JSON of the right shape, and anything it doesn't understand (an action
  from a newer version, a setting that doesn't check out) is left out and listed rather than guessed at.
- **Profile library.** *Profile ⋯ → Browse library…* lists ready-made profiles from
  [numpad-controllib](https://github.com/youssefahmed2017/numpad-controllib): official ones and ones shared by
  the community, with search and the ⚠ actions each one uses. Picking one imports it exactly like a file: it
  is checked the same way and you see what it will do before it is added. Nothing is fetched until you open
  the library. `NUMPADCTL_LIBRARY` points it at another `https://` address or at a local copy of the library.
  Names and descriptions have control and text-direction characters taken out (so a name can't disguise itself),
  and the library is never fetched over a redirect to plain `http://`. A profile is also checked against the checksum in the library's list, so a half-updated
  online copy is refused instead of imported.
- **Stickers.** Give a key a picture: select it and press **Choose image…** in the *Sticker* card (PNG, JPG, GIF,
  WebP, BMP or SVG). The picture takes the place of the key's name on the pad and on the key map overlay. A sticker
  belongs to a key of one profile, and a profile with none for a key shows the Default profile's, like it does for
  actions. Pictures are shrunk to at most 128 px and kept in the `stickers` folder of the settings directory; saving
  deletes the ones no profile uses any more. They stay on your computer: exporting a profile leaves them out.
- **Sticker packs.** A pack gives the whole pad its pictures in one go: **Profile ⋯ → Apply sticker pack…**, pick a `.zip`,
  see what will change, confirm. A pack is a zip (or a folder) with one picture per key named after it: `0.png` … `9.png`,
  `000.png`, `dot.png`, `plus.png`, `minus.png`, `star.png`, `slash.png`, `enter.png`, `numlock.png`, `backspace.png`
  (PNG, JPG, GIF, WebP, BMP or SVG), and optionally a `pack.json` with the pack's `name`, `author` and `license`, shown when
  you apply it. It is only a shortcut for choosing 19 pictures by hand, so nothing in it can do more than that, and it is
  read strictly: at most 64 files, 5 MB a picture, 40 MB in all, and names inside the zip never reach the file system.
  To make one, put your pictures in a folder (square, 256 px or more, transparent background) and run
  `python tools/make-sticker-pack.py my-pictures --name "My pack" --author "You" --license "Personal use only"`: it checks them,
  says which keys are missing and writes the zip. Anyone may make, share or sell packs; the app stays free either way.
- **Icon packs.** A pack can also restyle the icon of every *action* (volume, media, OBS, launch app …): **Settings →
  Appearance → Icon pack → Install pack…**, pick a `.zip`, confirm. A pack is a zip (or folder) with one picture per action,
  named after the action's id: `volume_up.png`, `mic_mute.png`, `obs_start_recording.png` … (any picture type as above), and
  optionally a `pack.json` with `name`, `author`, `license`. The pad and the key map overlay then draw the pack's picture
  instead of the built-in icon; an action the pack has no picture for keeps the built-in icon, and a sticker you put on a
  key still wins. Pictures are shrunk to 128 px and kept in the `icon-packs` folder of the settings directory; **Remove**
  deletes a pack and "Built-in icons" goes back. Read as strictly as sticker packs (at most 160 files, 5 MB a picture, 40 MB
  in all, 20 packs installed). To make one: `python tools/make-icon-pack.py my-icons --name "My icons" --author "You"`.
- **Profile sets.** A set is a whole separate setup (its own Default and its own
  per-app profiles), for example "Coding", "Streaming" and "Gaming". Only the active set
  does anything, and a set never borrows keys from another one. Put **Switch to a profile
  set**, **Next profile set** or **Previous profile set** on any key (a layer key slot
  works well) and press it to swap; the name pops up as a confirmation. One active set
  covers every pad and extra keyboard, and the choice is remembered across restarts.
  Settings files from before sets work as they were: your profiles become one set called
  "Default". In `config.json` they are the `sets` list (`"sets": [{"name": "Coding",
  "profiles": [...]}]`); which one is active is saved next to the modes state.
- **Key map overlay (the "Ghost HUD").** Press **Layer + Enter** and a see-through copy of your numpad
  fades onto the middle of the screen, twice: what each key does normally on the left, and with the
  layer key held on the right (for the app you are in: its profile first, Default for the rest; a key
  with more than one action shows "+1"). Press Layer + Enter again, or let go of the layer key, and it
  fades away. Holding the layer key alone no longer shows it, so Layer + 1 and friends don't flash it up.
  The combo belongs to the overlay: an action bound to Layer + that key doesn't run (Settings warns
  you). It never takes focus and lets every click through. Settings → *Key map overlay* switches it off,
  picks the combo key (*Open it with: Layer + …*), or brings back the old way (*Holding the layer key*:
  it shows for as long as the layer key is held), sets the opacity (30 to 100 %), and has a **Preview**
  button. In `config.json`: `"hud": {"trigger": "combo" or "hold", "key": "Enter"}`. It only
  runs when a layer key is set: it is a small separate process the service starts and stops by
  itself, so it costs nothing without one. On Linux it is drawn through XWayland (Wayland itself
  doesn't let an ordinary window float above the others without taking focus, XWayland does), so
  XWayland has to be running, as it is by default on Hyprland and KDE. On Windows it is a normal
  topmost window that doesn't take focus. If it keeps failing to start, the service log says so
  and tries again, slower each time. Restarting or stopping
  the service takes the overlay with it (and a crashed service's leftover is ended by the next one), so there is only ever one.

## Appearance (make it yours)
Settings → **Appearance** changes how the window looks and moves, and shows every change at once (kept with
Save, like everything else):
- **Material 3 design** on or off. Off is Qt's classic look (plain buttons, checkboxes, tabs), still in your
  colours. The key map overlay always stays Material.
- **Shape:** round (Material 3 Expressive pills), rounded or square corners everywhere.
- **Colours:** light, dark or follow the system, then where the colours come from:
  - a **built-in accent**;
  - **any colour you pick**: Google's own maths turns it into a whole Material You theme;
  - **a picture**, like your wallpaper: the colour is picked the way Android picks it;
  - **pywal**: follows `~/.cache/wal/colors.json`, so `wal -i <picture>` re-colours NumpadControl too;
  - **a theme file**: a [Material Theme Builder](https://material-foundation.github.io/material-theme-builder/)
    export, [matugen](https://github.com/InioX/matugen)'s JSON, or a plain `{"primary": "#..."}`. Roles the file
    leaves out are made from its primary colour.

  The picture, pywal's file and the theme file are watched: when a wallpaper script rewrites them, the window
  (and the key map overlay) re-colours by itself. **Scheme style** picks how one colour becomes a theme (tonal
  spot like Android, vibrant, expressive, fidelity, content, neutral, monochrome, rainbow, fruit salad), and
  **Contrast** standard, medium or high. **Export theme…** saves the colours in use (light and dark) as a
  Theme Builder-style JSON file to share or tweak.
- **Icons for actions on keys:** every action has a built-in icon on its key and on the key map: OBS's logo with a
  red dot for *Start recording* and a square for *Stop recording*, Python's logo with ▶ for *Run Python*, a chain
  for a macro, a split path for *If a mode is on…*, a moon for sleep, speakers for volume, and so on (Google's
  Material Symbols; the OBS and Python logos from Simple Icons). A sticker you chose for a key wins; the switch
  turns them all off.
- **Motion:** animations on or off, their speed (slower to faster), ripples on presses.
- **Window:** opacity (60 to 100 %; below 100 your desktop shows through, blurred if your compositor blurs:
  KDE, Hyprland; on X11 it needs a compositor), the font (any installed one, or the built-in Google Sans) and the
  text size (85 to 130 %).

In `config.json` these are under `"look"` (light/dark, accent and contrast stay where they were):
`"look": {"material": true, "source": "file", "file": "~/.cache/matugen/colors.json", "variant": "vibrant",
"shape": "round", "opacity": 90, "animations": true, "speed": 1.0, "ripples": true, "font": "", "font_scale": 100}`.
Sources are `accent`, `color` (with `"seed": "#rrggbb"`), `image` (with `"image": "<picture>"`), `pywal` and `file`.

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
and notifications are carried out by the trusted parent process, and a snippet that
prints more than 64 KB, asks for more than 10 actions or sends an oversized request is
stopped.
This is a solid guardrail, not a perfect jail. Don't run snippets from people you
don't trust.

## Commands
    numpad-control                          # open the settings window
    .venv/bin/python -m numpadctl run       # the service (normally via systemd)
    .venv/bin/python -m numpadctl detect    # press a key to find your numpad's USB ID
    .venv/bin/python -m numpadctl list      # list input devices
    .venv/bin/python -m numpadctl check     # guided test of a numpad (for docs/compatibility.md)
    .venv/bin/python -m numpadctl update    # install a newer release now
    journalctl --user -u numpad-control -f  # service log

## Starter presets
The ⋯ menu next to Profile → **Add a starter preset…** fills a profile's empty keys for
a common job: *Streaming (OBS)*, *Media and volume*, *Editing*, *Windows and desktops*.
Keys that already do something are never changed, and you can edit everything after.
(`numpadctl/presets.py`)

## Your own templates (Python)
Four starter presets aren't enough for every pad, so you can write your own, all inside the app: Profile ⋯ →
**Add a starter preset…** lists your templates after the built-in presets, with **New template…**, **Edit…**,
**Import…** (a `.py` someone shared with you) and **Delete**. The editor shows the code with Python colours and
every action on the right: search ("obs rec", "volume") and double-click one to insert a ready line such as
`pad.tap("1", "volume_up")`. **Try it** runs the template and lists what it would add (or the mistake and its
line) without changing anything; **Save** keeps it. Like a preset, a template only fills keys that have nothing
yet. (The files live in `~/.config/numpad-control/templates/` on Linux, if you'd rather use your own editor.)

```python
NAME = "Streaming pro"
DESCRIPTION = "Scenes on 1-3, mute on 0, copy-paste on the layer."

def build(pad):
    for n in range(1, 4):
        pad.tap(str(n), "obs_set_scene", scene=f"Scene {n}")
    pad.tap("0", "mic_mute")
    pad.hold("0", "obs_toggle_streaming")
    pad.layer.tap("1", "press_keys", keys="ctrl+c")
    pad.macro("5", [step("press_keys", keys="ctrl+a"), step("press_keys", keys="ctrl+c")])
    pad.if_mode("8", "Stream mode", [step("mic_mute")], [step("media_play_pause")])
    if pad.platform == "linux":
        pad.note("Shown after the keys are added.")
```

- `pad.tap / hold / double(key, action, setting=value...)`, `pad.set(key, slot, action, ...)` (with `rapid=` and
  `turbo=` too), `pad.macro(key, steps)` and `pad.if_mode(key, mode, then, otherwise)` fill the normal keys;
  the same on `pad.layer` fill the layer keys. `step(action, setting=value...)` is one macro step.
- It can read: `pad.keys`, `pad.platform`, `pad.desktop`, `pad.profile`, `pad.layer_key`, `pad.modes`,
  `pad.actions` (every action id and its settings) and `pad.bound` / `pad.layer_bound` (keys already in use).
- The editor's action list (or `python -m numpadctl actions`) shows every action id with its settings and their
  defaults; settings you leave out get the default.
- **Safety:** the list is made by reading `NAME` and `DESCRIPTION` without running anything. A template only
  runs when you pick it, in its own process with a 10-second limit (on Linux it also can't write files or start
  programs), and everything it asks for is checked like an imported profile file: unknown actions, bad settings
  and modes you don't have are left out and listed. It is still a program on your computer that can read files,
  so only keep templates you trust in that folder.
