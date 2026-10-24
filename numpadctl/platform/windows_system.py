"""System actions on Windows: apps, browser, clipboard, typing, media, volume, power.

The same functions as linux_system.py, using only what Windows and Python
provide (no extra packages). Errors are raised as SystemActionError with a
message meant for the user.
"""

import ctypes
import os
import subprocess
import time
import webbrowser
from pathlib import Path

# Explicit sizes (wintypes.DWORD is 8 bytes when this file is tested on Linux).
WORD, DWORD, LONG, ULONG_PTR = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32, ctypes.c_size_t

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


class SystemActionError(Exception):
    pass


def _user32():
    return ctypes.windll.user32


def spawn(*argv):
    """Start a program that keeps running on its own."""
    try:
        subprocess.Popen(argv, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as e:
        raise SystemActionError(f"couldn't start {argv[0]}: {e}")


def refresh_session():
    """Windows has no display variables to refresh; a desktop is always there."""
    return True


def _startfile(target):
    try:
        os.startfile(target)
    except OSError as e:
        raise SystemActionError(f"couldn't open {target}: {e.strerror or e}")


# ---------------------------------------------------------------- notifications

# A toast through Windows PowerShell (built into Windows 10/11). Title and text
# go in through environment variables, so they can't break the script.
_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
$text.Item(0).AppendChild($xml.CreateTextNode($env:NUMPAD_TITLE)) > $null
$text.Item(1).AppendChild($xml.CreateTextNode($env:NUMPAD_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notify(title, body=""):
    env = dict(os.environ, NUMPAD_TITLE=str(title), NUMPAD_BODY=str(body))
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST],
                         env=env, creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass  # a missing notification shouldn't break the action that wanted it


# ---------------------------------------------------------------- opening things

def open_url(url):
    _startfile(url)


def _default_browser():
    """The default browser's .exe from the registry, or None."""
    import winreg
    try:
        key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            prog_id = winreg.QueryValueEx(k, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as k:
            command = winreg.QueryValueEx(k, "")[0]
    except OSError:
        return None
    # e.g. "C:\Program Files\Mozilla Firefox\firefox.exe" -osint -url "%1"
    exe = command.split('"')[1] if command.startswith('"') else command.split()[0]
    return exe if Path(exe).exists() else None


def open_default_browser():
    exe = _default_browser()
    if exe:
        spawn(exe)
    else:
        webbrowser.open("about:blank")


def open_path(path):
    _startfile(path)


def launch_app(app):
    """app: a program (.exe) or a Start-menu shortcut (.lnk)."""
    if not Path(app).exists():
        raise SystemActionError(f"app {app!r} wasn't found")
    _startfile(app)


# ---------------------------------------------------------------- clipboard

CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002


def _kernel32():
    return ctypes.windll.kernel32


def copy_text(text):
    user32, kernel32 = _user32(), _kernel32()
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    data = (text + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(None):
        raise SystemActionError("the clipboard is busy - try again")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        ctypes.memmove(kernel32.GlobalLock(handle), data, len(data))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)  # the clipboard owns it now
    finally:
        user32.CloseClipboard()


def clipboard_text():
    user32, kernel32 = _user32(), _kernel32()
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        text = ctypes.wstring_at(kernel32.GlobalLock(handle))
        kernel32.GlobalUnlock(handle)
        return text
    finally:
        user32.CloseClipboard()


def copy_image(path):
    script = ("Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
              "[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile($env:NUMPAD_IMAGE))")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", script],
                   env=dict(os.environ, NUMPAD_IMAGE=str(path)), creationflags=CREATE_NO_WINDOW,
                   capture_output=True, timeout=15)


# ---------------------------------------------------------------- keyboard (SendInput)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD), ("time", DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", _INPUT_UNION)]


def _ext(vk):
    return (vk, True)


# Key names (the same as on Linux) -> (virtual-key code, extended key?).
VK = {
    **{chr(c): (c, False) for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): (0x30 + d, False) for d in range(10)},
    **{f"F{n}": (0x6F + n, False) for n in range(1, 25)},
    **{f"KP{d}": (0x60 + d, False) for d in range(10)},
    "ENTER": (0x0D, False), "ESC": (0x1B, False), "SPACE": (0x20, False), "TAB": (0x09, False),
    "BACKSPACE": (0x08, False), "CAPSLOCK": (0x14, False), "PAUSE": (0x13, False),
    "SCROLLLOCK": (0x91, False), "SYSRQ": (0x2C, False), "NUMLOCK": (0x90, False),
    "DELETE": _ext(0x2E), "INSERT": _ext(0x2D), "HOME": _ext(0x24), "END": _ext(0x23),
    "PAGEUP": _ext(0x21), "PAGEDOWN": _ext(0x22),
    "UP": _ext(0x26), "DOWN": _ext(0x28), "LEFT": _ext(0x25), "RIGHT": _ext(0x27),
    "LEFTCTRL": (0xA2, False), "RIGHTCTRL": _ext(0xA3), "LEFTSHIFT": (0xA0, False),
    "RIGHTSHIFT": (0xA1, False), "LEFTALT": (0xA4, False), "RIGHTALT": _ext(0xA5),
    "LEFTMETA": _ext(0x5B), "RIGHTMETA": _ext(0x5C), "COMPOSE": _ext(0x5D),
    "MINUS": (0xBD, False), "EQUAL": (0xBB, False), "LEFTBRACE": (0xDB, False),
    "RIGHTBRACE": (0xDD, False), "SEMICOLON": (0xBA, False), "APOSTROPHE": (0xDE, False),
    "GRAVE": (0xC0, False), "BACKSLASH": (0xDC, False), "COMMA": (0xBC, False),
    "DOT": (0xBE, False), "SLASH": (0xBF, False),
    "KPPLUS": (0x6B, False), "KPMINUS": (0x6D, False), "KPASTERISK": (0x6A, False),
    "KPSLASH": _ext(0x6F), "KPDOT": (0x6E, False), "KPENTER": _ext(0x0D),
    "VOLUMEUP": _ext(0xAF), "VOLUMEDOWN": _ext(0xAE), "MUTE": _ext(0xAD),
    "PLAYPAUSE": _ext(0xB3), "NEXTSONG": _ext(0xB0), "PREVIOUSSONG": _ext(0xB1), "STOPCD": _ext(0xB2),
}


def is_key(name):
    return name in VK


def _key(vk, up=False, extended=False):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return item


def _char(unit, up=False):
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki = KEYBDINPUT(wVk=0, wScan=unit, dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
                           time=0, dwExtraInfo=0)
    return item


def _send_inputs(inputs):
    array = (INPUT * len(inputs))(*inputs)
    sent = _user32().SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise SystemActionError("Windows blocked the key presses (an administrator window may be focused)")


def press_keys(combos):
    """combos: [["LEFTCTRL", "C"], ["ENTER"]]: keys in a combo are held together."""
    inputs = []
    for combo in combos:
        keys = [VK[name] for name in combo]
        inputs += [_key(vk, extended=ext) for vk, ext in keys]                    # hold down in order
        inputs += [_key(vk, up=True, extended=ext) for vk, ext in reversed(keys)]  # let go in reverse
    _send_inputs(inputs)


def type_text(text):
    """Type text exactly as written (any language), via Unicode key events."""
    inputs = []
    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            inputs += [_key(0x0D), _key(0x0D, up=True)]
        elif ch == "\t":
            inputs += [_key(0x09), _key(0x09, up=True)]
        else:
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):  # characters outside the BMP are two units
                unit = int.from_bytes(data[i:i + 2], "little")
                inputs += [_char(unit), _char(unit, up=True)]
    if inputs:
        _send_inputs(inputs)


