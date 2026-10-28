"""Key ids: the numpad's standard keys by name, and any other key by an id made from its code.

The standard keys ("0"-"9", ".", "+", "-", "*", "/", "Enter", "Backspace", "NumLock") and the
burst keys "00" / "000" have fixed names. A key the app doesn't know (a "(" key, a Tab key, a
macro key...) is reported by its code: "KEY_TAB" from Linux's evdev, "SC_0F" or "SC_E0_1D" (scan
code, E0 prefix) from Windows. Learn mode in the settings window adds such a key to the pad
("extra_keys" in the config), with a name you can change.
"""

BUILTIN = ("NumLock", "/", "*", "Backspace", "7", "8", "9", "-", "4", "5", "6", "+", "1", "2", "3", "Enter",
           "0", "000", ".")
DOUBLE_ZERO = "00"   # a numpad's "00" key: two 0s in a burst (only recognised once you've added it)

_EVDEV_NAMES = {"KPLEFTPAREN": "(", "KPRIGHTPAREN": ")", "KPEQUAL": "=", "KPPLUSMINUS": "±", "KPCOMMA": ",",
                "KPJPCOMMA": ",", "KPASTERISK": "*", "KPSLASH": "/", "KPMINUS": "-", "KPPLUS": "+", "KPDOT": ".",
                "KPENTER": "Enter", "ESC": "Esc", "BACKSPACE": "⌫", "SPACE": "Space", "MUTE": "Mute",
                "VOLUMEUP": "Vol +", "VOLUMEDOWN": "Vol −", "PLAYPAUSE": "Play/Pause", "NEXTSONG": "Next",
                "PREVIOUSSONG": "Previous", "CALC": "Calc", "COMPOSE": "Menu", "LEFTMETA": "Super"}
_SCANCODE_NAMES = {"01": "Esc", "0E": "⌫", "0F": "Tab", "39": "Space", "35": "/", "37": "*", "4A": "-", "4E": "+",
                   "E0_1C": "Enter", "E0_5D": "Menu", "E0_20": "Mute", "E0_2E": "Vol −", "E0_30": "Vol +",
                   "E0_22": "Play/Pause", "E0_19": "Next", "E0_10": "Previous"}


def evdev_id(name):
    """"KEY_TAB" from evdev's name for a code (a list of aliases is possible)."""
    return name[0] if isinstance(name, (list, tuple)) else name


def scancode_id(code, extended):
    return f"SC_{'E0_' if extended else ''}{code:02X}"


def label_for(key):
    """A readable default name for a key id."""
    if key in BUILTIN or key == DOUBLE_ZERO:
        return key
    if key.startswith("KEY_"):
        short = key[4:]
        return _EVDEV_NAMES.get(short) or short.replace("_", " ").title().replace("Kp", "Num ")
    if key.startswith("SC_"):
        code = key[3:]
        return _SCANCODE_NAMES.get(code) or f"Key {code.replace('_', ' ')}"
    return key


def extra_ids(cfg):
    return {extra["id"] for extra in cfg.get("extra_keys", [])}


def known(key, cfg):
    """Is this key on the pad: a standard key, or one added in Learn mode?"""
    return key in BUILTIN or key in extra_ids(cfg)


def display(key, cfg):
    """The name shown for a key: the name you gave an extra key, or the standard one."""
    for extra in cfg.get("extra_keys", []):
        if extra["id"] == key:
            return extra.get("label") or label_for(key)
    return label_for(key)
