Google Sans (text) and JetBrains Mono (code, Diagnostics), both under the SIL Open Font License
(see the `OFL-*.txt` files; from https://github.com/google/fonts). They are cut into static
Regular/Medium/Bold files from the variable versions. The UI loads them itself, so it looks the same on
Windows (where it otherwise fell back to a pixelated bitmap font) and Linux.

`MaterialSymbolsRounded.ttf` is Google's Material Symbols Rounded icon font (Apache License 2.0, see
`LICENSE-MaterialSymbols.txt`; from https://github.com/google/material-design-icons), cut down to the icons the
window uses with `tools/subset-icons.py` (weight 400, grade 0, size 24 fixed; the FILL axis kept). Its
`codepoints.json` maps each icon name to its character. To add an icon, add its name to the list and run the
tool again on the full font (see `numpadctl_ui/icons.py`).

`../brands/` holds two brand logos for the built-in key icons (numpadctl_ui/action_icons.py): OBS Studio and
Python, from Simple Icons (https://simpleicons.org, CC0 1.0, see `LICENSE-SimpleIcons.md` there), rendered once
into 128 px single-colour masks with `rsvg-convert` (the trimmed Qt has no SVG support) and tinted at runtime.
The logos are their owners' trademarks; they are shown only to say "this action works with OBS / Python".
