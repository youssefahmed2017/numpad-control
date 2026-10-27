# Compatibility

The two lists the plan's Phase 0 gate needs (section 8): **no game with anti-cheat
refuses to run or bans anyone**, and **setup works on at least 9 of 10 numpad models**.
Anyone can add a result: open an issue with the "Numpad model test" or "Game with
anti-cheat test" form, and it's copied here.

## Numpad models

Test with `python -m numpadctl check` (stop the service first). It asks for every key,
a held key and the `000` key, then prints the line for this table.

| Model | USB ID | System | Keys | Not on it | Holding a key | 000 key | Result |
|---|---|---|---|---|---|---|---|
| *(the project's own numpad; run `check` to fill in)* | c0f4:05f5 | Linux, Windows | | | | | works (used daily) |

Goal: 10 models, cheap ones first (AliExpress / local shops, wired and wireless).

## Games with anti-cheat

While one of these runs, NumpadPilot lets go of the numpad by itself (no keyboard
hook at all) and takes it back when the game closes (`numpadctl/games.py`). The test is
that the game starts and plays normally with NumpadPilot running, the tray shows
"Paused while … runs", and nothing is flagged in the days after.

| Game | Anti-cheat | Free to play | Tested by | Result |
|---|---|---|---|---|
| Valorant | Riot Vanguard (kernel) | yes | | not tested |
| League of Legends | Riot Vanguard (kernel) | yes | | not tested |
| Fortnite | Easy Anti-Cheat + BattlEye | yes | | not tested |
| Call of Duty: Warzone | RICOCHET (kernel) | yes | | not tested |
| Apex Legends | Easy Anti-Cheat | yes | | not tested |
| Battlefield 6 | EA Javelin (kernel) | no | | not tested |
| Rainbow Six Siege | BattlEye | yes (Siege X) | | not tested |
| PUBG: Battlegrounds | BattlEye-type, own | yes | | not tested |
| Counter-Strike 2 on FACEIT | FACEIT (kernel) | yes | | not tested |
| Genshin Impact | HoYoverse (kernel) | yes | | not tested |

## Testing without downloading ten games

Most of these games are tens of gigabytes. You don't need to install them all yourself:

- **Test the games you already have**, and at most one or two more. Games run fine from a
  hard disk (HDD); they only load slower, which doesn't matter for this test.
- **Let the beta testers do the rest.** Phase 1's closed beta (200 users, section 8) is
  mostly streamers and gamers who already have these games installed. Ask each one to
  send a "Game with anti-cheat test" report; one report per game, from anyone, counts.
- **Watch for a game not being recognised.** If the tray doesn't say "Paused while …
  runs" during a game, the report form asks for the game's program name (Task Manager →
  Details), which then goes into `games.py`.
