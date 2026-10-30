"""The numpad input backend for this operating system.

Every backend provides:
    open_numpad(spec, grab) -> numpad or None
        numpad.names, numpad.spec, numpad.close()
        async numpad.events() -> yields (key name, pressed); raises OSError when unplugged
    detect_device(timeout) -> spec of the next keyboard a numpad key is pressed on, or None
    list_devices() -> [(id, vendor, product, name)]
    open_device(spec, grab) -> like open_numpad for an extra device (all keys named "<id>:KEY_X"),
        which also has numpad.ungrab(); only Linux has it so far (Windows returns None)

Linux reads evdev (linux_numpad.py). Windows uses Raw Input and a keyboard hook, no
driver (windows_rawinput.py); NUMPADCTL_WINDOWS_BACKEND=interception switches to the
Interception driver instead (windows_numpad.py).
"""

import os

from . import IS_WINDOWS

if IS_WINDOWS and os.environ.get("NUMPADCTL_WINDOWS_BACKEND", "").lower() == "interception":
    from .windows_numpad import detect_device, list_devices, open_numpad  # noqa: F401
elif IS_WINDOWS:
    from .windows_rawinput import detect_device, list_devices, open_numpad  # noqa: F401
else:
    from .linux_numpad import detect_device, list_devices, open_device, open_numpad  # noqa: F401

if IS_WINDOWS:
    def open_device(spec, grab):  # noqa: F811
        return None
