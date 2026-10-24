"""The numpad input backend for this operating system.

Every backend provides:
    open_numpad(spec, grab) -> numpad or None
        numpad.names, numpad.spec, numpad.close()
        async numpad.events() -> yields (key name, pressed); raises OSError when unplugged
    detect_device(timeout) -> spec of the next keyboard a numpad key is pressed on, or None
    list_devices() -> [(id, vendor, product, name)]
"""

from . import IS_WINDOWS

if IS_WINDOWS:
    raise ImportError("numpad input isn't available on Windows yet")

from .linux_numpad import detect_device, list_devices, open_numpad  # noqa: E402,F401
