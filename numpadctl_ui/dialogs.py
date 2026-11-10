"""Settings and profile dialogs."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QVBoxLayout, QWidget)

from numpadctl import config, desktop, devices, keys, modes, obs, presets, ui_common
from .checkbox import Switch
from . import tokens
from .buttons import ComboBox, PushButton, SmoothScrollArea, SpinBox
from .widgets import card, label

APPEARANCES = [("auto", "Follow the system"), ("light", "Light"), ("dark", "Dark")]


class SettingsDialog(QDialog):
    """Device, keys, appearance, modes and OBS. Read the result with values()."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        cfg = window.cfg
        self.setWindowTitle("Settings")
        self.resize(560, 720)
        outer = QVBoxLayout(self)
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        frame, box = card()
        box.addWidget(label("Device", "heading"))
        row = QHBoxLayout()
        self.device_label = label("", "dim")
        self.device = dict(cfg["device"])
        self._show_device()
        row.addWidget(self.device_label, 1)
        self.detect_button = PushButton("Detect…")
        self.detect_button.clicked.connect(self.detect)
        row.addWidget(self.detect_button)
        box.addLayout(row)
        self.grab = Switch("Stop numpad from typing (keys only trigger actions)")
        self.grab.setChecked(cfg["grab"])
        box.addWidget(self.grab)
        layout.addWidget(frame)

        frame, box = card()
        box.addWidget(label("Keys", "heading"))
        box.addWidget(label("Layer key: hold it to give every other key a second set of actions", "small"))
        extras = [e["id"] for e in cfg.get("extra_keys", [])]
        self.layer_choices = [None] + ui_common.LAYER_KEY_CHOICES + extras
        self.layer_key = ComboBox()
        self.layer_key.addItems(["Off"] + ui_common.LAYER_KEY_CHOICES + [keys.display(k, cfg) for k in extras])
        self.layer_key.setCurrentIndex(self.layer_choices.index(cfg.get("layer_key")))
        box.addWidget(self.layer_key)
        box.addWidget(label("Numpad layout: where the keys are drawn (what each key does doesn't change)", "small"))
        self.layout_ids = list(ui_common.LAYOUTS)
        self.numpad_layout = ComboBox()
        self.numpad_layout.addItems([name for name, _ in ui_common.LAYOUTS.values()])
        current = cfg.get("numpad_layout") if cfg.get("numpad_layout") in ui_common.LAYOUTS else "standard"
        self.numpad_layout.setCurrentIndex(self.layout_ids.index(current))
        box.addWidget(self.numpad_layout)
        self.feedback = Switch("On-screen confirmations (e.g. “Recording” when OBS starts recording)")
        self.feedback.setChecked(cfg.get("feedback", True))
        box.addWidget(self.feedback)
        box.addWidget(label("Appearance of this window", "small"))
        self.appearance = ComboBox()
        self.appearance.addItems([text for _, text in APPEARANCES])
        self.appearance.setCurrentIndex([k for k, _ in APPEARANCES].index(cfg.get("appearance", "auto")))
        box.addWidget(self.appearance)
        box.addWidget(label("Accent colour", "small"))
        self.accent = ComboBox()
        for name, seed in tokens.SEEDS.items():
            swatch = QPixmap(16, 16)
            swatch.fill(Qt.transparent)
            painter = QPainter(swatch)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(seed))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, 16, 16)
            painter.end()
            self.accent.addItem(QIcon(swatch), name)
        self.accent.setCurrentText(cfg.get("accent", tokens.DEFAULT_ACCENT))
        box.addWidget(self.accent)
        box.addWidget(label("Contrast", "small"))
        self.contrast = ComboBox()
        self.contrast.addItems(["Standard", "Medium", "High"])
        self.contrast.setCurrentIndex(tokens.CONTRASTS.index(cfg.get("contrast", "standard")))
        box.addWidget(self.contrast)
        layout.addWidget(frame)

        frame, box = card()
        box.addWidget(label("Key map overlay", "heading"))
        box.addWidget(label("A see-through copy of your numpad fades onto the screen, showing what each key does: "
                            "normally on the left, with the layer key held on the right. It never takes focus or "
                            "catches clicks.", "dim", wrap=True))
        hud = config.hud_settings(cfg)
        self.hud_enabled = Switch("Show the key map")
        self.hud_enabled.setChecked(hud["enabled"])
        box.addWidget(self.hud_enabled)
        # How it opens (issue #12): Layer + a key toggles it (the default, so Layer + 1 etc. don't flash it up),
        # or the old way, for as long as the layer key is held. Index i < len(HUD_KEYS) means "Layer + HUD_KEYS[i]".
        trigger_row = QHBoxLayout()
        trigger_row.addWidget(label("Open it with", "small"))
        self.hud_keys = [k for k, *_ in ui_common.LAYOUT if k not in config.TAP_ONLY_KEYS]
        self.hud_trigger = ComboBox()
        self.hud_trigger.addItems([f"Layer + {ui_common.KEY_LABELS.get(k, k)}" for k in self.hud_keys]
                                  + ["Holding the layer key"])
        self.hud_trigger.setAccessibleName("How the key map opens")
        self.hud_trigger.setCurrentIndex(len(self.hud_keys) if hud["trigger"] == "hold" else
                                         self.hud_keys.index(hud["key"]) if hud["key"] in self.hud_keys else
                                         self.hud_keys.index(config.HUD_DEFAULT_KEY))
        trigger_row.addWidget(self.hud_trigger, 1)
        box.addLayout(trigger_row)
        self.hud_note = label("", "small", wrap=True)   # says when the combo is taken (see _check_hud_combo)
        box.addWidget(self.hud_note)
        self.hud_trigger.currentIndexChanged.connect(self._check_hud_combo)
        self.layer_key.currentIndexChanged.connect(self._check_hud_combo)
        self._check_hud_combo()
        row = QHBoxLayout()
        row.addWidget(label("Opacity", "small"))
        self.hud_opacity = SpinBox()
        self.hud_opacity.setRange(30, 100)
        self.hud_opacity.setSuffix(" %")
        self.hud_opacity.setValue(hud["opacity"])
        self.hud_opacity.setAccessibleName("Key map opacity")
        row.addWidget(self.hud_opacity)
        preview = PushButton("Preview")
        preview.setObjectName("flat")
        preview.setToolTip("Shows the key map for a few seconds (it uses the saved settings and layer key)")
        preview.clicked.connect(self.preview_hud)
        row.addWidget(preview)
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)

        frame, box = card()
        box.addWidget(label("Modes", "heading"))
        box.addWidget(label("On/off switches that “If a mode is on…” keys check. Flip them here, or with "
                            "the Toggle / Turn on / Turn off a mode actions.", "dim", wrap=True))
        self.mode_names = list(cfg.get("modes", []))
        self.modes_box = QVBoxLayout()
        box.addLayout(self.modes_box)
        add_row = QHBoxLayout()
        self.new_mode = QLineEdit(placeholderText="Add a mode (e.g. Stream mode)")
        self.new_mode.returnPressed.connect(self.add_mode)
        add = PushButton("Add")
        add.clicked.connect(self.add_mode)
        add_row.addWidget(self.new_mode, 1)
        add_row.addWidget(add)
        box.addLayout(add_row)
        self.fill_modes()
        layout.addWidget(frame)

        frame, box = card()
        box.addWidget(label("OBS", "heading"))
        box.addWidget(label("In OBS: Tools → WebSocket Server Settings → Enable WebSocket server. "
                            "Use “Show Connect Info” to see the password.", "dim", wrap=True))
        s = cfg["obs"]
        self.host = QLineEdit(s.get("host", "localhost"))
        self.port = SpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(s.get("port", 4455)))
        self.password = QLineEdit(s.get("password", ""))
        self.password.setEchoMode(QLineEdit.Password)
        for text, widget in (("Host", self.host), ("Port", self.port), ("Password", self.password)):
            box.addWidget(label(text, "small"))
            box.addWidget(widget)
        test_row = QHBoxLayout()
        test = PushButton("Test connection")
        test.clicked.connect(self.test_obs)
        self.obs_result = label("", "dim")
        test_row.addWidget(test)
        test_row.addWidget(self.obs_result, 1)
        box.addLayout(test_row)
        layout.addWidget(frame)
        layout.addStretch()

        scroll.setWidget(page)
        outer.addWidget(scroll)
        buttons = QDialogButtonBox()
        buttons.addButton(PushButton("Close"), QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.accept)
        outer.addWidget(buttons)

    def _show_device(self):
        d = self.device
        self.device_label.setText(f"{d.get('name', 'USB numpad')}  ({d['vendor']}:{d['product']})")

    def detect(self):
        self.detect_button.setEnabled(False)
        self.device_label.setText("Press any key on your numpad (15 s)…")

        def done(spec, error):
            self.detect_button.setEnabled(True)
            if spec:
                self.device = spec
            elif error:
                self.window.toast(str(error))
            else:
                self.window.toast("No numpad key press was seen.")
            self._show_device()
        self.window.detect(done)

    # modes: names are settings (saved with Save); on/off is live state (saved right away)
    def fill_modes(self):
        while self.modes_box.count():
            item = self.modes_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        state = modes.states()
        for name in self.mode_names:
            row = QHBoxLayout()
            switch = Switch(name)
            switch.setChecked(state.get(name, False))
            switch.toggled.connect(lambda on, n=name: modes.set_mode(n, on))
            remove = PushButton("Remove")
            remove.setObjectName("flat")
            remove.clicked.connect(lambda _=False, n=name: self.remove_mode(n))
            row.addWidget(switch, 1)
            row.addWidget(remove)
            self.modes_box.addLayout(row)

    def add_mode(self):
        name = " ".join(self.new_mode.text().split())
        if not name:
            return
        if name.lower() in (n.lower() for n in self.mode_names):
            self.window.toast(f"There's already a mode called “{name}”")
            return
        self.mode_names.append(name)
        self.new_mode.clear()
        self.fill_modes()

    def remove_mode(self, name):
        self.mode_names.remove(name)
        self.fill_modes()

    def obs_values(self):
        return {"host": self.host.text().strip() or "localhost", "port": self.port.value(),
                "password": self.password.text()}

    def test_obs(self):
        self.obs_result.setText("Connecting…")
        settings = self.obs_values()

        def done(version, error):
            self.obs_result.setText(str(error) if error else f"Connected to OBS {version}")
        ui_common.run_in_background(lambda: obs.test_connection(settings), done, self.window.dispatch)

    def hud_choice(self):
        """("combo", key) or ("hold", key the combo would use) from the "Open it with" list."""
        index = self.hud_trigger.currentIndex()
        if index >= len(self.hud_keys):
            return "hold", config.hud_settings(self.window.cfg)["key"]
        return "combo", self.hud_keys[index]

    def _check_hud_combo(self, *_):
        """Explain what the chosen combo costs: the overlay takes it, so an action bound there won't run."""
        trigger, key = self.hud_choice()
        layer = self.layer_choices[self.layer_key.currentIndex()]
        name = ui_common.KEY_LABELS.get(key, key)
        if trigger == "hold":
            text = "It shows while the layer key is held, and also pops up when you press Layer + another key."
        elif not layer:
            text = "Choose a layer key (above) first: the key map opens with Layer + a key."
        elif key == layer:
            text = f"{name} is the layer key itself: pick another key for the key map."
        else:
            taken = [p["name"] for p in self.window.cfg["profiles"] if key in p.get("layer_bindings", {})]
            text = (f"Layer + {name} opens and closes the key map, so what it does in {', '.join(taken)} won't run."
                    if taken else f"Press Layer + {name} to open the key map, again (or let go of the layer key) to close it.")
        self.hud_note.setText(text)

    def preview_hud(self):
        if not self.window.link.connected:
            self.window.toast("The background service isn't running.")
            return
        if not self.window.cfg.get("layer_key"):
            self.window.toast("Choose a layer key (Keys, above) and save first: the key map shows what it unlocks.")
            return
        self.window.link.send({"cmd": "hud"})
        self.window.toast("Showing the key map for a few seconds (saved settings).")

    def values(self):
        return {"device": self.device, "grab": self.grab.isChecked(),
                "hud": {"enabled": self.hud_enabled.isChecked(), "opacity": self.hud_opacity.value(),
                        "trigger": self.hud_choice()[0], "key": self.hud_choice()[1]},
                "layer_key": self.layer_choices[self.layer_key.currentIndex()],
                "numpad_layout": self.layout_ids[self.numpad_layout.currentIndex()],
                "feedback": self.feedback.isChecked(),
                "appearance": APPEARANCES[self.appearance.currentIndex()][0],
                "accent": self.accent.currentText(),
                "contrast": tokens.CONTRASTS[self.contrast.currentIndex()],
                "modes": self.mode_names, "obs": self.obs_values()}


