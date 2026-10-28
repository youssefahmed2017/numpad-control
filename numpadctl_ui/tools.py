"""Diagnostics report and key tester."""

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from numpadctl import diagnostics, ui_common
from .widgets import label
from .buttons import ComboBox, Menu, PushButton, SmoothScrollArea, ToolButton


def _monospace(edit):
    edit.setReadOnly(True)
    edit.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    return edit


class DiagnosticsDialog(QDialog):
    """Everything about this install in one block of text, with a Copy button."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Diagnostics")
        self.resize(760, 640)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Paste this into a bug report. It never contains passwords.", "dim"))
        self.text = _monospace(QPlainTextEdit())
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.copy_button = PushButton("Copy")
        self.copy_button.clicked.connect(self.copy)
        refresh = PushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        close = PushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addWidget(refresh)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        self.text.setPlainText("Collecting…")
        window = self.window
        from numpadctl import config
        cfg = config.load()
        status = window.last_status
        ui_common.run_in_background(lambda: diagnostics.collect(cfg, status), self._show, window.dispatch)

    def _show(self, report, error):
        self.text.setPlainText(report if error is None else f"Could not collect the report: {error}")

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_button.setText("Copied ✓")


class KeyTesterDialog(QDialog):
    """Live: what the numpad sends (raw) and what the service makes of it (→)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.last = None
        self.setWindowTitle("Key tester")
        self.resize(460, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Press keys on the numpad. Each press and release is listed with the time since "
                               "the one before; → shows what the service made of it (e.g. 000).", "dim", wrap=True))
        self.text = _monospace(QPlainTextEdit())
        self.text.setMaximumBlockCount(500)
        layout.addWidget(self.text, 1)
        self.state = label("", "small")
        layout.addWidget(self.state)
        row = QHBoxLayout()
        clear = PushButton("Clear")
        clear.clicked.connect(self.text.clear)
        close = PushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(clear)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.finished.connect(lambda _: window.link.send({"cmd": "raw", "on": False}))
        self.start()

    def start(self):
        if self.window.link.connected:
            self.window.link.send({"cmd": "raw", "on": True})
            self.state.setText("Listening…")
        else:
            self.state.setText("The background service isn't running, so there is nothing to listen to.")

    def add_raw(self, key, down, t):
        gap = "" if self.last is None else f"+{(t - self.last) * 1000:6.0f} ms"
        self.last = t
        self.text.appendPlainText(f"{gap:>12}  {key:<10} {'pressed' if down else 'released'}")

    def add_key(self, key):
        self.text.appendPlainText(f"{'':>12}  → {key}")
