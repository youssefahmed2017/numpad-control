"""Redraws the NumpadControl wordmark on the three banner pictures, keeping the rest of each picture.

    python tools/make-banners.py OUT_FOLDER      (needs Pillow and the Noto Sans Black font)

The pictures (assets/banner.png, assets/social-preview.png, site/img/og.png) were made outside this repo with
the name drawn in. This clears the old wordmark, which sits on a flat background, and draws the new one in
the same two colours ("Numpad" dark, "Control" purple), as large as fits between the logo and the right-hand
shape. It writes the results to OUT_FOLDER so they can be looked at before they replace the originals.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "/usr/share/fonts/noto/NotoSans-Black.ttf"
TRACKING = -0.035   # letter spacing in em: the original is set tight
SS = 4              # draw 4x, then shrink: smooth edges

# picture -> where the old wordmark is (x0, x1 = left edge and the furthest right it may reach; top, bottom of the
# area to clear), the baseline, and the height of a capital letter, all in pixels of that picture
PICTURES = {
    ROOT / "assets/banner.png": dict(x0=1056, x1=1900, clear=(1040, 560, 1910, 745), baseline=691, cap=106),
    ROOT / "assets/social-preview.png": dict(x0=528, x1=948, clear=(520, 240, 955, 322), baseline=303, cap=53),
    ROOT / "site/img/og.png": dict(x0=494, x1=886, clear=(486, 238, 892, 318), baseline=299, cap=51),
}


def sample_colours(image, box):
    """(dark, purple): the darkest pixel of the old wordmark, and the most common strongly purple one."""
    region = image.crop(box)
    pixels = list(region.getdata())
    dark = min(pixels, key=lambda p: sum(p))
    purples = [p for p in pixels if p[0] - p[1] > 40 and p[2] - p[1] > 25 and sum(p) < 500]
    counts = {}
    for p in purples:
        counts[p] = counts.get(p, 0) + 1
    return dark, max(counts, key=counts.get)


def layout(text, font):
    """x offset of each letter (with kerning and tracking) and the total width, at the font's own size."""
    xs, x = [], 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        pair = font.getlength(text[i:i + 2]) - font.getlength(text[i + 1:i + 2]) if i + 1 < len(text) else font.getlength(ch)
        x += pair + TRACKING * font.size
    return xs, x - TRACKING * font.size


def redraw(path, spec, out_folder):
    image = Image.open(path).convert("RGB")
    left, top, right, bottom = spec["clear"]
    dark, purple = sample_colours(image, (left, top, right, bottom))
    background = image.getpixel((left, top))
    ImageDraw.Draw(image).rectangle(spec["clear"], fill=background)

    text, split = "NumpadControl", len("Numpad")
    probe = ImageFont.truetype(FONT, 1000)
    cap = probe.getbbox("N")[3] - probe.getbbox("N")[1]
    size = spec["cap"] * 1000 / cap                      # a font size that gives the original capital height
    xs, width = layout(text, ImageFont.truetype(FONT, round(size)))
    room = spec["x1"] - spec["x0"]
    if width > room:                                      # too wide: shrink to fit
        size *= room / width
    font = ImageFont.truetype(FONT, round(size * SS))
    xs, width = layout(text, font)
    layer = Image.new("RGBA", (round(width) + 8 * SS, round(size * 1.5) * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    base = round(size * 1.1) * SS
    for i, (ch, x) in enumerate(zip(text, xs)):
        draw.text((4 * SS + x, base), ch, font=font, fill=(purple if i >= split else dark) + (255,), anchor="ls")
    layer = layer.resize((layer.width // SS, layer.height // SS), Image.LANCZOS)
    image.paste(layer, (round(spec["x0"] - 4), round(spec["baseline"] - base / SS)), layer)
    target = Path(out_folder) / path.name
    image.save(target)
    print(f"{path.name}: wordmark {width / SS:.0f}px wide (room {room}px), font size {size:.0f}px -> {target}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)
    for picture, spec in PICTURES.items():
        redraw(picture, spec, sys.argv[1])
