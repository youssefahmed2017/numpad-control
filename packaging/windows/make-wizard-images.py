"""Draws the installer's side images (wizard/*.bmp) in the NumpadPilot look; commit the result.

    python make-wizard-images.py        (needs Pillow; run it again after changing the artwork)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
ASSETS = HERE.parents[1] / "assets"
LIGHT = dict(top=(255, 247, 250), bottom=(246, 226, 249), blob1=(253, 218, 253), blob2=(253, 222, 216),
             blob3=(241, 220, 240), key1=(255, 255, 255), key2=(124, 78, 127), key3=(253, 222, 216), flat=(255, 247, 250))
DARK = dict(top=(34, 28, 40), bottom=(42, 31, 50), blob1=(74, 45, 82), blob2=(78, 52, 50),
            blob3=(55, 40, 62), key1=(70, 58, 78), key2=(168, 120, 172), key3=(98, 70, 70), flat=(43, 43, 43))
SS = 3  # draw big, then shrink: smooth edges


def gradient(size, theme):
    w, h = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    top, bottom = theme['top'], theme['bottom']
    for y in range(h):
        t = y / max(1, h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return image


def blob(image, box, color):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color)
    image.paste(layer, (0, 0), layer)


def key(image, center, size, angle, color):
    """A soft, slightly tilted rounded key like the ones in the banner."""
    side = int(size * 1.6)
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pad = (side - size) // 2
    d.rounded_rectangle((pad, pad + size * 0.06, pad + size, pad + size + size * 0.06), size * 0.28, fill=(120, 80, 130, 50))
    d.rounded_rectangle((pad, pad, pad + size, pad + size), size * 0.28, fill=color)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    image.paste(layer, (int(center[0] - side / 2), int(center[1] - side / 2)), layer)


def logo(image, center, size):
    icon = Image.open(ASSETS / "icon-512.png").convert("RGBA").resize((size, size), Image.LANCZOS)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (center[0] - size / 2, center[1] - size / 2 + size * 0.07, center[0] + size / 2, center[1] + size / 2 + size * 0.07),
        size * 0.3, fill=(124, 78, 127, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.07))
    image.paste(shadow, (0, 0), shadow)
    image.paste(icon, (int(center[0] - size / 2), int(center[1] - size / 2)), icon)


def large(width, height, theme):
    w, h = width * SS, height * SS
    image = gradient((w, h), theme).convert("RGBA")
    blob(image, (-w * 0.55, h * 0.05, w * 0.75, h * 0.62), theme["blob1"] + (255,))
    blob(image, (w * 0.25, h * 0.58, w * 1.55, h * 1.15), theme["blob2"] + (255,))
    blob(image, (w * 0.55, -h * 0.1, w * 1.2, h * 0.14), theme["blob3"] + (255,))
    key(image, (w * 0.2, h * 0.2), w * 0.2, -10, theme["key1"] + (255,))
    key(image, (w * 0.8, h * 0.31), w * 0.17, 12, theme["key2"] + (255,))
    key(image, (w * 0.25, h * 0.78), w * 0.17, 9, theme["key3"] + (255,))
    key(image, (w * 0.78, h * 0.85), w * 0.2, -8, theme["key1"] + (255,))
    logo(image, (w * 0.5, h * 0.5), int(w * 0.52))
    return image.convert("RGB").resize((width, height), Image.LANCZOS)


def small(size, theme):
    s = size * SS
    image = Image.new("RGBA", (s, s), theme["flat"] + (255,))  # the colour of the wizard's header, so it blends in
    logo(image, (s / 2, s / 2), int(s * 0.74))
    return image.convert("RGB").resize((size, size), Image.LANCZOS)


out = HERE / "wizard"
out.mkdir(exist_ok=True)
for name, theme in (("", LIGHT), ("dark-", DARK)):
    for width, height in ((164, 314), (246, 471), (328, 628)):
        large(width, height, theme).save(out / f"side-{name}{width}.bmp")
    for size in (55, 83, 110):
        small(size, theme).save(out / f"small-{name}{size}.bmp")
print("wrote", *sorted(p.name for p in out.glob("*.bmp")))
