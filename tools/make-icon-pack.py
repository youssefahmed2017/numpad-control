"""Check a folder of pictures and zip it into a NumpadControl action icon pack.

    python tools/make-icon-pack.py my-icons --name "Graphite" --author "Your name" --license "Personal use only"

The folder holds one picture per action, named after it: volume_up.png, mic_mute.png, obs_start_recording.png, launch_app.png ...
(png, jpg, gif, webp, bmp or svg). There are about 75 actions; a pack doesn't have to cover them all: an action without a picture
keeps the built-in icon. The pack is checked with the same code the settings window uses to read it (numpadctl/icon_packs.py), then
written as NumpadControl-icons-<name>.zip next to the folder (or where -o says), with a pack.json that shows the name, author and
license when someone installs it: Settings → Appearance → Icon pack → Install pack…

Pictures under 128 pixels are flagged (a stored icon is kept at up to 128 px), and so are ones that aren't square. Draw them at
256 px or more with a transparent background around a tile: the picture is shown whole, in its own colours.
"""

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from numpadctl import icon_packs  # noqa: E402
from numpadctl_ui import action_icons  # noqa: E402

MIN_SIDE = 128


def png_size(data):
    """(width, height) of a PNG, or None for anything else."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a folder of pictures and zip it into a NumpadControl action icon pack.")
    ap.add_argument("folder", help="the folder with one picture per action")
    ap.add_argument("--name", required=True, help="the pack's name, shown in Settings")
    ap.add_argument("--author", default="", help="who made it")
    ap.add_argument("--license", default="", help='how it may be used, e.g. "Personal use only, no resale"')
    ap.add_argument("--license-file", help="a text file to include as LICENSE.txt")
    ap.add_argument("-o", "--output", help="where to write the zip (default: next to the folder)")
    args = ap.parse_args(argv)

    ids = sorted(action_icons.ICONS)
    try:
        pack = icon_packs.read_pack(Path(args.folder), ids)
    except icon_packs.PackError as e:
        print(f"error: {e}")
        return 1
    problems = 0
    for action_id, (extension, data) in sorted(pack.files.items()):
        size = png_size(data) if extension == ".png" else None
        if size and min(size) < MIN_SIDE:
            print(f"warning: {action_id}: {size[0]}x{size[1]} is smaller than {MIN_SIDE} px, so it will look blurry")
            problems += 1
        if size and abs(size[0] - size[1]) > 0.1 * max(size):
            print(f"warning: {action_id}: {size[0]}x{size[1]} isn't square")
            problems += 1
    for note in pack.ignored:
        print(f"note: {note}")
    missing = [a for a in ids if a not in pack.files]
    print(f"{len(pack.files)} of {len(ids)} actions have a picture" + (f"; the others keep the built-in icon: {' '.join(missing[:8])}"
                                                                        + (" ..." if len(missing) > 8 else "") if missing else ""))

    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-") or "pack"
    out = Path(args.output) if args.output else Path(args.folder).resolve().parent / f"NumpadControl-icons-{slug}.zip"
    info = {"name": args.name, "author": args.author, "license": args.license}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(name, data):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))    # a fixed time: the same pack gives the same zip
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
        add("pack.json", json.dumps(info, indent=2, ensure_ascii=False) + "\n")
        if args.license_file:
            add("LICENSE.txt", Path(args.license_file).read_bytes())
        for action_id, (extension, data) in sorted(pack.files.items()):
            add(action_id + extension, data)
    check = icon_packs.read_pack(out, ids)          # read it back the way the settings window will
    assert set(check.files) == set(pack.files) and check.name == args.name[:60]
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)" + (f"; {problems} warning(s) above" if problems else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
