"""Making a sticker out of a picture file: open it, shrink it, keep it as a small PNG named after its content."""

import hashlib
import os
import tempfile

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap

from numpadctl import stickers

FILTER = "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg);;All files (*)"
MAX_PIXELS = 40_000_000   # refuse absurdly big pictures before they are decoded


class StickerError(Exception):
    """The picture can't be used; the message says why, in plain words."""


def _read_scaled(reader, side):
    """Decode `reader`'s picture at most `side` pixels wide and high. Raises StickerError."""
    reader.setAutoTransform(True)                # photos taken sideways
    full = reader.size()
    if not full.isValid():
        raise StickerError("That doesn't look like a picture NumpadControl can open.")
    if full.width() * full.height() > MAX_PIXELS:
        raise StickerError("That picture is too large to open.")
    box = QSize(side, side)
    # asking the reader for the small size lets it decode a big photo cheaply (and draws SVG sharp)
    reader.setScaledSize(full.scaled(box, Qt.KeepAspectRatio) if full.width() > box.width()
                         or full.height() > box.height() else full)
    image = reader.read()
    if image.isNull():
        raise StickerError("That doesn't look like a picture NumpadControl can open.")
    return image


def png_bytes(path, side=None):
    """The picture file `path` as PNG bytes, at most `side` (default: sticker size) pixels wide and high. Raises StickerError."""
    side = side or stickers.SIZE
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise StickerError(f"Couldn't read the file: {e.strerror or e}") from None
    if size > stickers.MAX_SOURCE_BYTES:
        raise StickerError("That file is too big to be a sticker (over 20 MB).")
    reader = QImageReader(str(path))
    try:
        image = _read_scaled(reader, side)
    finally:
        device = reader.device()         # Windows can't delete the file while the reader still holds it open
        if device is not None:
            device.close()
    image = image.convertToFormat(QImage.Format_ARGB32)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def make(path):
    """Store `path` as a sticker and return its name. Raises StickerError."""
    raw = png_bytes(path)
    name = hashlib.sha256(raw).hexdigest()[:16] + ".png"
    target = stickers.path_for(name)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
    except OSError as e:
        raise StickerError(f"Couldn't keep the sticker: {e.strerror or e}") from None
    return name


def png_from_bytes(data, extension, side=None):
    """Like png_bytes(), for a picture that is only in memory (one from a pack)."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "picture" + extension)     # a name we choose: nothing from the pack reaches the file system
        with open(path, "wb") as f:
            f.write(data)
        return png_bytes(path, side)


def make_from_bytes(data, extension):
    """Like make(), for a picture that is only in memory (one from a sticker pack). `extension` is its file type."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "picture" + extension)     # a name we choose: nothing from the pack reaches the file system
        with open(path, "wb") as f:
            f.write(data)
        return make(path)


_cache = {}


def pixmap(name, side):
    """The sticker `name` as a pixmap fitting `side` x `side` (device pixels follow the screen), or None."""
    path = stickers.path_for(name)
    if path is None:
        return None
    key = (name, side)
    if key not in _cache:
        loaded = QPixmap(str(path)) if path.is_file() else QPixmap()
        if loaded.isNull():
            return None   # not remembered: the file may appear (or be fixed) later
        scaled = loaded.scaled(side * 2, side * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(2.0)
        _cache[key] = scaled
    return _cache[key]
