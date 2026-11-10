"""The key map overlay ("Ghost HUD"): a see-through copy of the numpad that fades onto the screen showing what
each key does: the Normal keys on the left, the Layer keys (layer key held) on the right.

When it shows is the service's choice (config.hud_settings): by default Layer + a key (Enter) opens it and the
same combo, or letting go of the layer key, closes it; the old way shows it for as long as the layer key is held.

It runs as its own small process (the service starts it, see Daemon.manage_hud) and listens to the service like the
settings window does. It never takes focus and lets every click through. On Linux it is started through XWayland, where
a window the window manager doesn't manage floats above everything without being tiled or stealing the keyboard."""

import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from numpadctl import config, ui_common

from . import motion, sticker_image, theme, tokens
from .widgets import Dispatcher

CELL_W, CELL_H, GAP, PAD, TITLE_H = 104, 70, 8, 20, 34
PANEL_GAP = 24  # between the Normal and the Layer half
GONE_AFTER = 5  # status messages saying the service is gone, 2 s apart, before the overlay quits too
ROWS, COLUMNS = 5, 4
STICKER = 28   # a sticker's size on the overlay, where the key's name would be


class Hud(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NumpadControl key map")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
                            | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.keys, self.stickers, self.opacity, self.alpha = {}, {}, 0.9, 0.0
        self.base, self.base_stickers = None, {}   # None: an older service sent only the layer half
        self.layer_key = self.combo_key = ""
        self._size_for(halves=2)
        self.cells = ui_common.LAYOUT
        self.gone = 0
        self.fade = motion.Spring(self, "default_effects", self.set_alpha)
        self.fade.when_done(self.faded)

    @staticmethod
    def grid_width():
        return COLUMNS * CELL_W + (COLUMNS - 1) * GAP

    def _size_for(self, halves):
        self.setFixedSize(PAD * 2 + halves * self.grid_width() + (halves - 1) * PANEL_GAP,
                          PAD * 2 + TITLE_H + ROWS * CELL_H + (ROWS - 1) * GAP)

    # ---------------------------------------------------------------- showing and hiding
    def set_alpha(self, value):
        self.alpha = float(value)
        self.update()

    def fade_to(self, target):
        self.fade.go(self.alpha, target)

    def faded(self):
        if self.alpha <= 0.0:
            self.hide()

    def show_keys(self, keys, opacity, stickers=None, base=None, base_stickers=None, layer_key="", combo_key=""):
        self.keys, self.opacity = dict(keys), max(30, min(100, int(opacity))) / 100
        self.stickers = dict(stickers) if isinstance(stickers, dict) else {}
        self.base = dict(base) if isinstance(base, dict) else None
        self.base_stickers = dict(base_stickers) if isinstance(base_stickers, dict) else {}
        self.layer_key, self.combo_key = layer_key or "", combo_key or ""
        self._size_for(halves=1 if self.base is None else 2)
        self.cells = ui_common.layout_for(config.load())   # read again each time: the layout can change in Settings
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.geometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + (area.height() - self.height()) // 2)
        self.show()
        self.fade_to(1.0)

    def hide_keys(self):
        if self.isVisible():
            self.fade_to(0.0)

    def on_message(self, message):
        event = message.get("event")
        if event == "hud":
            if message.get("on"):
                self.show_keys(message.get("keys", {}), message.get("opacity", 90), message.get("stickers"),
                               message.get("base"), message.get("base_stickers"),
                               message.get("layer_key", ""), message.get("combo_key", ""))
            else:
                self.hide_keys()
        elif event == "status":
            self.gone = 0 if message.get("running", True) else self.gone + 1
            if self.gone >= GONE_AFTER:  # the service is gone for good: nothing left to show
                QApplication.instance().quit()

    # ---------------------------------------------------------------- drawing
    def special(self, key, layer):
        """The text for the two keys that aren't actions here: the layer key itself, and the combo key that
        opens and closes this overlay (in the Layer half). None for every other key."""
        if key == self.layer_key and self.layer_key:
            return "Held" if layer else "Layer key"
        if layer and key == self.combo_key and self.combo_key:
            return "Key map"
        return None

    def draw_half(self, painter, colour, left, title, keys, stickers, layer):
        """One numpad: a title (M3 title-medium in the accent colour), then the keys in the layout's places."""
        title_font = QFont(self.font())
        title_font.setPointSizeF(max(9.0, title_font.pointSizeF() + 1))
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(colour("primary" if layer else "onSurface"))
        painter.drawText(QRectF(left, PAD - 4, self.grid_width(), TITLE_H), Qt.AlignLeft | Qt.AlignVCenter, title)

        name_font, action_font = QFont(self.font()), QFont(self.font())
        name_font.setBold(True)
        name_font.setPointSizeF(max(9.0, name_font.pointSizeF() + 1))
        action_font.setPointSizeF(max(8.0, action_font.pointSizeF() - 1))
        for key, row, column, span in self.cells:
            x = left + column * (CELL_W + GAP)
            y = PAD + TITLE_H + row * (CELL_H + GAP)
            height = span * CELL_H + (span - 1) * GAP
            special = self.special(key, layer)
            used = key in keys and special is None
            # M3 roles: a used key is a tonal tile (tertiary in the Layer half, secondary in the Normal half),
            # the layer / combo keys are outlined, unused keys sit back in the surface colour
            fill, text = (("tertiaryContainer", "onTertiaryContainer") if layer else
                          ("secondaryContainer", "onSecondaryContainer")) if used else ("surfaceContainerHigh", "onSurfaceVariant")
            painter.setPen(Qt.NoPen)
            painter.setBrush(colour(fill, min(1.0, self.opacity + 0.1)))
            painter.drawRoundedRect(QRectF(x, y, CELL_W, height), 16, 16)
            if special:
                painter.setPen(QPen(colour("primary"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(x + 1, y + 1, CELL_W - 2, height - 2), 15, 15)
            painter.setFont(name_font)
            painter.setPen(colour(text if used else "onSurface" if special else "onSurfaceVariant",
                                  1.0 if used or special else 0.7))
            sticker = sticker_image.pixmap(stickers.get(key), STICKER) if used else None
            if sticker:   # the key's picture instead of its name
                logical = sticker.deviceIndependentSize()
                painter.drawPixmap(QPointF(x + (CELL_W - logical.width()) / 2, y + 4 + (STICKER - logical.height()) / 2),
                                   sticker)
            else:
                painter.drawText(QRectF(x, y + 8, CELL_W, 24), Qt.AlignHCenter | Qt.AlignVCenter,
                                 ui_common.KEY_LABELS.get(key, key))
            painter.setFont(action_font)
            words = special or keys.get(key, "—")
            elided = QFontMetrics(action_font).elidedText(words, Qt.ElideRight, CELL_W - 14)
            painter.setPen(colour("primary" if special else text if used else "onSurfaceVariant",
                                  1.0 if used or special else 0.45))
            painter.drawText(QRectF(x + 7, y + 34, CELL_W - 14, 28), Qt.AlignHCenter | Qt.AlignTop, elided)

    def paintEvent(self, _):
        c = theme.current
        if not c or self.alpha <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self.alpha)

        def colour(name, strength=1.0):
            result = QColor(c[name])
            result.setAlphaF(strength)
            return result

        painter.setPen(Qt.NoPen)
        painter.setBrush(colour("surfaceContainer", self.opacity))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 28, 28)

        halves = [("Layer", self.keys, self.stickers, True)]
        if self.base is not None:
            layer_name = ui_common.KEY_LABELS.get(self.layer_key, self.layer_key)
            halves = [("Normal", self.base, self.base_stickers, False),
                      (f"Layer  ·  hold {layer_name}" if layer_name else "Layer", self.keys, self.stickers, True)]
        for index, (title, keys, stickers, layer) in enumerate(halves):
            self.draw_half(painter, colour, PAD + index * (self.grid_width() + PANEL_GAP), title, keys, stickers, layer)
        painter.end()


def run():
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NumpadControl key map")
    app.setQuitOnLastWindowClosed(False)
    cfg = config.load()
    theme.apply(app, cfg.get("appearance", "auto"), cfg.get("accent", tokens.DEFAULT_ACCENT),
                cfg.get("contrast", "standard"))
    hud = Hud()
    dispatch = Dispatcher()
    hud.link = ui_common.ServiceLink(hud.on_message, dispatch)  # kept alive by the HUD for as long as the app runs
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
