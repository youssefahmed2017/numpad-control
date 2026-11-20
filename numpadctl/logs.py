"""Logging for the service and the Windows tray: one line format with the level, one rotating log file on every
platform (not only the system journal), a level you can raise to DEBUG, and the helpers that Diagnostics and
Tools > Copy the log use to read the end of the file.

    NUMPADCTL_LOG=debug python -m numpadctl run       (or "log_level": "debug" in config.json)

DEBUG adds one line per raw key event (down / up), which is what to look at when the numpad "does nothing":
if no raw line appears when a key is pressed, the key never reached the program (the hardware or the USB
connection), and no setting can fix that.
"""

import logging
import logging.handlers
import os

from .platform import paths

FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
DEFAULT_LEVEL = "info"
MAX_BYTES = 1_000_000     # the file is cut at 1 MB, and the last two are kept (numpad-control.log.1, .2)
BACKUPS = 2
NAME = "numpad-control.log"


def log_path():
    return paths.state_dir() / NAME


def level_name(cfg=None):
    """The log level: the NUMPADCTL_LOG environment variable, else "log_level" in config.json, else "info"
    (a name it doesn't know falls back to "info": a typo must not stop the service from logging)."""
    wanted = os.environ.get("NUMPADCTL_LOG", "").strip().lower()
    if not wanted:
        if cfg is None:
            try:
                from . import config
                cfg = config.load()
            except Exception:
                cfg = {}
        wanted = str(cfg.get("log_level", "")).strip().lower()
    return wanted if wanted in LEVELS else DEFAULT_LEVEL


def setup(console=True, cfg=None):
    """Send the logs to the rotating file (and, with `console`, to stderr, which systemd keeps in the journal), and
    set the level of NumpadControl's own logger. Safe to call twice. Returns the level name that is in use."""
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "_numpadctl", False)]
    if not ours:
        formatter = logging.Formatter(FORMAT)
        handlers = []
        try:
            log_path().parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(log_path(), maxBytes=MAX_BYTES, backupCount=BACKUPS,
                                                                 encoding="utf-8"))
        except OSError:      # a folder we can't write to must not stop the service: the journal still has the lines
            pass
        if console or not handlers:
            handlers.append(logging.StreamHandler())
        for handler in handlers:
            handler.setFormatter(formatter)
            handler._numpadctl = True
            root.addHandler(handler)
    root.setLevel(logging.INFO)    # other libraries stay at INFO; only NumpadControl's own logger follows the choice
    name = level_name(cfg)
    logging.getLogger("numpadctl").setLevel(LEVELS[name])
    return name


def tail(lines=200):
    """The last `lines` lines of the log file as a list (empty when there is none yet)."""
    try:
        return log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []
