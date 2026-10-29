"""The settings window app: one copy at a time, optional hidden start, tray icon."""

import getpass
import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from numpadctl import config, desktop, ui_common
from numpadctl.platform import IS_WINDOWS, paths
from . import effects, theme, tokens
from .window import MainWindow

PID_PATH = paths.runtime_dir() / "numpad-control-window.pid"  # for bar modules listing hidden apps


ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def draw_icon():
    """The NumpadPilot icon, from assets/ (one PNG per size so every spot gets a sharp one)."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addFile(str(ASSETS / f"icon-{size}.png"))
    return icon


def _server_name():
    return f"numpad-control-window-{getpass.getuser()}"


def run(args=()):
    hidden = "--hidden" in args
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NumpadPilot")
    app.setDesktopFileName(ui_common.APP_ID)  # the window's class on Wayland
    app.setQuitOnLastWindowClosed(False)

    # One copy at a time: a second launch asks the first to show its window.
    probe = QLocalSocket()
    probe.connectToServer(_server_name())
    if probe.waitForConnected(300):
        if not hidden:
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(_server_name())
    server = QLocalServer()
    server.listen(_server_name())

    settings = config.load()
    app.installEventFilter(ripples := effects.RippleFilter(app))  # ripples on every button press
    theme.apply(app, settings.get("appearance", "auto"), settings.get("accent", tokens.DEFAULT_ACCENT),
                settings.get("contrast", "standard"))
    icon = draw_icon()
    app.setWindowIcon(icon)
    window = MainWindow(keep_running=not IS_WINDOWS)
    theme.follow_system(app, lambda: window.cfg)

    def show():
        window.show()
        window.raise_()
        window.activateWindow()
        if not IS_WINDOWS:
            desktop.focus_app_window(ui_common.APP_ID)  # Hyprland doesn't let apps focus themselves

    def request_quit():
        if window.dirty:
            show()
            window.toast("Save or discard your changes before quitting.")
        else:
            app.quit()

    def on_connection():
        sock = server.nextPendingConnection()
        sock.waitForReadyRead(300)
        if bytes(sock.readAll()) == b"show":
            show()
        sock.close()
    server.newConnection.connect(on_connection)
    QShortcut(QKeySequence("Ctrl+Q"), window, activated=request_quit)

    # Hyprland lists hidden apps in the bar instead (PID file); Windows has the service's own tray.
    if not IS_WINDOWS and desktop.current() != desktop.HYPRLAND and QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(icon, app)
        tray.setToolTip("NumpadPilot")
        menu = QMenu()
        menu.addAction("Open settings", show)
        menu.addAction("Quit", request_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and show())
        tray.show()

    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    app.aboutToQuit.connect(lambda: PID_PATH.unlink(missing_ok=True))
    if not hidden:
        show()
    return app.exec()
