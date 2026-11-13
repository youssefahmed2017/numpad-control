#!/usr/bin/env python3
"""Render the screenshots the README and docs show, offscreen, from a temporary config.

    python tools/docs-screenshots.py [OUTPUT_FOLDER]      (default: docs/screenshots)

Nothing opens on a screen and nothing touches the real config. The docs-screenshots workflow runs
this when the settings window's code changes and commits the pictures that came out different.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from numpadctl import config, modes, presets, ui_common  # noqa: E402
from numpadctl_ui import dialogs, picker as picker_module, template_editor, theme, tokens, tools, welcome, window as window_module  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
SIZE = (1180, 800)


def step(action, **params):
    return {"action": action, "params": params}


GO_LIVE = [step("obs_switch_scene", scene="Live"), step("mic_mute"), step("wait", seconds="1"),
           step("obs_start_streaming"), step("show_notification", text="You are live")]


class Link:
    connected = True

    def __init__(self, on_message, dispatch):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


def settle(app, seconds=0.6):
    """Let timers and queued layout work run (the editor is rebuilt a moment after a key is selected)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication.instance() or QApplication([])
    theme.apply(app, "dark", tokens.DEFAULT_ACCENT, "standard")
    root = Path(tempfile.mkdtemp())
    cfg = {"device": {"vendor": "c0f4", "product": "05f5"}, "grab": True, "feedback": True, "appearance": "dark",
           "layer_key": "Enter", "modes": ["Stream mode", "Gaming"], "obs": {"host": "localhost", "port": 4455, "password": ""},
           "welcomed": True,
           "profiles": [{"name": "Default", "match": "", "layer_bindings": {}, "bindings": {}}]}
    (root / "config.json").write_text(json.dumps(cfg))
    patches = [mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", root / "config.json"),
               mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "modes.json"),
               mock.patch.object(picker_module, "RECENT_PATH", root / "recent.json"),
               mock.patch.object(ui_common, "ServiceLink", Link),
               mock.patch.object(ui_common, "installed_apps", lambda: [("Firefox", "firefox.desktop"), ("Spotify", "spotify.desktop")])]
    for p in patches:
        p.start()
    written, failed = [], []

    def save(widget, name):
        settle(app, 0.4)
        QWidget.grab(widget).save(str(OUT / name))   # not widget.grab(): SettingsDialog has a control of that name
        written.append(name)

    def attempt(name, work):
        try:
            work()
        except Exception as error:   # one picture failing must not stop the others
            failed.append(name)
            print(f"warning: {name} was not made: {error!r}", file=sys.stderr, flush=True)

    try:
        w = window_module.MainWindow()
        w.resize(*SIZE)
        w.show()
        w.update_status({"running": True, "connected": True, "devices": ["Usb KeyBoard"]})
        keys = w.keymap()
        presets.apply(presets.BY_NAME["Streaming (OBS)"], keys)
        keys["7"] = {"tap": step("macro", steps=GO_LIVE)}
        keys["5"] = {"tap": step("obs_toggle_recording"), "hold": step("obs_stop_recording")}
        keys["8"] = {"tap": step("if_mode", mode="Stream mode", then=[step("media_next")], otherwise=[step("mic_mute")])}
        w.arrange_keys()
        w.refresh_pad()

        def window_with(key, name):
            def work():
                w.select(key)
                settle(app)
                w.dirty_label.setText("")
                save(w, name)
            return work
        attempt("macro.png", window_with("7", "macro.png"))
        attempt("hold.png", window_with("5", "hold.png"))
        attempt("if-mode.png", window_with("8", "if-mode.png"))

        def popup():
            w.snackbar.show_message("Recording")
            save(w, "popup.png")
        attempt("popup.png", popup)

        def dialog(name, make, size):
            def work():
                d = make()
                d.resize(*size)
                d.show()
                save(d, name)
                d.close()
            return work
        attempt("settings.png", dialog("settings.png", lambda: dialogs.SettingsDialog(w), (620, 700)))

        def appearance():
            d = dialogs.SettingsDialog(w)
            d.tabs.setCurrentIndex(1)
            d.resize(620, 700)
            d.show()
            save(d, "settings-appearance.png")
            d.close()
        attempt("settings-appearance.png", appearance)
        attempt("presets.png", dialog("presets.png", lambda: dialogs.PresetDialog(w, "Default"), (560, 480)))

        def tester():
            d = tools.KeyTesterDialog(w)
            d.resize(520, 420)
            d.show()
            base = 100.0
            for key, down, dt in (("5", True, 0), ("5", False, .09), ("0", True, 1.2), ("0", False, .004)):
                base += dt
                d.add_raw(key, down, base)
            d.add_key("5")
            save(d, "tester.png")
            d.close()
        attempt("tester.png", tester)
        w.last_status = {"running": True, "connected": True, "devices": ["Usb KeyBoard"]}
        attempt("welcome.png", dialog("welcome.png", lambda: welcome.WelcomeDialog(w), (640, 560)))
        attempt("template-editor.png", dialog("template-editor.png", lambda: template_editor.TemplateEditor(w, w), (900, 640)))
    finally:
        for p in patches:
            p.stop()
    print(f"wrote {len(written)} pictures to {OUT}: {', '.join(written)}", flush=True)
    os._exit(0 if written else 1)   # skip Qt's teardown, which can crash after the work is done


if __name__ == "__main__":
    main()
