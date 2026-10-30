"""The settings window: the numpad on the left, the selected key's editor on the right."""

import copy

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from numpadctl import actions, config, keys, presets, ui_common
from numpadctl.platform import IS_WINDOWS
from . import dialogs, effects, egg, secret, theme, tokens, tools, welcome
from .buttons import ComboBox, Menu, PushButton, SmoothScrollArea, ToolButton, _Morph
from .picker import ActionPicker
from .widgets import Dispatcher, add_param_widgets, card, label

FLASH_MS = 250
KEY_FADE_MS = 160
KEY_RADIUS = 20
KEY_HOVER_RADIUS = 30
KEY_PRESSED_RADIUS = 10
DEFAULTS_LOOK = {"appearance": "auto", "accent": tokens.DEFAULT_ACCENT, "contrast": "standard"}


class KeyButton(_Morph, QPushButton):
    """A numpad key: its name, and below it what it does (a compact key of a keyboard picture shows only its
    name; what it does is in the tooltip and a tinted tile)."""

    def __init__(self, key, name=None, compact=False):
        super().__init__()
        self.key = key
        self.compact = compact
        self.setObjectName("numkey")
        self.setProperty("compact", compact)
        self._morph_setup()  # hover and press animation (buttons.py)
        self._sel = 0.0      # 0..1, animated
        self._sel_animation = self._animation(lambda v: setattr(self, "_sel", v))
        self.setToolTip(name or key)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # Enter fills its two rows
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*(1, 1, 1, 1) if compact else (4, 4, 4, 4))
        layout.setSpacing(0)
        self.name = label(name or ui_common.KEY_LABELS.get(key, key), "keyname")
        self.action = label("", "keyaction")
        for part in (self.name, self.action):
            part.setAlignment(Qt.AlignCenter)
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(part)
        self.action.setVisible(not compact)

    def _animation(self, apply):
        animation = QVariantAnimation(self, duration=KEY_FADE_MS)
        animation.valueChanged.connect(lambda value: (apply(value), self.update()))
        return animation

    def _fade(self, animation, current, target):
        animation.stop()
        animation.setStartValue(float(current))
        animation.setEndValue(float(target))
        animation.start()

    def _set(self, prop, value):
        if self.property(prop) == value:  # re-styling is slow: only when something changed
            return
        self.setProperty(prop, value)
        for widget in (self, self.name, self.action):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    def set_selected(self, on):
        if bool(self.property("selected")) != on:
            self._fade(self._sel_animation, self._sel, on)
        self._set("selected", on)

    def flash(self):
        self._set("flash", True)
        QTimer.singleShot(FLASH_MS, lambda: self._set("flash", False))

    def current_radius(self):
        """Rounded tile at rest, rounder on hover, squeezed while pressed (like the other buttons)."""
        radius = KEY_RADIUS + (KEY_HOVER_RADIUS - KEY_RADIUS) * self._hover
        radius += (KEY_PRESSED_RADIUS - radius) * self._press
        return radius * 0.35 if self.compact else radius

    def ripple_color(self):
        c = theme.current
        return QColor(c["onPrimaryContainer" if self.property("selected") else "onSurface"] if c else "#000000")

    def paintEvent(self, event):
        """The tile: tonal container, state layers that fade in and out, a selected look that cross-fades."""
        c = theme.current
        if not c:
            return super().paintEvent(event)
        resting = c["tertiaryContainer"] if self.property("layer") else c["surfaceContainerHigh"]
        content = c["onTertiaryContainer"] if self.property("layer") else c["onSurface"]
        if self.property("bound") and not self.property("layer"):  # a key of a keyboard picture that does something
            resting, content = c["secondaryContainer"], c["onSecondaryContainer"]
        look = tokens.blend(resting, content, tokens.STATE["hover"] * self._hover)
        chosen = tokens.blend(c["primaryContainer"], c["onPrimaryContainer"], tokens.STATE["hover"] * self._hover)
        color = QColor(tokens.blend(look, chosen, self._sel))
        color = QColor(tokens.blend(color.name(), content, tokens.STATE["pressed"] * min(1.0, max(0.0, self._press))))
        self._update_press()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        top = QColor(tokens.blend(color.name(), "#ffffff", 0.05))  # the same barely-there gradient as the app bar
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        radius = self.current_radius()
        painter.drawRoundedRect(rect, radius, radius)
        if self.property("flash"):
            painter.setPen(QPen(QColor(c["primary"]), 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)


class MainWindow(QMainWindow):
    def __init__(self, keep_running=False):
        super().__init__()
        self.setWindowTitle("NumpadPilot")
        self.resize(1120, 760)
        self.keep_running = keep_running  # closing only hides the window
        self.dispatch = Dispatcher()
        self.first_run = not config.CONFIG_PATH.exists()  # a new install gets the welcome
        self.cfg = config.load()
        self.tour = None  # the open WelcomeDialog
        self.egg_keys = egg.Matcher()
        self.combo = egg.Combo()  # numpad then keyboard: opens the secret panel
        self.secret = None  # the open SecretPanel
        self.last_key_press = None
        self.profile_index, self.layer, self.selected = 0, False, None
        self.device = ""  # the id of the keyboard shown on the left ("" is the numpad)
        self.dirty = False
        self.on_detected = None
        self.last_status = {"running": False}
        self.tester = None
        self.key_buttons = {}

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 8)
        outer.setSpacing(12)
        self.appbar = self._build_header()
        outer.addWidget(self.appbar)
        outer.addWidget(self._build_banner())
        body = QHBoxLayout()
        body.addWidget(self._build_left())
        line = QFrame()
        line.setObjectName("separator")
        body.addWidget(line)
        self.editor_scroll = SmoothScrollArea()
        self.editor_scroll.setWidgetResizable(True)
        body.addWidget(self.editor_scroll, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        effects.elevate(self.appbar, 1, dark=theme.current.get("surface", "#000000") < "#808080")

        def restyle(c):
            try:
                effects.elevate(self.appbar, 1, dark=c["surface"] < "#808080")
            except RuntimeError:  # this window is gone
                theme.listeners.remove(restyle)
        theme.listeners.append(restyle)

        self.refresh_profiles()
        self.refresh_layer_switch()
        self.select("1")
        self.link = ui_common.ServiceLink(self.on_service_message, self.dispatch)
        QApplication.instance().installEventFilter(self)

    # ---------------------------------------------------------------- layout
    def _build_header(self):
        """The top app bar: name, connection status, tools, Settings and Save."""
        bar = QFrame()
        bar.setObjectName("appbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 8, 12, 8)
        row.setSpacing(8)
        row.addWidget(label("NumpadPilot", "appname"))
        self.status = label("Connecting…", "dim")
        self.status.setContentsMargins(10, 4, 10, 4)  # the chip's padding (a stylesheet padding doesn't size a label)
        row.addWidget(self.status)
        row.addStretch()
        self.dirty_label = label("", "dim")
        row.addWidget(self.dirty_label)
        self.learn = ToolButton(text="⌨ Learn")
        self.learn.setCheckable(True)
        self.learn.setToolTip("Learn mode: press a numpad key to select it here (its action won't run)")
        self.learn.toggled.connect(self.on_learn_toggled)
        row.addWidget(self.learn)
        extra = ToolButton(text="Tools ▾")
        extra.setPopupMode(QToolButton.InstantPopup)
        menu = Menu(extra)
        menu.addAction("Key tester…", self.open_tester)
        menu.addAction("Diagnostics…", self.open_diagnostics)
        menu.addAction("Welcome tour…", self.open_welcome)
        menu.addSeparator()
        self.follow = menu.addAction("Select a key when I press it")
        self.follow.setCheckable(True)
        self.follow.setChecked(True)
        self.follow.setToolTip("While this window is in front, pressing a numpad key selects it here "
                               "instead of running its action")
        self.follow.toggled.connect(lambda _: self.sync_capture())
        extra.setMenu(menu)
        row.addWidget(extra)
        settings = PushButton("Settings")
        settings.clicked.connect(self.open_settings)
        row.addWidget(settings)
        self.save_button = PushButton("Save")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)
        return bar

    def _build_banner(self):
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        row = QHBoxLayout(self.banner)
        row.addWidget(label("The background service isn't running, so the numpad does nothing."), 1)
        start = PushButton("Start service")
        start.clicked.connect(self.start_service)
        row.addWidget(start)
        self.banner.hide()
        return self.banner

    def _build_left(self):
        panel = QWidget()
        panel.setObjectName("left_panel")
        panel.setFixedWidth(470)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 14, 8)
        layout.setSpacing(10)

        profiles = QHBoxLayout()
        profiles.addWidget(label("Profile", "heading"))
        self.profile_combo = ComboBox()
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        profiles.addWidget(self.profile_combo, 1)
        menu_button = ToolButton(text="⋯", toolTip="Profiles: different keys per app")
        menu_button.setPopupMode(QToolButton.InstantPopup)
        menu = Menu(menu_button)
        menu.addAction("New profile…", lambda: self.profile_dialog(None))
        menu.addAction("Duplicate profile…", lambda: self.profile_dialog(None, copy_from=self.profile_index))
        menu.addAction("Edit profile…", lambda: self.profile_dialog(self.profile_index))
        menu.addAction("Delete profile", self.delete_profile)
        menu.addSeparator()
        menu.addAction("Add a starter preset…", self.add_preset)
        menu_button.setMenu(menu)
        profiles.addWidget(menu_button)
        layout.addLayout(profiles)

        self.device_row = QWidget()
        devices = QHBoxLayout(self.device_row)
        devices.setContentsMargins(0, 0, 0, 0)
        devices.addWidget(label("Device", "heading"))
        self.device_combo = ComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        devices.addWidget(self.device_combo, 1)
        device_button = ToolButton(text="⋯", toolTip="Use a keyboard as an extra pad")
        device_button.setPopupMode(QToolButton.InstantPopup)
        device_menu = Menu(device_button)
        device_menu.addAction("Add a keyboard…", self.add_device)
        self.grab_action = device_menu.addAction("Stop this keyboard typing")
        self.grab_action.setCheckable(True)
        self.grab_action.setToolTip("On: its keys only run actions. Holding Ctrl+Alt+Esc on it gives it back.")
        self.grab_action.toggled.connect(self.on_grab_toggled)
        self.remove_device_action = device_menu.addAction("Remove this keyboard", self.remove_device)
        device_button.setMenu(device_menu)
        devices.addWidget(device_button)
        layout.addWidget(self.device_row)
        self.device_row.setVisible(not IS_WINDOWS)  # extra keyboards are Linux-only so far

        self.layer_frame = QFrame()
        self.layer_frame.setObjectName("segments")
        segments = QHBoxLayout(self.layer_frame)
        segments.setContentsMargins(3, 3, 3, 3)
        group = QButtonGroup(self)
        for i, text in enumerate(("Normal", "Layer (key held)")):
            button = PushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(i == 0)
            group.addButton(button, i)
            segments.addWidget(button)
        group.idToggled.connect(lambda i, on: on and self.on_layer_changed(i == 1))
        self.layer_group = group
        layout.addWidget(self.layer_frame)

        self.pad_stack = QStackedWidget()
        self.pad_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        numpad_page = QWidget()
        page_layout = QVBoxLayout(numpad_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(8)
        for key, row, col, span in ui_common.LAYOUT:
            button = KeyButton(key)
            button.clicked.connect(lambda _=False, k=key: self.select(k))
            grid.addWidget(button, row, col, span, 1)
            self.key_buttons[key] = button
        page_layout.addLayout(grid)

        self.extra_title = label("Extra keys", "heading")
        page_layout.addWidget(self.extra_title)
        self.extra_grid = QGridLayout()
        self.extra_grid.setSpacing(8)
        page_layout.addLayout(self.extra_grid)
        self.pad_stack.addWidget(numpad_page)

        keyboard_page = QWidget()
        page_layout = QVBoxLayout(keyboard_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        self.keyboard_grid = QGridLayout()
        self.keyboard_grid.setSpacing(3)
        page_layout.addLayout(self.keyboard_grid)
        self.keyboard_extra_title = label("Other keys of this keyboard", "heading")
        page_layout.addWidget(self.keyboard_extra_title)
        self.keyboard_extra_grid = QGridLayout()
        self.keyboard_extra_grid.setSpacing(8)
        page_layout.addLayout(self.keyboard_extra_grid)
        self.pad_stack.addWidget(keyboard_page)
        layout.addWidget(self.pad_stack)
        self.rebuild_extras()
        self.refresh_devices()

        self.pad_help = label("", "small", wrap=True)
        layout.addWidget(self.pad_help)
        self.set_pad_help()
        layout.addStretch()
        return panel

    # ---------------------------------------------------------------- extra keys
    EXTRA_COLUMNS = 4

    def rebuild_extras(self):
        """The pad's extra keys (added in Learn mode) below the standard ones."""
        for key in [k for k in self.key_buttons if k not in keys.BUILTIN and not keys.split(k)[0]]:
            self.key_buttons.pop(key).deleteLater()
        for i in reversed(range(self.extra_grid.count())):
            self.extra_grid.takeAt(i)
        for index, extra in enumerate(self.cfg.get("extra_keys", [])):
            button = KeyButton(extra["id"], extra.get("label") or keys.label_for(extra["id"]))
            button.clicked.connect(lambda _=False, k=extra["id"]: self.select(k))
            self.extra_grid.addWidget(button, index // self.EXTRA_COLUMNS, index % self.EXTRA_COLUMNS)
            self.key_buttons[extra["id"]] = button
        self.extra_title.setVisible(bool(self.cfg.get("extra_keys")))

    def extra_list(self, key):
        """Where the extra keys of this key's device are kept in the config."""
        device = keys.split(key)[0]
        return keys.device_extras(self.cfg, device) if device else self.cfg.setdefault("extra_keys", [])

    def add_extra_key(self, key, name=None):
        device = keys.split(key)[0]
        if device and key in self.key_buttons or not device and keys.known(key, self.cfg):
            return
        self.extra_list(key).append({"id": key, "label": name or keys.label_for(key)})
        self.rebuild_extras()
        self.rebuild_device_extras()
        self.mark_dirty()
        self.refresh_pad()

    def rename_extra_key(self, key, name):
        for extra in self.extra_list(key):
            if extra["id"] == key:
                extra["label"] = name
        button = self.key_buttons.get(key)
        if button:
            button.name.setText(name or keys.label_for(key))
            button.setToolTip(name or key)
        self.mark_dirty()

    def remove_extra_key(self, key):
        device = keys.split(key)[0]
        remaining = [e for e in self.extra_list(key) if e["id"] != key]
        if device:
            self.device_config()["extra_keys"] = remaining
        else:
            self.cfg["extra_keys"] = remaining
        if self.cfg.get("layer_key") == key:
            self.cfg["layer_key"] = None
            self.refresh_layer_switch()
        self.rebuild_extras()
        self.rebuild_device_extras()
        self.mark_dirty()
        self.select(self.default_key())

    # ---------------------------------------------------------------- extra keyboards
    def device_config(self):
        """The config entry of the keyboard shown now (None for the numpad)."""
        return next((d for d in self.cfg.get("devices", []) if d["id"] == self.device), None)

    def default_key(self):
        return f"{self.device}:KEY_ESC" if self.device else "1"

    def set_pad_help(self):
        if self.device:
            self.pad_help.setText("Click a key to choose what it does; tinted keys already do something. A key that "
                                  "isn't drawn (media keys…): turn on Learn and press it, and it's added below.")
        else:
            self.pad_help.setText("Click a key to choose what it does. A key that isn't here (a “(”, Tab, a macro key…): "
                                  "turn on Learn and press it, and it's added.")

    def refresh_devices(self):
        """The Device list: the numpad, then the keyboards added in the config."""
        devices = self.cfg.get("devices", [])
        if self.device and not self.device_config():
            self.device = ""
        extra = self.last_status.get("extra", {})
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Numpad")
        for device in devices:
            state = extra.get(device["id"], {})
            note = " (given back)" if state.get("released") else \
                " (not connected)" if state and not state.get("connected") else ""
            self.device_combo.addItem(device["name"] + note)
        self.device_combo.setCurrentIndex(1 + [d["id"] for d in devices].index(self.device) if self.device else 0)
        self.device_combo.blockSignals(False)
        config_entry = self.device_config()
        self.grab_action.blockSignals(True)
        self.grab_action.setChecked(bool(config_entry and config_entry.get("grab", True)))
        self.grab_action.blockSignals(False)
        self.grab_action.setEnabled(config_entry is not None)
        self.remove_device_action.setEnabled(config_entry is not None)

    def say_given_back(self, before, after):
        """A keyboard just went back to typing (its escape chord was held): say so here as well."""
        for device in self.cfg.get("devices", []):
            if after.get(device["id"], {}).get("released") and not before.get(device["id"], {}).get("released"):
                self.toast(f"{device['name']} is typing again (Ctrl+Alt+Esc). Remove it and add it again to use it as a pad.")

    def on_device_changed(self, index):
        devices = self.cfg.get("devices", [])
        self.set_device(devices[index - 1]["id"] if 0 < index <= len(devices) else "")

    def set_device(self, device):
        self.device = device
        for key in [k for k in self.key_buttons if keys.split(k)[0]]:
            self.key_buttons.pop(key).deleteLater()
        if device:
            self.build_keyboard()
        self.pad_stack.setCurrentIndex(1 if device else 0)
        self.pad_stack.currentWidget().adjustSize()
        self.pad_stack.setFixedHeight(self.pad_stack.currentWidget().sizeHint().height())
        self.centralWidget().findChild(QWidget, "left_panel").setFixedWidth(620 if device else 470)
        self.refresh_devices()
        self.set_pad_help()
        self.select(self.default_key())

    def build_keyboard(self):
        for i in reversed(range(self.keyboard_grid.count())):
            self.keyboard_grid.takeAt(i)
        for name, text, row, col, width, height in ui_common.KEYBOARD_LAYOUT:
            key = f"{self.device}:{name}"
            button = KeyButton(key, text, compact=True)
            button.clicked.connect(lambda _=False, k=key: self.select(k))
            self.keyboard_grid.addWidget(button, row, col, height, width)
            self.key_buttons[key] = button
        for column in range(60):
            self.keyboard_grid.setColumnStretch(column, 1)
        self.rebuild_device_extras()

    def rebuild_device_extras(self):
        """Keys of this keyboard that the picture doesn't have, added in Learn mode."""
        if not self.device:
            return
        for key in [k for k in self.key_buttons if keys.split(k)[0] and k not in self.layout_keys()]:
            self.key_buttons.pop(key).deleteLater()
        for i in reversed(range(self.keyboard_extra_grid.count())):
            self.keyboard_extra_grid.takeAt(i)
        extras = keys.device_extras(self.cfg, self.device)
        for index, extra in enumerate(extras):
            button = KeyButton(extra["id"], extra.get("label") or keys.label_for(extra["id"]))
            button.clicked.connect(lambda _=False, k=extra["id"]: self.select(k))
            self.keyboard_extra_grid.addWidget(button, index // self.EXTRA_COLUMNS, index % self.EXTRA_COLUMNS)
            self.key_buttons[extra["id"]] = button
        self.keyboard_extra_title.setVisible(bool(extras))

    def layout_keys(self):
        return {f"{self.device}:{name}" for name, *_ in ui_common.KEYBOARD_LAYOUT}

    def add_device(self):
        taken = {(self.cfg["device"]["vendor"], self.cfg["device"]["product"])}
        taken |= {(d["vendor"], d["product"]) for d in self.cfg.get("devices", [])}
        dialog = dialogs.AddDeviceDialog(self, taken, {d["id"] for d in self.cfg.get("devices", [])})
        if dialog.exec():
            spec = dialog.values()
            self.cfg.setdefault("devices", []).append(spec)
            self.mark_dirty()
            self.set_device(spec["id"])
            self.toast("Keyboard added. Save to start using it.")

    def remove_device(self):
        device = self.device_config()
        if device is None:
            return
        answer = QMessageBox.question(self, "Remove keyboard",
                                      f"Remove {device['name']} and the actions you set on its keys?")
        if answer != QMessageBox.Yes:
            return
        self.cfg["devices"].remove(device)
        for profile in self.cfg["profiles"]:
            for kind in ("bindings", "layer_bindings"):
                profile[kind] = {k: v for k, v in profile[kind].items() if keys.split(k)[0] != device["id"]}
        if keys.split(self.cfg.get("layer_key") or "")[0] == device["id"]:
            self.cfg["layer_key"] = None
            self.refresh_layer_switch()
        self.mark_dirty()
        self.set_device("")

    def on_grab_toggled(self, on):
        device = self.device_config()
        if device is not None:
            device["grab"] = on
            self.mark_dirty()

    # ---------------------------------------------------------------- model
    @property
    def profile(self):
        return self.cfg["profiles"][self.profile_index]

    def keymap(self):
        return self.profile["layer_bindings" if self.layer else "bindings"]

    def slot_binding(self, key, slot):
        return self.keymap().get(key, {}).get(slot) or ui_common.NONE_BINDING

    @staticmethod
    def slots_for(key):
        return ("tap",) if key in config.TAP_ONLY_KEYS else config.SLOTS

    def mark_dirty(self):
        self.dirty = True
        self.dirty_label.setText("Unsaved changes")

    # ---------------------------------------------------------------- the numpad
    def refresh_pad(self, only=None):
        """Update the keys' look and labels: all of them, or just `only` (typing changes one key)."""
        layer_key = self.cfg.get("layer_key")
        for key, button in ([(only, self.key_buttons[only])] if only in self.key_buttons else
                            [] if only else self.key_buttons.items()):
            button._set("layer", key == layer_key)
            if key == layer_key:
                text = "Layer key"
            else:
                tap = actions.BY_ID.get(self.slot_binding(key, "tap")["action"], actions.BY_ID["none"])
                extra = sum(actions.is_set(self.slot_binding(key, s)) for s in ("hold", "double"))
                text = "—" if tap.id == "none" else tap.label
                if extra:
                    text = ("" if tap.id == "none" else text + " ") + f"+{extra}"
            if button.compact:
                button._set("bound", text != "—" and key != layer_key)
                tip = f"{button.name.text()}: {text}"
                if button.toolTip() != tip:
                    button.setToolTip(tip)
            elided = button.action.fontMetrics().elidedText(text, Qt.ElideRight, 96)
            if button.action.text() != elided:
                button.action.setText(elided)
            button.set_selected(key == self.selected)

    def select(self, key):
        changed = key != self.selected
        self.selected = key
        self.refresh_pad()
        self.build_editor(fade=changed)

    # ---------------------------------------------------------------- the editor
    def build_editor(self, fade=False):
        key = self.selected
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 8, 14, 14)
        layout.setSpacing(12)
        device = self.device_config() if keys.split(key)[0] else None
        layout.addWidget(label(f"Key  {keys.display(key, self.cfg)}" + (f" on {device['name']}" if device else ""), "title"))
        context = self.profile["name"] + (" profile" if self.profile_index else " profile · applies everywhere")
        layout.addWidget(label(context + (" · layer" if self.layer else ""), "dim"))

        if key in keys.extra_ids(self.cfg) or key in (e["id"] for e in keys.device_extras(self.cfg, keys.split(key)[0])):
            frame, inner = card()
            inner.addWidget(label("Extra key", "heading"))
            inner.addWidget(label(f"Added in Learn mode (it reports itself as {key}).", "small"))
            row = QHBoxLayout()
            name = QLineEdit(keys.display(key, self.cfg))
            name.setAccessibleName("Key name")
            name.setPlaceholderText("Name shown on the pad")
            name.textEdited.connect(lambda text, k=key: self.rename_extra_key(k, text.strip()))
            row.addWidget(name, 1)
            remove = PushButton("Remove key")
            remove.setObjectName("flat")
            remove.clicked.connect(lambda _=False, k=key: self.remove_extra_key(k))
            row.addWidget(remove)
            inner.addLayout(row)
            layout.addWidget(frame)

        if key == self.cfg.get("layer_key"):
            frame, inner = card()
            inner.addWidget(label("This is your layer key", "heading"))
            inner.addWidget(label("Hold it and press another key to run that key's Layer actions. "
                                  "Change or turn it off in Settings.", "dim", wrap=True))
            layout.addWidget(frame)
        else:
            slots = self.slots_for(key)
            has_extra = any(actions.is_set(self.slot_binding(key, s)) for s in slots if s != "tap")
            for slot in slots:
                layout.addWidget(self._slot_card(key, slot, has_extra))
            if self.profile_index:
                layout.addWidget(label("Anything left as “(nothing)” here uses the Default profile's action.",
                                       "dim", wrap=True))
            if key == "000":
                layout.addWidget(label("The 000 key sends three 0s at once, so it can't be held or double-tapped.",
                                       "dim", wrap=True))
        layout.addStretch()
        old = self.editor_scroll.takeWidget()
        self.editor_scroll.setWidget(page)
        if fade:
            effects.fade_in(page)
        if old is not None:
            old.deleteLater()

    def _slot_card(self, key, slot, has_extra):
        binding = self.slot_binding(key, slot)
        action = actions.BY_ID.get(binding["action"], actions.BY_ID["none"])
        frame, layout = card()
        layout.addWidget(label(ui_common.SLOT_TITLES[slot], "heading"))
        layout.addWidget(label(ui_common.slot_description(slot, has_extra), "dim", wrap=True))

        layout.addWidget(label("Action", "small"))
        picker = ActionPicker(actions.ACTIONS, actions.ACTIONS.index(action), ui_common.ACTION_NAMES)
        picker.setAccessibleName(f"{ui_common.SLOT_TITLES[slot]} action")
        picker.picked.connect(lambda i: self.on_action_changed(slot, i))
        layout.addWidget(picker)
        hint = None
        if action.repeat and slot == "tap":
            hint = "Repeats while held"
        if action.confirm:
            how = {"tap": "Press once, then again", "hold": "Hold once, then hold again",
                   "double": "Double-tap, then double-tap again"}[slot]
            hint = f"{how} within {actions.CONFIRM_MAX_SECONDS:g} s to confirm"
        if hint:
            layout.addWidget(label(hint, "small"))

        if action.id != "none":
            add_param_widgets(layout, action, binding["params"], self, self.on_param_changed)
            if slot == "hold" and not action.confirm:
                rapid = QCheckBox("Rapid-fire after holding 2 s")
                rapid.setToolTip("Fires once, then keeps firing if you hold 2 more seconds")
                rapid.setChecked(actions.rapid_fire(binding))
                rapid.toggled.connect(lambda on: (binding.__setitem__("rapid", on), self.mark_dirty()))
                layout.addWidget(rapid)
            test = PushButton("▶ Test now")
            test.clicked.connect(lambda: self.test(slot))
            layout.addWidget(test)
        return frame

    def on_action_changed(self, slot, index):
        action = actions.ACTIONS[index]
        self.keymap().setdefault(self.selected, {})[slot] = ui_common.new_binding(action)
        self.mark_dirty()
        self.refresh_pad()
        QTimer.singleShot(0, self.build_editor)  # not while the dropdown's signal is running

    def on_param_changed(self):
        self.mark_dirty()
        self.refresh_pad(only=self.selected)

    # ---------------------------------------------------------------- profiles & layer
    def refresh_profiles(self):
        self.profile_combo.blockSignals(True)  # a new list isn't the user switching profiles
        self.profile_combo.clear()
        self.profile_combo.addItems([p["name"] for p in self.cfg["profiles"]])
        self.profile_index = min(self.profile_index, len(self.cfg["profiles"]) - 1)
        self.profile_combo.setCurrentIndex(self.profile_index)
        self.profile_combo.blockSignals(False)

    def on_profile_changed(self, index):
        if index >= 0 and index != self.profile_index:
            self.profile_index = index
            self.refresh_pad()
            self.build_editor()

    def refresh_layer_switch(self):
        has_layer = bool(self.cfg.get("layer_key"))
        self.layer_frame.setVisible(has_layer)
        if not has_layer and self.layer:
            self.layer_group.button(0).setChecked(True)

    def on_layer_changed(self, layer):
        self.layer = layer
        self.refresh_pad()
        self.build_editor()

    def profile_dialog(self, index, copy_from=None):
        if index == 0:
            self.toast("The Default profile always applies and can't be edited.")
            return
        result = dialogs.ProfileDialog.ask(self, self.cfg["profiles"], index, copy_from)
        if result is None:
            return
        name, classes = result
        if index:
            self.profile.update(name=name, match=classes)
        else:
            copied = self.cfg["profiles"][copy_from] if copy_from is not None else {}
            self.cfg["profiles"].append({"name": name, "match": classes,
                                         "bindings": copy.deepcopy(copied.get("bindings", {})),
                                         "layer_bindings": copy.deepcopy(copied.get("layer_bindings", {}))})
            self.profile_index = len(self.cfg["profiles"]) - 1
            if not classes:
                self.toast("It won't apply until you add a window class (Edit profile…)")
        self.mark_dirty()
        self.refresh_profiles()
        self.refresh_pad()
        self.build_editor()

    def add_preset(self):
        preset = dialogs.PresetDialog.ask(self, self.profile["name"])
        if preset is None:
            return
        added, kept = presets.apply(preset, self.keymap())
        if added:
            self.mark_dirty()
            self.refresh_pad()
            self.build_editor()
        self.toast(f"{preset.name}: {added} key actions added" + (f", {kept} kept as they were" if kept else ""))

    def delete_profile(self):
        if self.profile_index == 0:
            self.toast("The Default profile can't be deleted.")
            return
        answer = QMessageBox.question(self, "Delete profile", f"Delete “{self.profile['name']}”?\n"
                                      "Its key setup will be removed.")
        if answer == QMessageBox.Yes:
            del self.cfg["profiles"][self.profile_index]
            self.profile_index = 0
            self.mark_dirty()
            self.refresh_profiles()
            self.refresh_pad()
            self.build_editor()

    # ---------------------------------------------------------------- settings
    def open_settings(self):
        dialog = dialogs.SettingsDialog(self)
        dialog.exec()
        new = dialog.values()
        if any(self.cfg.get(k) != v for k, v in new.items()):
            look = ("appearance", "accent", "contrast")
            look_changed = any(new[k] != self.cfg.get(k, DEFAULTS_LOOK[k]) for k in look)
            self.cfg.update(new)
            self.mark_dirty()
            self.refresh_layer_switch()
            self.refresh_pad()
            self.build_editor()
            if look_changed:
                from . import theme
                from PySide6.QtWidgets import QApplication
                theme.apply(QApplication.instance(), new["appearance"], new["accent"], new["contrast"])

    # ---------------------------------------------------------------- tools
    def open_diagnostics(self):
        tools.DiagnosticsDialog(self).exec()

    def open_secret(self):
        if self.secret is None:
            secret.SecretPanel(self).show()  # not modal: other windows can sit above it

    def eventFilter(self, obj, event):
        """Letters typed on the keyboard count towards the secret combo, and towards "out" once the console is open
        (while one of our windows is in front)."""
        if (event.type() == QEvent.KeyPress and not event.isAutoRepeat()
                and (self.isActiveWindow() or (self.secret is not None and self.secret.isActiveWindow()))):
            # Qt hands the same key press to the window and then to each widget it passes through: count it once.
            once = (event.timestamp(), event.nativeScanCode(), event.key())
            if once == self.last_key_press:
                return super().eventFilter(obj, event)
            self.last_key_press = once
            letter = egg.letter_of(event)
            if letter and self.secret is not None:
                self.secret.on_letter(letter)
            elif letter and self.combo.press("key", letter):
                QTimer.singleShot(0, self.open_secret)
            elif letter and self.combo.progress > 3:
                self.toast(f"secret: {self.combo.progress - 3}/5")
        return super().eventFilter(obj, event)

    def open_welcome(self):
        if self.tour is None:
            welcome.WelcomeDialog(self).exec()

    def save_welcomed(self):
        if not self.dirty:  # remember the tour was seen (with nothing half-edited to write along)
            config.save(self.cfg)

    def showEvent(self, event):
        super().showEvent(event)
        if self.first_run and not self.cfg.get("welcomed"):
            self.first_run = False
            QTimer.singleShot(300, self.open_welcome)

    def open_tester(self):
        if self.tester is None:
            self.tester = tools.KeyTesterDialog(self)
            self.tester.finished.connect(lambda _: setattr(self, "tester", None))
        self.tester.show()
        self.tester.raise_()

    # ---------------------------------------------------------------- service link
    def on_service_message(self, message):
        event = message.get("event")
        if event == "status":
            self.say_given_back(self.last_status.get("extra", {}), message.get("extra", {}))
            self.last_status = message
            self.update_status(message)
            self.refresh_devices()
            if self.tour:
                self.tour.refresh_status()
            if self.tester:  # the service (re)started: ask for the raw keys again
                self.tester.start()
        elif event == "raw" and self.tester:
            self.tester.add_raw(message["key"], message["down"], message["t"])
        elif event == "key":
            if self.tester:
                self.tester.add_key(message["key"])
            key_device = keys.split(message["key"])[0]
            if self.learn.isChecked() and key_device == self.device and key_device and message["key"] not in self.key_buttons:
                self.add_extra_key(message["key"], message.get("label"))
                self.toast(f"Added the key “{keys.display(message['key'], self.cfg)}” to the keyboard")
            elif self.learn.isChecked() and message.get("unknown") and not keys.known(message["key"], self.cfg):
                self.add_extra_key(message["key"], message.get("label"))
                self.toast(f"Added the key “{keys.display(message['key'], self.cfg)}” to the pad")
            if key_device and key_device != self.device and key_device in keys.device_ids(self.cfg) \
                    and (self.learn.isChecked() or self.following_keys()):
                self.set_device(key_device)  # pressed on another keyboard: show that one
            elif not key_device and self.device and (self.learn.isChecked() or self.following_keys()):
                self.set_device("")
            if self.tour:
                self.tour.on_key(message["key"])
            if self.secret:
                self.secret.on_pad_key(message["key"])
            elif self.combo.press("pad", message["key"]):
                QTimer.singleShot(0, self.open_secret)
            elif self.combo.progress == 3:
                self.toast("secret: now the keyboard")
            if self.egg_keys.press(message["key"]):
                egg.Confetti(self.centralWidget(), text="KONAMI")
            button = self.key_buttons.get(message["key"])
            if button:
                button.flash()
            if message["key"] in self.key_buttons and (self.learn.isChecked() or self.following_keys()):
                self.select(message["key"])
        elif event == "detected" and self.on_detected:
            callback, self.on_detected = self.on_detected, None
            callback(message.get("spec"), None)

    def update_status(self, message):
        if not message.get("running"):
            self.status.setText("Service not running")
            self.status.setObjectName("bad")
            self.banner.show()
            if self.learn.isChecked():
                self.learn.setChecked(False)
        else:
            self.banner.hide()
            if message.get("connected"):
                devices = message.get("devices") or ["numpad"]
                self.status.setText(f"{min(devices, key=len)} connected")
                self.status.setObjectName("ok")
            else:
                self.status.setText("Numpad not plugged in")
                self.status.setObjectName("warn")
            self.sync_capture()  # reconnected: turn capture back on if it should be
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def following_keys(self):
        """True while the window is in front and pressed keys select instead of act."""
        return self.follow.isChecked() and self.isActiveWindow() and self.link.connected

    def sync_capture(self):
        """Keep the service in step: in Learn mode, or while this window is in front, keys report but don't run."""
        learn = self.learn.isChecked()
        self.link.send({"cmd": "capture", "on": learn or self.following_keys() or bool(self.tour and self.tour.wants_capture()) or self.secret is not None,
                        "learn": learn})

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and hasattr(self, "follow"):
            self.sync_capture()

    def on_learn_toggled(self, on):
        if on and not self.link.connected:
            self.toast("Learn mode needs the background service running.")
            self.learn.setChecked(False)
            return
        self.sync_capture()
        if on:
            self.toast("Learn mode: press a key on the numpad")

    def start_service(self):
        ui_common.start_service()
        self.toast("Starting the service…")

    def detect(self, done):
        """Find the numpad: via the service if it runs (it holds the device), else directly."""
        if self.link.connected:
            self.on_detected = done
            self.link.send({"cmd": "detect"})
        else:
            from numpadctl.platform import numpad_input
            ui_common.run_in_background(numpad_input.detect_device, done, self.dispatch)

    # ---------------------------------------------------------------- feedback
    def toast(self, message):
        self.statusBar().showMessage(message, 4000)

    def show_problems(self, problems, ok_message):
        if problems:
            QMessageBox.warning(self, "Problem", "\n".join(problems))
        else:
            self.toast(ok_message)

    def test(self, slot):
        key, binding = self.selected, self.slot_binding(self.selected, slot)
        if actions.BY_ID[binding["action"]].confirm:
            self.toast("Not run from here, to keep your session safe. On the numpad: press once, then again.")
            return
        self.toast(f"Running key {key} ({ui_common.SLOT_TITLES[slot].lower()})…")

        def done(output, error):
            if error:
                QMessageBox.warning(self, f"Key {key} failed", str(error))
            else:
                self.toast(f"Key {key} ran OK" + (f": {output}" if output else ""))
        ui_common.run_in_background(lambda: actions.run(self.cfg, binding), done, self.dispatch)

    # ---------------------------------------------------------------- save / close
    def save(self):
        for profile in self.cfg["profiles"]:
            for kind in ("bindings", "layer_bindings"):
                for key, slots in profile[kind].items():
                    for slot, binding in slots.items():
                        problems = actions.binding_problems(binding, self.cfg)
                        if problems:
                            QMessageBox.warning(self, "Can't save",
                                                f"{profile['name']}: key {key} ({ui_common.SLOT_TITLES[slot]}):\n\n"
                                                + "\n".join(problems))
                            return False
        for profile in self.cfg["profiles"]:  # drop empty slots and keys
            for kind in ("bindings", "layer_bindings"):
                profile[kind] = {key: kept for key, slots in profile[kind].items()
                                 if (kept := {s: b for s, b in slots.items() if actions.is_set(b)})}
        config.save(self.cfg)
        self.dirty = False
        self.dirty_label.setText("")
        self.toast("Saved. The service picks it up automatically.")
        return True

    def discard_changes(self):
        self.cfg = config.load()
        self.dirty = False
        self.dirty_label.setText("")
        self.refresh_profiles()
        self.refresh_layer_switch()
        self.refresh_devices()
        self.set_device(self.device)

    def closeEvent(self, event):
        if self.dirty:
            answer = QMessageBox.question(self, "Save changes?", "Your key setup has unsaved changes.",
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                          QMessageBox.Save)
            if answer == QMessageBox.Cancel or (answer == QMessageBox.Save and not self.save()):
                event.ignore()
                return
            if answer == QMessageBox.Discard:
                self.discard_changes()
        if self.learn.isChecked():
            self.learn.setChecked(False)  # never leave the numpad blocked while hidden
        if self.keep_running:
            event.ignore()
            self.hide()
        else:
            event.accept()
