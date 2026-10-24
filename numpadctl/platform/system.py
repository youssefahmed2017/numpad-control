"""System actions for this operating system (see linux_system.py for the list)."""

from . import IS_WINDOWS

if IS_WINDOWS:
    raise ImportError("system actions aren't available on Windows yet")

from .linux_system import *  # noqa: E402,F401,F403
from .linux_system import SystemActionError  # noqa: E402,F401
