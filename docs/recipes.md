# Recipes

Part of the [NumpadControl docs](../README.md). Each recipe is a setup you can build in a few minutes in the
settings window. Every action named here is described in [Features and actions](features.md#every-action).

To set a key: click it in the window, choose an action in the slot (Press, Hold or Double tap), fill in its
settings and press **Save**. Pressing a key while the window is in front only selects it; press it twice to run it.

## 1. A stream deck for OBS
In OBS: *Tools → WebSocket Server Settings → Enable WebSocket server*. Put the password under NumpadControl's
*Settings → OBS* and press **Test connection**.

| Key | Press | Hold | Double tap |
|---|---|---|---|
| `1` / `2` / `3` | Switch scene (Starting, Game, Chat) | | |
| `0` | Mute / unmute the microphone | Start / stop streaming | |
| `.` | Save replay buffer | | Start / stop recording |
| `Enter` | Show / hide the camera source | | |

Tips:
- Each OBS name field has a list button that fetches the real scene and source names from OBS, so you don't type them.
- Streaming is on Hold so a stray tap can't go live by accident.
- The fastest start: *Add a starter preset… → Streaming (OBS)* fills the empty keys for you.

## 2. A mic panic button
For the moment someone walks in.
1. Pick a key, for example `NumLock`, and set Press to **Privacy panic**.
2. Choose what it does with the checkboxes: mute microphone and speakers, pause media, hide every window, and
   optionally lock the screen. Name an OBS scene and camera source to hide those too.
3. On the same key in the layer, set **Undo privacy panic**. It puts back exactly what the panic changed.

A step that fails (OBS not open, no microphone) never stops the rest, and the message says what failed.

## 3. A coding pad that follows your editor
1. Open the *Profile ⋯* menu, create a profile and name it "Editor", and set its window match to your editor's window class (for
   example `kitty` or `code`).
2. Bind keys that only make sense there: `1` → Press keys `ctrl+shift+t`, `2` → Press keys `ctrl+w`, `3` → Macro
   (Type text `git status`, Press keys `Enter`).
3. Anything you leave unset falls back to your Default profile, so volume and media keys keep working.

When that window is focused the pad switches by itself, and goes back when you leave.

## 4. A game pad with a layer
1. Set a **Layer key** in Settings (for example `NumLock`). Hold it and every other key uses its Layer action.
2. Put the actions you need constantly on the normal keys (push-to-talk toggle, a macro), and the rarer ones on the layer.
3. Add a **Profile set** called "Gaming" with its own Default, and put *Switch to a profile set* on a layer key to
   swap between "Gaming" and "Everyday".

Press **Layer + Enter** to show a see-through map of what every key does, so you don't have to remember.

## 5. Your own template
If you set up the same pad often, write it once. *Profile ⋯ → Add a starter preset… → New template…* opens an editor:

```python
NAME = "Streaming pro"
DESCRIPTION = "Scenes on 1-3, mute on 0."

def build(pad):
    for n in range(1, 4):
        pad.tap(str(n), "obs_set_scene", scene=f"Scene {n}")
    pad.tap("0", "mic_mute")
    pad.hold("0", "obs_toggle_streaming")
```

**Try it** shows what it would add without changing anything. More in
[Your own templates](features.md#your-own-templates-python).

## Share what you build
*Profile ⋯ → Export profile…* saves a profile as a small file, and the
[profile library](https://github.com/youssefahmed2017/numpad-controllib) holds ready-made ones. If you make something
useful, a pull request there is welcome.
