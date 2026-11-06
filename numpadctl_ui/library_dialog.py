"""Profile ⋯ → Browse library…: pick a ready-made profile from the library (numpadctl/library.py)."""

import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from numpadctl import actions, library
from .buttons import ComboBox, PushButton
from .widgets import Dispatcher, label


class LibraryDialog(QDialog):
    """Browse the library and pick a profile. ask() returns (entry, file text) or None.

    The list and the chosen file are fetched in the background (`run` starts the work; tests pass one that
    runs it at once). The text then goes through the same importer and confirmation as a file from disk."""

    FILTERS = [("all", "All profiles"), ("official", "Official"), ("community", "Community")]

    def __init__(self, parent, fetch_index=None, fetch_profile=None, run=None):
        super().__init__(parent)
        self.fetch_index = fetch_index or library.fetch_index
        self.fetch_profile = fetch_profile or library.fetch_profile
        self.run = run or (lambda work: threading.Thread(target=work, daemon=True).start())
        self.dispatch = Dispatcher()
        self.entries, self.shown = [], []
        self.result_entry = self.result_text = None
        self.closed = False
        self.setWindowTitle("Profile library")
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(label("Profile library", "title"))
        layout.addWidget(label(f"Ready-made profiles from {library.describe_source()}. Before one is added you "
                               "see what it will do, like any imported profile.", "dim", wrap=True))
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: an app, a job, a tag…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        row.addWidget(self.search, 1)
        self.tier = ComboBox()
        for _, text in self.FILTERS:
            self.tier.addItem(text)
        self.tier.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.tier)
        layout.addLayout(row)
        self.status = label("", "dim", wrap=True)
        layout.addWidget(self.status)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.on_selected)
        self.list.itemDoubleClicked.connect(lambda _: self.import_selected())
        layout.addWidget(self.list, 1)
        self.details = label("", "small", wrap=True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox()
        self.retry = PushButton("Try again")
        self.retry.clicked.connect(self.load)
        buttons.addButton(self.retry, QDialogButtonBox.ActionRole)
        self.import_button = PushButton("Import…")
        self.import_button.setObjectName("primary")
        self.import_button.setDefault(True)
        self.import_button.clicked.connect(self.import_selected)
        buttons.addButton(self.import_button, QDialogButtonBox.ActionRole)
        buttons.addButton(PushButton("Close"), QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.load()

    # ---------------------------------------------------------------- background work
    def _background(self, work, done, failed):
        def go():
            try:
                result = work()
            except library.LibraryError as e:
                self.dispatch(self._finish, failed, str(e))
            except Exception as e:  # a bug, or something odd from the network: say so, don't crash the window
                self.dispatch(self._finish, failed, f"something went wrong ({e})")
            else:
                self.dispatch(self._finish, done, result)
        self.run(go)

    def _finish(self, fn, value):
        if not self.closed:  # the window was closed while it was fetching
            fn(value)

    def done(self, code):
        self.closed = True
        super().done(code)

    # ---------------------------------------------------------------- the list
    def load(self):
        self.status.setText("Getting the list of profiles…")
        self.retry.hide()
        self.import_button.setEnabled(False)
        self.entries, self.shown = [], []
        self.list.clear()
        self.details.setText("")
        self._background(self.fetch_index, self.loaded, self.load_failed)

    def loaded(self, entries):
        self.entries = entries
        self.refresh()

    def load_failed(self, message):
        self.status.setText(f"Couldn't get the library: {message}.")
        self.retry.show()

    def refresh(self):
        tier = self.FILTERS[self.tier.currentIndex()][0]
        search = self.search.text()
        shown = [e for e in self.entries if (tier == "all" or e.tier == tier) and e.matches(search)]
        shown.sort(key=lambda e: (not e.fits_this_computer, e.needs_newer_app))  # stable: official first stays
        self.shown = shown
        self.list.clear()
        for entry in shown:
            self.list.addItem(QListWidgetItem(f"{entry.name}\n{self.byline(entry)}"))
        if not self.entries:
            self.status.setText("The library has no profiles yet.")
        elif not shown:
            self.status.setText("No profile matches that.")
        else:
            self.status.setText(f"{len(shown)} of {len(self.entries)} profiles")
        if shown:
            self.list.setCurrentRow(0)
        else:
            self.on_selected(-1)

    @staticmethod
    def byline(entry):
        parts = ["Official" if entry.tier == "official" else f"by @{entry.author or 'someone'}"]
        if entry.platforms:
            parts.append(", ".join(library.PLATFORMS[p] for p in entry.platforms))
        parts.append(f"{entry.keys} keys")
        if entry.risky_actions:
            parts.append(f"⚠ {len(entry.risky_actions)}")
        if entry.needs_newer_app:
            parts.append(f"needs NumpadControl {entry.min_app_version}")
        elif not entry.fits_this_computer:
            parts.append("not made for this computer")
        return "  ·  ".join(parts)

    def current(self):
        row = self.list.currentRow()
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def on_selected(self, _row):
        entry = self.current()
        self.import_button.setEnabled(bool(entry) and not entry.needs_newer_app)
        if entry is None:
            self.details.setText("")
            return
        lines = [entry.description] if entry.description else []
        lines.append(f"Switches on in: {', '.join(entry.match)}" if entry.match else
                     "General: it doesn't switch on by itself. After importing, copy its keys into Default "
                     "or give it a window class (Edit profile…).")
        if entry.requires:
            lines.append("Needs: " + "; ".join(entry.requires))
        if entry.risky_actions:
            names = [actions.BY_ID[a].label if a in actions.BY_ID else a for a in entry.risky_actions]
            lines.append("⚠ " + ", ".join(names) + " (they run programs, press keys for you, or power the PC off)")
        if entry.needs_newer_app:
            lines.append(f"Made for NumpadControl {entry.min_app_version} or newer: update to import it.")
        self.details.setText("\n".join(lines))

    # ---------------------------------------------------------------- import
    def import_selected(self):
        entry = self.current()
        if entry is None or not self.import_button.isEnabled():
            return
        self.import_button.setEnabled(False)
        self.status.setText(f"Getting “{entry.name}”…")

        def got(text):
            self.result_entry, self.result_text = entry, text
            self.accept()

        def failed(message):
            self.status.setText(f"Couldn't get “{entry.name}”: {message}.")
            self.import_button.setEnabled(True)

        self._background(lambda: self.fetch_profile(entry), got, failed)

    @classmethod
    def ask(cls, parent, **kwargs):
        dialog = cls(parent, **kwargs)
        if dialog.exec() == QDialog.Accepted and dialog.result_text is not None:
            return dialog.result_entry, dialog.result_text
        return None
