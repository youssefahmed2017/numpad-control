# The service's API (for the Numpad Control app and other clients)

The open engine's background service and any settings app (the closed-source Numpad
Control app, or one you write) talk only through two things: the **settings file** and a
**local connection**. Nothing else is shared, which is what lets the app be closed source
on top of the AGPL engine (plan, section 11). Changes here are made only by adding fields
or messages, never by changing or removing existing ones.

`numpadctl/ui_common.py` (open) wraps all of this for Python apps: `ServiceLink` for the
connection (it reconnects by itself, and reports a lost service as a status with
`"running": false`), plus the key layout and action names.

## 1. The settings file

`config.json` in the settings folder (Linux: `~/.config/numpad-control/`; Windows:
`%APPDATA%\numpad-control\`). Clients edit it and save it; the service notices the change
by itself (within 2 seconds for device settings, at the next key press for everything
else). Write it atomically (a temporary file, then rename), as `config.save()` does.
The format is described by `DEFAULT_CONFIG` in `numpadctl/config.py`; unknown keys are kept.

## 2. The connection

**Linux:** a Unix socket at `$XDG_RUNTIME_DIR/numpad-control.sock`, readable only by the user.

**Windows** (and Linux with `NUMPADCTL_IPC=tcp`): TCP on `127.0.0.1`. The port and a
random key are in `%LOCALAPPDATA%\numpad-control\run\numpad-control.port` as
`{"port": 52344, "key": "…"}`, readable only by the user. Send the key and a newline first;
without it, the service closes the connection.

No service listening means it isn't running.

Both ways, every message is one JSON object on one line (UTF-8, ending in `\n`).

### Messages to the service

| Message | Meaning |
|---|---|
| `{"cmd": "status"}` | Send the status again (it's also sent on connecting and whenever it changes). |
| `{"cmd": "capture", "on": true}` | "Learn" mode: key presses are reported but run no actions, until `"on": false` or the client disconnects. |
| `{"cmd": "raw", "on": true}` | Also send every raw press and release (for a key tester), until `"on": false`. |
| `{"cmd": "detect"}` | Report the next numpad key pressed on any keyboard, to find which device is the numpad (15 seconds at most). |

### Messages from the service

| Message | When |
|---|---|
| `{"event": "status", "connected": true, "devices": ["…"], "paused_for": null}` | On connecting, on request, and whenever it changes. `connected`: the numpad is open. `devices`: its device names. `paused_for`: the game with anti-cheat the numpad is let go for, or `null`. |
| `{"event": "key", "key": "5"}` | A key was pressed (after the `000` burst is recognised, so `"000"` is a key here). |
| `{"event": "raw", "key": "0", "down": true, "t": 1234.567}` | With `raw` on: every press and release as the numpad sends it; `t` is a monotonic time in seconds. |
| `{"event": "detected", "spec": {"vendor": "c0f4", "product": "05f5", "name": "…"}}` | The answer to `detect`; `spec` is `null` if nothing was pressed in time. Put it in the settings file's `device` to use that numpad. |

Clients must ignore fields and events they don't know: newer services add them.

## 3. Commands

`python -m numpadctl …` works without any app: `run` (the service), `detect [--json]`,
`list`, `check` (the guided numpad test), `gui` (the app, or the settings file without it).
