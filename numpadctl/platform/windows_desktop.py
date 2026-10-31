"""Window, workspace, screenshot and lock actions on Windows.

The same functions as desktop.py offers for Hyprland and KDE Plasma; on Windows
desktop.py uses these instead. A window's "class" (for profiles, Focus a window
and Wait for window) is its program's name without ".exe", e.g. "obs64",
"firefox", "Discord" (matched ignoring case).
"""

import ctypes
import subprocess
import time
from pathlib import Path

from ..desktop import DesktopError

SW_RESTORE, SW_MAXIMIZE = 9, 3
WM_CLOSE = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001


def _user32():
    return ctypes.windll.user32


def _kernel32():
    return ctypes.windll.kernel32


def _program(hwnd):
    """The program name (without .exe) owning a window, or ""."""
    user32, kernel32 = _user32(), _kernel32()
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = ctypes.c_uint32(512)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).stem
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def _title(hwnd):
    user32 = _user32()
    length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), buffer, length + 1)
    return buffer.value


def _windows():
    """[(hwnd, program, title)] of visible top-level windows that have a title, front to back."""
    user32, found = _user32(), []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):
        if user32.IsWindowVisible(ctypes.c_void_p(hwnd)) and _title(hwnd):
            found.append((hwnd, _program(hwnd), _title(hwnd)))
        return True
    user32.EnumWindows(callback_type(visit), None)
    return found


def _foreground():
    _user32().GetForegroundWindow.restype = ctypes.c_void_p
    return _user32().GetForegroundWindow()


def active_window_class():
    hwnd = _foreground()
    return _program(hwnd) if hwnd else ""


def open_windows():
    """[(program, title)], one per program, for picking a profile's app."""
    seen, result = set(), []
    for _, program, title in _windows():
        if program and program.lower() not in seen:
            seen.add(program.lower())
            result.append((program, title))
    return result


def _bring_to_front(hwnd):
    user32 = _user32()
    if user32.IsIconic(ctypes.c_void_p(hwnd)):
        user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
    # Windows only lets the program the user last used take focus; a simulated Alt
    # press counts as user input, so this program may then bring the window forward.
    from .windows_system import _tap
    _tap("LEFTALT")
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))


def focus_window(cls):
    for hwnd, program, _ in _windows():
        if program.lower() == cls.lower():
            _bring_to_front(hwnd)
            return
    raise DesktopError(f"no {cls} window is open")


def _active():
    hwnd = _foreground()
    if not hwnd:
        raise DesktopError("no window is focused")
    return hwnd


def close_window():
    _user32().PostMessageW(ctypes.c_void_p(_active()), WM_CLOSE, 0, 0)


def hide_windows():
    """Win+D: show the desktop (press it again and the windows come back)."""
    user32 = _user32()
    for code, flags in ((0x5B, 0), (0x44, 0), (0x44, 2), (0x5B, 2)):  # Win down, D down, D up, Win up
        user32.keybd_event(code, 0, flags, 0)
    return {"win_d": True}


def restore_windows(token):
    """Win+D again brings the windows back."""
    if token.get("win_d"):
        hide_windows()


def force_close_window():
    """End the focused window's program at once and return its name. Unsaved work in it is lost."""
    from ..desktop import PROTECTED
    hwnd = _active()
    name = _program(hwnd)
    pid = ctypes.c_uint32()
    _user32().GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    if not pid.value or name.lower() in PROTECTED or pid.value == _kernel32().GetCurrentProcessId():
        raise DesktopError(f"{name or 'that window'} is protected, it is not force-quit")
    _kernel32().OpenProcess.restype = ctypes.c_void_p
    handle = _kernel32().OpenProcess(PROCESS_TERMINATE, False, pid.value)
    if not handle:
        raise DesktopError(f"{name} can't be ended from here (it may be running as administrator)")
    try:
        _kernel32().TerminateProcess(ctypes.c_void_p(handle), 1)
    finally:
        _kernel32().CloseHandle(ctypes.c_void_p(handle))
    return name


def toggle_fullscreen():
    """Windows has no general fullscreen for other programs' windows: maximize / restore."""
    hwnd, user32 = _active(), _user32()
    user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE if user32.IsZoomed(ctypes.c_void_p(hwnd)) else SW_MAXIMIZE)


def toggle_floating():
    raise DesktopError("Floating windows only work on Hyprland")


def toggle_scratchpad():
    raise DesktopError("The scratchpad only works on Hyprland")


def go_to_workspace(number):
    raise DesktopError("Windows can't switch to a numbered desktop - use Next / Previous workspace")


def move_window_to_workspace(number):
    raise DesktopError("Windows can't move windows between desktops for other programs")


def step_workspace(step):
    """Windows' virtual desktops: Ctrl+Win+Right / Left."""
    from .windows_system import press_keys
    press_keys([["LEFTCTRL", "LEFTMETA", "RIGHT" if step > 0 else "LEFT"]])


def show_osd(message, icon):
    return False  # no popup API on Windows; the caller shows a notification instead


def toggle_dnd():
    raise DesktopError("Windows has no way for programs to turn on Do not disturb")


def screenshot(path: Path, region=False):
    """Full screen: saved to path (True). Region: opens Windows' Snipping tool, which
    copies the region itself (returns None: no file)."""
    if region:
        import os
        os.startfile("ms-screenclip:")
        return None
    from PIL import ImageGrab
    ImageGrab.grab(all_screens=True).save(path)
    return True


def lock_screen():
    _user32().LockWorkStation()


def focus_app_window(app_id):
    pass  # Qt brings its own window forward on Windows
