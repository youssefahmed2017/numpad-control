"""Numpad Control on Windows: the service in the background, with a tray icon.

Start it with numpad-control.pyw (double-click it, or "Start at login" in the
tray menu), which runs without a console window. Logs go to
%LOCALAPPDATA%\\numpad-control\\state\\numpad-control.log.

Tray menu: status, Settings… (the settings window; also a left click), Edit
settings file, Pause, Start at login, Show log, Quit.
"""

import asyncio
import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from . import paths

log = logging.getLogger("numpadctl")

APP_NAME = "Numpad Control"
AUTOSTART_NAME = "Numpad Control"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LAUNCHER = Path(__file__).resolve().parents[2] / "numpad-control.pyw"
STATUS_REFRESH_SECONDS = 2


def log_path():
    return paths.state_dir() / "numpad-control.log"


# ---------------------------------------------------------------- start at login

def autostart_command():
    """pythonw (no console window) running the launcher next to the code."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{LAUNCHER}"'


def _winreg():
    import winreg
    return winreg


def autostart_enabled(winreg=None):
    winreg = winreg or _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
    except OSError:
        return False


def set_autostart(on, winreg=None):
    winreg = winreg or _winreg()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- the icon

def draw_icon(size=64):
    """A small numpad: a dark rounded square with a 3x3 grid of keys."""
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, size - 3, size - 3), radius=size // 6, fill=(40, 44, 52, 255))
    gap, cell = size // 16, (size - 4 * size // 16 - 6) // 3
    for row in range(3):
        for col in range(3):
            x = 3 + gap + col * (cell + gap)
            y = 3 + gap + row * (cell + gap)
            color = (53, 132, 228, 255) if (row, col) == (1, 1) else (220, 223, 228, 255)
            draw.rounded_rectangle((x, y, x + cell, y + cell), radius=max(1, cell // 4), fill=color)
    return image


# ---------------------------------------------------------------- the app

class TrayApp:
    def __init__(self, daemon, open_file):
        self.daemon = daemon
        self.open_file = open_file   # open_file(path): shows a text file (Notepad)
        self.icon = None
        self.error = None            # set if the service stopped with an error
        self.loop = asyncio.new_event_loop()
        self.main_task = None        # created when the service thread starts
        self._stopped = threading.Event()

    # status shown in the menu and the icon's tooltip
    def status_text(self):
        if self.error:
            return f"Stopped: {self.error}"
        if self.daemon.paused:
            return "Paused"
        return "Numpad connected" if self.daemon.numpad is not None else "Numpad not found - plug it in"

    def refresh(self):
        if self.icon is not None:
            self.icon.title = f"{APP_NAME} - {self.status_text()}"
            self.icon.update_menu()

    # menu actions
    def open_settings(self, *_):
        """The settings window (a separate process, like on Linux)."""
        from .windows_system import spawn
        spawn(str(Path(sys.executable).with_name("pythonw.exe")), str(LAUNCHER), "gui")

    def edit_settings_file(self, *_):
        self.open_file(config_path())

    def show_log(self, *_):
        self.open_file(log_path())

    def toggle_pause(self, *_):
        self.daemon.paused = not self.daemon.paused
        log.info("paused" if self.daemon.paused else "resumed")
        self.refresh()

    def toggle_autostart(self, *_):
        set_autostart(not autostart_enabled())
        self.refresh()

    def quit(self, *_):
        self._stopped.set()
        if self.main_task is not None:
            self.loop.call_soon_threadsafe(self.main_task.cancel)
        if self.icon is not None:
            self.icon.stop()

    # threads
    def run_service(self):
        """The service's event loop (background thread)."""
        asyncio.set_event_loop(self.loop)
        self.main_task = self.loop.create_task(self.daemon.main())
        if self._stopped.is_set():  # Quit was clicked before the service got going
            self.main_task.cancel()
        try:
            self.loop.run_until_complete(self.main_task)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # e.g. Windows refused the keyboard hook
            log.exception("the service stopped")
            from .. import crash
            crash.report("service")
            self.error = str(e)
            from ..actions import notify
            notify(APP_NAME, f"Stopped: {e}")
            self.refresh()

    def watch_status(self):
        last = None
        while not self._stopped.wait(STATUS_REFRESH_SECONDS):
            text = self.status_text()
            if text != last:
                last = text
                self.refresh()

    def menu(self):
        from pystray import Menu, MenuItem as Item
        return Menu(
            Item(lambda item: self.status_text(), None, enabled=False),
            Menu.SEPARATOR,
            Item("Settings…", self.open_settings, default=True),
            Item("Edit settings file", self.edit_settings_file),
            Item("Pause", self.toggle_pause, checked=lambda item: self.daemon.paused),
            Item("Start at login", self.toggle_autostart, checked=lambda item: autostart_enabled()),
            Item("Show log", self.show_log),
            Menu.SEPARATOR,
            Item("Quit", self.quit))

    def run(self):
        import pystray
        threading.Thread(target=self.run_service, daemon=True).start()
        threading.Thread(target=self.watch_status, daemon=True).start()
        self.icon = pystray.Icon("numpad-control", draw_icon(), APP_NAME, menu=self.menu())
        self.refresh()
        self.icon.run()


def config_path():
    from ..config import CONFIG_PATH
    return CONFIG_PATH


def _already_running():
    """A named mutex: only one Numpad Control per user session."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _already_running.handle = kernel32.CreateMutexW(None, False, "Local\\NumpadControl")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def _message_box(text):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)  # MB_ICONERROR


def main():
    try:
        log_path().parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2,
                                                       encoding="utf-8")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=[handler])
        from .. import crash
        crash.install("tray")
        if _already_running():
            _message_box("Numpad Control is already running - look for its icon in the system tray.")
            return
        from .. import config, daemon
        from .windows_system import spawn
        if not config.CONFIG_PATH.exists():  # so "Open settings file" has something to open
            config.save(config.load())
        log.info("starting")
        TrayApp(daemon.Daemon(), open_file=lambda path: spawn("notepad.exe", str(path))).run()
        log.info("stopped")
    except Exception as e:
        log.exception("couldn't start")
        from .. import crash
        crash.report("tray")
        _message_box(f"Numpad Control couldn't start:\n\n{e}\n\nDetails are in {log_path()}")
