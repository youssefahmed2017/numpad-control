"""Material Symbols (Rounded): the icons Google's own apps use, drawn from the bundled font.

assets/fonts/MaterialSymbolsRounded.ttf is Google's variable font cut down to the icons below
(tools/subset-icons.py; about 12 KB instead of 15 MB). Weight 400, grade 0 and optical size 24 are
fixed; the FILL axis is kept, so an icon can be outlined (0) or filled (1), like a selected tab.

Buttons name their icon with set_symbol(button, "save"); the morphing buttons (buttons.py) draw it in
their own content colour, so it follows the theme, the state and the light / dark switch.
"""

import json
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FAMILY = "Material Symbols Rounded"
CODEPOINTS = {name: chr(int(code, 16)) for name, code in
              json.loads((FONT_DIR / "MaterialSymbolsRounded.codepoints.json").read_text()).items()}
SIZE = 18          # in buttons (M3's small size: next to 14 px labels a 20-24 px icon looked too heavy)
ICON_BUTTON = 20   # alone in a round icon button, and the drop-down arrows of fields
_loaded = []


def available():
    """True once the icon font is registered (theme.load_fonts does it; this is the fallback)."""
    if not _loaded:
        if FAMILY not in QFontDatabase.families():
            QFontDatabase.addApplicationFont(str(FONT_DIR / "MaterialSymbolsRounded.ttf"))
        _loaded.append(FAMILY in QFontDatabase.families())
    return _loaded[0]


def glyph(name):
    """The character that draws `name` in the icon font."""
    return CODEPOINTS[name]


def font(px=SIZE, fill=0.0):
    f = QFont(FAMILY)
    f.setPixelSize(px)
    f.setStyleStrategy(QFont.PreferAntialias)
    if fill:
        f.setVariableAxis(QFont.Tag("FILL"), float(fill))
    return f


def pixmap(name, color, px=SIZE, fill=0.0, ratio=2.0):
    """The icon as a transparent pixmap, drawn at `ratio` for sharp edges on HiDPI screens."""
    image = QPixmap(round(px * ratio), round(px * ratio))
    image.fill(Qt.transparent)
    image.setDevicePixelRatio(ratio)
    if available():
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(font(px, fill))
        painter.setPen(QColor(color))
        painter.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, glyph(name))
        painter.end()
    return image


def icon(name, color, px=SIZE, fill=0.0):
    """A QIcon of the icon in one colour (the same pixmap for every mode: the caller picks the colour)."""
    result = QIcon()
    picture = pixmap(name, color, px, fill)
    for mode in (QIcon.Normal, QIcon.Disabled, QIcon.Active, QIcon.Selected):
        result.addPixmap(picture, mode)
    return result


def set_symbol(button, name, px=SIZE):
    """Give a morphing button (buttons.py) an icon; it is drawn in the button's content colour."""
    button.setProperty("symbol", name)
    button.setIconSize(QSize(px, px))
    button.update()
