"""Games with anti-cheat: while one runs, the service lets go of the numpad completely.

NumpadPilot reads the numpad without a driver (Windows: Raw Input, plus a keyboard
hook DLL that Windows loads into apps to stop the numpad's keys from typing). Games
with anti-cheat dislike DLLs loaded into them, so while such a game runs nothing is
hooked at all: the numpad types like a normal keyboard, and it comes back by itself
when the game closes.

Settings: "pause_for_games": "auto" (on Windows only; Linux reads the numpad through the
kernel's own input layer), true or false; "protected_games": more program names, e.g.
["MyGame.exe"]. The game is recognised by its program name, so nothing is read from it.
"""

from .platform import IS_WINDOWS

# Program name (lower case) -> what to show. The anti-cheat services in the second half
# only run while one of their games does, so they cover games not listed here.
PROTECTED = {
    "valorant-win64-shipping.exe": "Valorant",
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


def enabled(cfg):
    setting = cfg.get("pause_for_games", "auto")
    return IS_WINDOWS if setting == "auto" else bool(setting)


def protected_game(cfg, running):
    """The name of a protected game in `running` (lower-case program names), or None."""
    extra = {name.lower(): name for name in cfg.get("protected_games", []) if isinstance(name, str)}
    for name in sorted(running):
        if name in extra:
            return extra[name]
        if name in PROTECTED:
            return PROTECTED[name]
    return None
