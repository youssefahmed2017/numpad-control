"""Check a folder of pictures and zip it into a NumpadControl sticker pack.

    python tools/make-sticker-pack.py my-pictures --name "Pastel" --author "Your name" --license "Personal use only"

The folder holds one picture per key, named after it: 0.png ... 9.png, 000.png, dot.png, plus.png, minus.png, star.png,
slash.png, enter.png, numlock.png, backspace.png (png, jpg, gif, webp, bmp or svg). The pack is checked with the same code
the settings window uses to read it (numpadctl/sticker_packs.py), then written as NumpadControl-stickers-<name>.zip next
to the folder (or where -o says) with a pack.json that shows the name, author and license when someone applies it:
Profile ⋯ → Apply sticker pack…

PNGs under 128 pixels are flagged: stickers are kept at up to 128 px, so a smaller picture is blurry. Draw them at 256 px
or more, square, with a transparent background.
"""

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from numpadctl import sticker_packs  # noqa: E402


MIN_SIDE = 128   # stickers are kept at up to 128 px


def png_size(data):
    """(width, height) of a PNG, or None for anything else."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a folder of pictures and zip it into a NumpadControl sticker pack.")
    ap.add_argument("folder", help="the folder with one picture per key")
    ap.add_argument("--name", required=True, help="the pack's name, shown when it is applied")
    ap.add_argument("--author", default="", help="who made it")
    ap.add_argument("--license", default="", help='how it may be used, e.g. "Personal use only, no resale"')
    ap.add_argument("--license-file", help="a text file to include as LICENSE.txt")
    ap.add_argument("-o", "--output", help="where to write the zip (default: next to the folder)")
    args = ap.parse_args(argv)

    folder = Path(args.folder)
    try:
        pack = sticker_packs.read_pack(folder)
    except sticker_packs.PackError as e:
        print(f"error: {e}")
        return 1
    problems = 0
    for key, (extension, data) in sorted(pack.files.items()):
        size = png_size(data) if extension == ".png" else None
        if size and min(size) < MIN_SIDE:
            print(f"warning: key {key}: {size[0]}x{size[1]} is smaller than {MIN_SIDE} px, so it will look blurry")
            problems += 1
        if size and abs(size[0] - size[1]) > 0.1 * max(size):
            print(f"warning: key {key}: {size[0]}x{size[1]} isn't square")
            problems += 1
    for note in pack.ignored:
        print(f"note: {note}")
    missing = [k for k in sticker_packs.ALL_KEYS if k not in pack.files]
    print(f"{len(pack.files)} of {len(sticker_packs.ALL_KEYS)} keys have a picture" + (f"; missing: {' '.join(missing)}" if missing else ""))

    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-") or "pack"
    out = Path(args.output) if args.output else folder.resolve().parent / f"NumpadControl-stickers-{slug}.zip"
    info = {"name": args.name, "author": args.author, "license": args.license}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(name, data):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))    # a fixed time: the same pack gives the same zip
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
        add("pack.json", json.dumps(info, indent=2, ensure_ascii=False) + "\n")
        if args.license_file:
            add("LICENSE.txt", Path(args.license_file).read_bytes())
        for key, (extension, data) in sorted(pack.files.items()):
            name = next(n for n, k in sticker_packs.KEY_FILE_NAMES.items() if k == key and n not in ("period",))
            add(name + extension, data)
    check = sticker_packs.read_pack(out)          # read it back the way the settings window will
    assert set(check.files) == set(pack.files) and check.name == args.name[:sticker_packs.MAX_TEXT]
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)" + (f"; {problems} warning(s) above" if problems else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
