"""Cut Google's Material Symbols Rounded variable font down to the icons the settings window uses.

    pip install fonttools
    python tools/subset-icons.py "MaterialSymbolsRounded[FILL,GRAD,opsz,wght].ttf" \
        "MaterialSymbolsRounded[FILL,GRAD,opsz,wght].codepoints"

Both files are in https://github.com/google/material-design-icons (variablefont/). The full font is about 15 MB;
the result (assets/fonts/MaterialSymbolsRounded.ttf) is about 12 KB. Weight 400, grade 0 and optical size 24 are
fixed (Material's defaults for 20-24 px icons); the FILL axis is kept, so an icon can be drawn outlined or filled
(icons.py, buttons.py: a checked button's icon is filled). It also writes MaterialSymbolsRounded.codepoints.json
({name: hex code point}), which icons.py reads. To add an icon, add its name to ICONS and run this again.
"""

import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ICONS = ["add", "add_circle", "alt_route", "apps", "arrow_back", "arrow_drop_down", "arrow_forward", "bedtime",
         "bolt", "build", "celebration", "check", "check_circle", "chevron_right", "circle", "close", "code",
         "content_copy", "dangerous", "dark_mode", "data_object", "delete", "do_not_disturb_on", "download",
         "drag_indicator", "edit", "error", "expand_less", "expand_more", "fiber_manual_record", "filter_alt",
         "folder_open", "fullscreen", "headphones", "help", "image", "info", "keyboard", "keyboard_alt",
         "keyboard_keys", "layers", "light_mode", "link", "list", "lock", "mic", "mic_off", "more_vert",
         "move_group", "music_note", "music_off", "notifications", "open_in_new", "palette", "pause",
         "picture_in_picture", "play_arrow", "play_pause", "power_settings_new", "privacy_tip", "public",
         "radio_button_checked", "radio_button_unchecked", "record_voice_over", "refresh", "remove", "replay",
         "restart_alt", "rocket_launch", "save", "screenshot_monitor", "screenshot_region", "search",
         "select_window", "sensors", "sensors_off", "settings", "settings_backup_restore", "skip_next",
         "skip_previous", "space_dashboard", "speaker", "speaker_group", "stack", "stop", "stop_circle",
         "swap_horiz", "sync", "timer", "toggle_off", "toggle_on", "tune", "undo", "upload", "videocam",
         "visibility", "voice_over_off", "volume_down", "volume_off", "volume_up", "warning"]
OUT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "MaterialSymbolsRounded.ttf"


def main(font_file, codepoints_file):
    table = dict(line.split() for line in open(codepoints_file) if line.strip())
    missing = [name for name in ICONS if name not in table]
    if missing:
        sys.exit(f"not in this font: {', '.join(missing)}")
    font = TTFont(font_file, lazy=False)   # lazy loading breaks the subsetter on this font's glyph variations
    options = subset.Options()
    options.layout_features = []           # no ligatures: icons.py draws by code point, not by name
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[int(table[name], 16) for name in ICONS])
    subsetter.subset(font)                 # subset first: pinning the axes of the full font takes minutes
    font = instancer.instantiateVariableFont(font, {"wght": 400, "GRAD": 0, "opsz": 24})
    font.save(OUT)
    OUT.with_suffix(".codepoints.json").write_text(json.dumps({n: table[n] for n in sorted(ICONS)}, indent=0) + "\n")
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB, {len(ICONS)} icons, axes {[a.axisTag for a in font['fvar'].axes]}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
