"""The numpad input backend for this operating system.

Every backend provides:
    open_numpad(spec, grab) -> numpad or None
        numpad.names, numpad.spec, numpad.close()
        async numpad.events() -> yields (key name, pressed); raises OSError when unplugged
    detect_device(timeout) -> spec of the next keyboard a numpad key is pressed on, or None
    list_devices() -> [(id, vendor, product, name)]

Linux reads evdev (linux_numpad.py); Windows uses the Interception driver
(windows_numpad.py).
"""

from . import IS_WINDOWS

if IS_WINDOWS:
    from .windows_numpad import detect_device, list_devices, open_numpad  # noqa: F401
else:
    from .linux_numpad import detect_device, list_devices, open_numpad  # noqa: F401
