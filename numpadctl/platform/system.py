"""System actions for this operating system (see linux_system.py for the list).

Linux: linux_system.py; Windows: windows_system.py. Both raise SystemActionError.
"""

from . import IS_WINDOWS

if IS_WINDOWS:
    from .windows_system import *  # noqa: F401,F403
    from .windows_system import SystemActionError  # noqa: F401
else:
    from .linux_system import *  # noqa: F401,F403
    from .linux_system import SystemActionError  # noqa: F401
