"""The first-run welcome: find the numpad, pick a starting point, press a key to see it work."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QRadioButton, QSizePolicy,
                               QStackedWidget, QVBoxLayout)

from numpadctl import actions, presets

from .buttons import PushButton
from .widgets import card, label

# (name, what it does, the starter preset it applies or None)
CHOICES = [
    ("Streaming", "Go live, record, switch scenes, mute the mic (OBS)", "Streaming (OBS)"),
    ("Music and media", "Play, skip, volume, mute", "Media and volume"),
    ("Everyday shortcuts", "Copy, paste, undo, save, screenshots", "Editing"),
    ("Start empty", "Set every key up yourself", None),
]
DEFAULT_CHOICE = 1  # media keys: harmless if pressed by accident
TEST_KEY = "5"


def chip(text, kind):
    widget = label(text, kind)
    widget.setContentsMargins(12, 4, 12, 4)
    widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return widget


def set_chip(widget, text, kind):
    widget.setText(text)
    widget.setObjectName(kind)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ChoiceCard(QFrame):
    """A whole card you can click to pick it."""

    def __init__(self, name, description):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        self.radio = QRadioButton()
        row.addWidget(self.radio)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label(name))
        text.addWidget(label(description, "small", wrap=True))
        row.addLayout(text, 1)
        for child in self.findChildren(QFrame):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def mousePressEvent(self, event):
        self.radio.setChecked(True)


class WelcomeDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.chosen = DEFAULT_CHOICE
        self.test_key = None
        self.setWindowTitle("Welcome to NumpadPilot")
        self.resize(560, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)
        dots = QHBoxLayout()
        dots.addStretch()
        self.dots = [label("○", "dim") for _ in range(3)]
        for dot in self.dots:
            dots.addWidget(dot)
        dots.addStretch()
        layout.addLayout(dots)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)
        self.intro = label("", "dim", wrap=True)
        self.intro.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.intro)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._connect_page())
        self.pages.addWidget(self._choice_page())
        self.pages.addWidget(self._try_page())
        layout.addWidget(self.pages, 1)

        row = QHBoxLayout()
        self.back = PushButton("Back")
        self.back.setObjectName("flat")
        self.back.clicked.connect(lambda: self.go(self.pages.currentIndex() - 1))
        row.addWidget(self.back)
        row.addStretch()
        self.next = PushButton("Next")
        self.next.setObjectName("primary")
        self.next.setDefault(True)
        self.next.clicked.connect(self.advance)
        row.addWidget(self.next)
        layout.addLayout(row)

        window.tour = self
        self.go(0)
        self.refresh_status()

    # ---------------------------------------------------------------- pages
    def _connect_page(self):
        frame, inner = card()
        inner.addWidget(label("Plug in your numpad", "heading"))
        inner.addWidget(label("Press any key on it. We'll find it by itself.", "dim", wrap=True))
        self.status = chip("", "warn")
        inner.addWidget(self.status)
        inner.addWidget(label("Not showing up? Try another USB port, then press a key again.", "small", wrap=True))
        buttons = QHBoxLayout()
        diagnostics = PushButton("Run diagnostics")
        diagnostics.setObjectName("flat")
        diagnostics.clicked.connect(self.window.open_diagnostics)
        buttons.addWidget(diagnostics)
        self.start = PushButton("Start the service")
        self.start.setObjectName("flat")
        self.start.clicked.connect(self.window.start_service)
        buttons.addWidget(self.start)
        buttons.addStretch()
        inner.addLayout(buttons)
        inner.addStretch()
        return frame

    def _choice_page(self):
        frame, inner = card()
        inner.addWidget(label("What will you use it for?", "heading"))
        group = QButtonGroup(self)
        for index, (name, description, _) in enumerate(CHOICES):
            item = ChoiceCard(name, description)
            group.addButton(item.radio, index)
            item.radio.setChecked(index == DEFAULT_CHOICE)
            inner.addWidget(item)
        group.idClicked.connect(lambda index: setattr(self, "chosen", index))
        inner.addStretch()
        return frame

    def _try_page(self):
        frame, inner = card()
        inner.addWidget(label("Try a key", "heading"))
        self.try_text = label("", "dim", wrap=True)
        inner.addWidget(self.try_text)
        self.try_result = chip("Waiting for a key…", "warn")
        inner.addWidget(self.try_result)
        inner.addWidget(label("Tip: while this window is in front, keys only show up here. "
                              "They run their action the rest of the time.", "small", wrap=True))
        inner.addStretch()
        return frame

    # ---------------------------------------------------------------- flow
    def go(self, index):
        if index < 0:
            return
        self.pages.setCurrentIndex(index)
        titles = (("Welcome to NumpadPilot", "Turn a cheap numpad into a control deck. This takes about a minute."),
                  ("Pick a starting point", "You can change every key later. Nothing here is permanent."),
                  ("Try it", "Press a key and see it register."))
        self.title.setText(titles[index][0])
        self.intro.setText(titles[index][1])
        for i, dot in enumerate(self.dots):
            dot.setText("●" if i == index else "○")
        self.back.setText("Skip" if index == 0 else "Back")
        self.back.clicked.disconnect()
        self.back.clicked.connect(self.reject if index == 0 else lambda: self.go(index - 1))
        self.next.setText("Finish" if index == 2 else "Next")
        self.window.sync_capture()  # keys are only reported (not run) on the last page

    def advance(self):
        index = self.pages.currentIndex()
        if index == 1:
            self.apply_choice()
        if index == 2:
            self.accept()
        else:
            self.go(index + 1)

    def apply_choice(self):
        name = CHOICES[self.chosen][2]
        self.test_key = None
        if name:
            preset = presets.BY_NAME[name]
            added, _ = presets.apply(preset, self.window.keymap())
            if added:
                self.window.mark_dirty()
                self.window.refresh_pad()
                self.window.build_editor()
                self.window.save()
            self.test_key = TEST_KEY if TEST_KEY in preset.keys else next(iter(preset.keys))
            action_id = preset.keys[self.test_key]["tap"][0]
            self.try_text.setText(f"Press key {self.test_key} on your numpad. "
                                  f"It's set to “{actions.BY_ID[action_id].label}”.")
        else:
            self.try_text.setText("Press any key on your numpad. Every key is empty, so it will just register.")
        set_chip(self.try_result, "Waiting for a key…", "warn")

    def wants_capture(self):
        return self.pages.currentIndex() == 2

    # ---------------------------------------------------------------- service events
    def refresh_status(self):
        state = self.window.last_status
        self.start.setVisible(not state.get("running"))
        if not state.get("running"):
            set_chip(self.status, "The background service isn't running", "bad")
        elif state.get("connected"):
            devices = state.get("devices") or ["numpad"]
            set_chip(self.status, f"✓  {min(devices, key=len)} connected", "ok")
        else:
            set_chip(self.status, "Waiting for a numpad…", "warn")

    def on_key(self, key):
        if self.pages.currentIndex() != 2:
            return
        if self.test_key is None or key == self.test_key:
            set_chip(self.try_result, f"🎉  You pressed {key}. It works!", "ok")
        else:
            set_chip(self.try_result, f"You pressed {key}. Try key {self.test_key}.", "warn")

    def done(self, result):
        self.window.tour = None
        self.window.cfg["welcomed"] = True
        self.window.save_welcomed()
        self.window.sync_capture()
        super().done(result)