class ProfileDialog(QDialog):
    """Name and window classes of a profile (new, duplicated, or edited)."""

    def __init__(self, parent, profiles, index, copy_from):
        super().__init__(parent)
        if copy_from is not None:
            source = profiles[copy_from]
            title = f"Duplicate “{source['name']}”"
            intro = (f"Makes a new profile that starts with the same keys as “{source['name']}”, "
                     "which you can then change. Choose the apps it applies to.")
            name, match = f"{source['name']} copy", source["match"] if copy_from else ""
        else:
            title = "Edit profile" if index else "New profile"
            intro = "A profile's keys apply while one of its apps is focused. Keys it doesn't set use the Default profile."
            name, match = (profiles[index]["name"], profiles[index]["match"]) if index else ("", "")
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(intro, "dim", wrap=True))
        layout.addWidget(label("Name", "small"))
        self.name = QLineEdit(name)
        layout.addWidget(self.name)
        layout.addWidget(label("Window classes (comma-separated)", "small"))
        self.classes = QLineEdit(match)
        layout.addWidget(self.classes)
        windows = desktop.open_windows()
        if windows:
            layout.addWidget(label("Add an open window", "small"))
            picker = ComboBox()
            picker.addItems(["—"] + [f"{t[:40]}  ({c})" for c, t in windows])
            picker.currentIndexChanged.connect(lambda i: i > 0 and self._add_class(windows[i - 1][0]))
            layout.addWidget(picker)
        buttons = QDialogButtonBox()
        ok = PushButton("Save" if index else "Create")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.addButton(ok, QDialogButtonBox.AcceptRole)
        buttons.addButton(PushButton("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_class(self, cls):
        current = [c.strip() for c in self.classes.text().split(",") if c.strip()]
        if cls not in current:
            self.classes.setText(", ".join(current + [cls]))
        if not self.name.text():
            self.name.setText(cls.split(".")[-1])

    @classmethod
    def ask(cls, parent, profiles, index, copy_from=None):
        """(name, classes) or None if cancelled / no name."""
        dialog = cls(parent, profiles, index, copy_from)
        if dialog.exec() != QDialog.Accepted or not dialog.name.text().strip():
            return None
        return dialog.name.text().strip(), dialog.classes.text().strip()


class PresetDialog(QDialog):
    """Pick a starter setup; it fills only the keys that have nothing yet."""

    def __init__(self, parent, profile_name):
        super().__init__(parent)
        self.setWindowTitle("Starter preset")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Starter preset", "title"))
        layout.addWidget(label(f"Fills the empty keys of “{profile_name}”. Keys that already do something are kept.",
                               "dim", wrap=True))
        self.list = QListWidget()
        for preset in presets.PRESETS:
            self.list.addItem(preset.name)
        layout.addWidget(self.list)
        self.description = label("", "small", wrap=True)
        layout.addWidget(self.description)
        self.list.currentRowChanged.connect(
            lambda row: self.description.setText(presets.PRESETS[row].description if row >= 0 else ""))
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        buttons = QDialogButtonBox()
        ok = PushButton("Add keys")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.addButton(ok, QDialogButtonBox.AcceptRole)
        buttons.addButton(PushButton("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self):
        return presets.PRESETS[self.list.currentRow()]

    @classmethod
    def ask(cls, parent, profile_name):
        dialog = cls(parent, profile_name)
        return dialog.chosen() if dialog.exec() == QDialog.Accepted else None


class AddDeviceDialog(QDialog):
    """Pick a plugged-in keyboard to use as an extra pad. Read the result with values()."""

    def __init__(self, window, taken, taken_ids):
        super().__init__(window)
        self.window, self.taken, self.taken_ids = window, taken, taken_ids
        self.setWindowTitle("Add a keyboard")
        self.resize(480, 460)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(label("Pick the keyboard to use as a pad. All of its keys can run actions.", wrap=True))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.on_selected)
        layout.addWidget(self.list, 1)
        refresh = PushButton("Refresh")
        refresh.setObjectName("flat")
        refresh.clicked.connect(self.scan)
        layout.addWidget(refresh, 0, Qt.AlignLeft)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Name shown in the window")
        self.name.setAccessibleName("Keyboard name")
        layout.addWidget(self.name)
        self.grab = Switch("Stop this keyboard typing (its keys only run actions)")
        self.grab.setChecked(True)
        layout.addWidget(self.grab)
        layout.addWidget(label("Hold Ctrl+Alt+Esc on it to give it back if you ever need to type with it.", "small", wrap=True))

        self.access = QWidget()
        box = QVBoxLayout(self.access)
        box.setContentsMargins(0, 0, 0, 0)
        self.access_text = label("NumpadControl may only read the keyboards you allow. This one isn't allowed yet. "
                                 "Allowing it lets every program you run read what you type on it, not only "
                                 "NumpadControl, so don't allow a keyboard you type passwords on.", wrap=True)
        box.addWidget(self.access_text)
        self.allow = PushButton("Allow access…")
        self.allow.clicked.connect(self.allow_access)
        box.addWidget(self.allow, 0, Qt.AlignLeft)
        self.command = QLineEdit()
        self.command.setReadOnly(True)
        self.command.setAccessibleName("Command to run in a terminal")
        self.command.hide()
        box.addWidget(self.command)
        layout.addWidget(self.access)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.ok.setText("Add keyboard")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.scan()

    def scan(self, select=None):
        self.list.clear()
        for item in devices.keyboards(skip=self.taken):
            entry = QListWidgetItem(item["name"] + ("" if item["readable"] else "  (needs access)"))
            entry.setData(Qt.UserRole, item)
            self.list.addItem(entry)
            if select == (item["vendor"], item["product"]):
                self.list.setCurrentItem(entry)
        if self.list.count() == 0:
            self.on_selected(None, None)
        elif self.list.currentItem() is None:
            self.list.setCurrentRow(0)

    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def on_selected(self, item, _previous):
        device = self.current()
        self.name.setText(device["name"] if device else "")
        self.access.setVisible(bool(device) and not device["readable"])
        self.command.hide()
        self.allow.setEnabled(True)
        self.ok.setEnabled(bool(device) and device["readable"])

    def allow_access(self):
        device = self.current()
        if QMessageBox.question(self, "Allow access", f"Let programs you run read the keys of {device['name']}?\n\n"
                                "That includes anything typed on it, such as passwords. You can take it away again "
                                "by removing the keyboard in NumpadControl.") != QMessageBox.Yes:
            return
        self.allow.setEnabled(False)
        self.access_text.setText("Waiting for your password…")

        def done(_output, error):
            if error:
                self.access_text.setText(f"Couldn't do it from here ({error}). Run this in a terminal, then press Refresh:")
                self.command.setText(devices.manual_command(device["vendor"], device["product"]))
                self.command.show()
                self.allow.setEnabled(True)
            else:  # udev needs a moment to apply the rule
                QTimer.singleShot(1000, lambda: self.scan((device["vendor"], device["product"])))
        ui_common.run_in_background(lambda: devices.install_rule(device["vendor"], device["product"]), done,
                                    self.window.dispatch)

    def values(self):
        device = self.current()
        name = self.name.text().strip() or device["name"]
        return {"id": devices.make_id(name, self.taken_ids), "vendor": device["vendor"],
                "product": device["product"], "name": name, "grab": self.grab.isChecked()}
