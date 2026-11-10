"""Games with anti-cheat: while one runs, the service takes its keyboard hook out of the picture.

NumpadControl reads the numpad without a driver (Windows: Raw Input, plus a keyboard
hook DLL that Windows loads into apps to stop the numpad's keys from typing). Games
with anti-cheat dislike DLLs loaded into them, and only the DLL is the problem: Raw Input
puts nothing into any other program. So there are two ways to be careful:

  "hook"  the numpad is reopened without the hook DLL while the game runs. The numpad's
          actions keep working; its keys also reach the game as normal typing. The hook
          comes back by itself when the game closes. (The default on Windows.)
  "full"  the numpad is let go completely: it types like a normal keyboard, nothing is
          read, and it comes back when the game closes.

Settings: "pause_for_games": "auto" (= "hook" on Windows, off elsewhere: Linux reads the
numpad through the kernel's own input layer), "hook", "full" (true means the same), or
false; "protected_games": more program names, e.g. ["MyGame.exe"]. The game is recognised
by its program name, so nothing is read from it.
"""

from .platform import IS_WINDOWS

# Program name (lower case) -> what to show. The anti-cheat services in the second half
# only run while one of their games does, so they cover games not listed here. Launcher stubs
# are in too: they start a moment before the game itself, and the hook has to be gone by then.
PROTECTED = {
    "valorant.exe": "Valorant",
    "valorant-win64-shipping.exe": "Valorant",
    "fortnitelauncher.exe": "Fortnite",
    "league of legends.exe": "League of Legends",
    "fortniteclient-win64-shipping.exe": "Fortnite",
    "cod.exe": "Call of Duty",
    "modernwarfare.exe": "Call of Duty: Modern Warfare",
    "bf6.exe": "Battlefield 6",
    "bf2042.exe": "Battlefield 2042",
    "r5apex.exe": "Apex Legends",
    "r5apex_dx12.exe": "Apex Legends",
    "rainbowsix.exe": "Rainbow Six Siege",
    "rainbowsix_be.exe": "Rainbow Six Siege",
    "tslgame.exe": "PUBG",
    "destiny2.exe": "Destiny 2",
    "genshinimpact.exe": "Genshin Impact",
    "starrail.exe": "Honkai: Star Rail",
    "zenlesszonezero.exe": "Zenless Zone Zero",
    "faceit.exe": "FACEIT",
    "easyanticheat.exe": "a game with Easy Anti-Cheat",
    "easyanticheat_eos.exe": "a game with Easy Anti-Cheat",
    "beservice.exe": "a game with BattlEye",
    "beservice_x64.exe": "a game with BattlEye",
    "eaanticheat.gameservice.exe": "a game with EA Javelin anti-cheat",
}


def mode(cfg):
    """What to do while a game with anti-cheat runs: "hook" (drop only the hook), "full" (let go) or "off"."""
    setting = cfg.get("pause_for_games", "auto")
    if setting is False:
        return "off"
    if setting is True or setting == "full":
        return "full"
    if setting == "hook":
        return "hook"
    return "hook" if IS_WINDOWS else "off"  # "auto" (and anything unknown)


def enabled(cfg):
    return mode(cfg) != "off"


def protected_game(cfg, running):
    """The name of a protected game in `running` (lower-case program names), or None."""
    extra = {name.lower(): name for name in cfg.get("protected_games", []) if isinstance(name, str)}
    for name in sorted(running):
        if name in extra:
            return extra[name]
        if name in PROTECTED:
            return PROTECTED[name]
    return None