# ---------------------------------------------------------------- media and volume
# Simulated media and volume keys: Windows shows its own volume popup. Each
# volume key press moves the volume by 2%.

VOLUME_STEP = 2


def _tap(name, times=1):
    vk, ext = VK[name]
    _send_inputs([_key(vk, up=up, extended=ext) for _ in range(times) for up in (False, True)])


def media(command):
    """command: "play-pause", "stop", "next" or "previous"."""
    _tap({"play-pause": "PLAYPAUSE", "stop": "STOPCD", "next": "NEXTSONG",
          "previous": "PREVIOUSSONG"}[command])


def change_volume(step):
    """step: percent, e.g. +5 or -5 (Windows moves in 2% steps, so +5 becomes +6)."""
    presses = max(1, round(abs(step) / VOLUME_STEP))
    _tap("VOLUMEUP" if step > 0 else "VOLUMEDOWN", presses)


def set_volume(percent):
    """Down to 0, then up to the level (the nearest 2%)."""
    _tap("VOLUMEDOWN", 100 // VOLUME_STEP)
    if percent:
        _tap("VOLUMEUP", round(percent / VOLUME_STEP))


def toggle_mute(microphone=False):
    if microphone:  # there's no microphone key; use Core Audio
        from .windows_audio import AudioError, toggle_microphone_mute
        try:
            toggle_microphone_mute()
        except AudioError as e:
            raise SystemActionError(str(e))
        return
    _tap("MUTE")


# ---------------------------------------------------------------- power

def power(what):
    """what: "suspend", "poweroff" or "reboot"."""
    if what == "suspend":
        # Sleep; on PCs with hibernation turned on, Windows may hibernate instead.
        ctypes.windll.powrprof.SetSuspendState(False, False, False)
    elif what in ("poweroff", "reboot"):
        subprocess.run(["shutdown", "/s" if what == "poweroff" else "/r", "/t", "0"],
                       creationflags=CREATE_NO_WINDOW, check=False)
    else:
        raise SystemActionError(f"unknown power action {what!r}")
