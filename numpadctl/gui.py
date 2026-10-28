"""Opening the settings: the NumpadPilot app if it can run, otherwise the settings file.

The app (settings window and dialogs) is the numpadctl_ui package next to this one. It
needs Qt for Python (PySide6); without it, the service still works, set up through
config.json.
"""

import sys

from . import config


def app_installed():
    try:
        import numpadctl_ui.app  # noqa: F401
    except ImportError:
        return False
    return True


def run(args=()):
    from . import crash
    crash.install("settings")
    if app_installed():
        from numpadctl_ui import app
        return app.run(args)
    if "--hidden" in args:  # started at login to wait in the tray: there's no app to wait
        return 0
    if not config.CONFIG_PATH.exists():
        config.save(config.load())  # the defaults, so there's a file to edit
    print(f"The settings window needs Qt for Python (PySide6), which isn't installed; opening the settings file instead:\n  {config.CONFIG_PATH}\n"
          "The service picks up changes when you save it.", file=sys.stderr)
    from .platform import system
    system.open_path(str(config.CONFIG_PATH))
    return 0
