"""Settings and profile dialogs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import desktop, modes, obs, ui_common
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
        scroll = QScrollArea()
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
        self.detect_button = QPushButton("Detect…")
        self.detect_button.clicked.connect(self.detect)
        row.addWidget(self.detect_button)
        box.addLayout(row)
        self.grab = QCheckBox("Stop numpad from typing (keys only trigger actions)")
        self.grab.setChecked(cfg["grab"])
        box.addWidget(self.grab)
        layout.addWidget(frame)

        frame, box = card()
        box.addWidget(label("Keys", "heading"))
        box.addWidget(label("Layer key: hold it to give every other key a second set of actions", "small"))
        self.layer_choices = [None] + ui_common.LAYER_KEY_CHOICES
        self.layer_key = QComboBox()
        self.layer_key.addItems(["Off"] + ui_common.LAYER_KEY_CHOICES)
        self.layer_key.setCurrentIndex(self.layer_choices.index(cfg.get("layer_key")))
        box.addWidget(self.layer_key)
        self.feedback = QCheckBox("On-screen confirmations (e.g. “Recording” when OBS starts recording)")
        self.feedback.setChecked(cfg.get("feedback", True))
        box.addWidget(self.feedback)
        box.addWidget(label("Appearance of this window", "small"))
        self.appearance = QComboBox()
        self.appearance.addItems([text for _, text in APPEARANCES])
        self.appearance.setCurrentIndex([k for k, _ in APPEARANCES].index(cfg.get("appearance", "auto")))
        box.addWidget(self.appearance)
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
        add = QPushButton("Add")
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
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(s.get("port", 4455)))
        self.password = QLineEdit(s.get("password", ""))
        self.password.setEchoMode(QLineEdit.Password)
        for text, widget in (("Host", self.host), ("Port", self.port), ("Password", self.password)):
            box.addWidget(label(text, "small"))
            box.addWidget(widget)
        test_row = QHBoxLayout()
        test = QPushButton("Test connection")
        test.clicked.connect(self.test_obs)
        self.obs_result = label("", "dim")
        test_row.addWidget(test)
        test_row.addWidget(self.obs_result, 1)
        box.addLayout(test_row)
        layout.addWidget(frame)
        layout.addStretch()

        scroll.setWidget(page)
        outer.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
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
            switch = QCheckBox(name)
            switch.setChecked(state.get(name, False))
            switch.toggled.connect(lambda on, n=name: modes.set_mode(n, on))
            remove = QPushButton("Remove")
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

    def values(self):
        return {"device": self.device, "grab": self.grab.isChecked(),
                "layer_key": self.layer_choices[self.layer_key.currentIndex()],
                "feedback": self.feedback.isChecked(),
                "appearance": APPEARANCES[self.appearance.currentIndex()][0],
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
            picker = QComboBox()
            picker.addItems(["—"] + [f"{t[:40]}  ({c})" for c, t in windows])
            picker.currentIndexChanged.connect(lambda i: i > 0 and self._add_class(windows[i - 1][0]))
            layout.addWidget(picker)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Save" if index else "Create")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
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
