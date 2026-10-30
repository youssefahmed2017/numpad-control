"""The key map overlay ("Ghost HUD"): a see-through copy of the numpad that fades in while the layer key is held,
showing what each key does, and fades out when you let go.

It runs as its own small process (the service starts it, see Daemon.manage_hud) and listens to the service like the
settings window does. It never takes focus and lets every click through. On Linux it is started through XWayland, where
a window the window manager doesn't manage floats above everything without being tiled or stealing the keyboard."""

import sys

from PySide6.QtCore import QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from numpadctl import config, ui_common

from . import theme, tokens
from .widgets import Dispatcher

CELL_W, CELL_H, GAP, PAD, TITLE_H = 104, 70, 8, 20, 34
FADE_MS = 140
GONE_AFTER = 5  # status messages saying the service is gone, 2 s apart, before the overlay quits too
ROWS, COLUMNS = 5, 4


class Hud(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NumpadPilot key map")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
                            | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(PAD * 2 + COLUMNS * CELL_W + (COLUMNS - 1) * GAP,
                          PAD * 2 + TITLE_H + ROWS * CELL_H + (ROWS - 1) * GAP)
        self.keys, self.opacity, self.alpha = {}, 0.9, 0.0
        self.gone = 0
        self.fade = QVariantAnimation(self, duration=FADE_MS)
        self.fade.valueChanged.connect(self.set_alpha)
        self.fade.finished.connect(self.faded)

    # ---------------------------------------------------------------- showing and hiding
    def set_alpha(self, value):
        self.alpha = float(value)
        self.update()

    def fade_to(self, target):
        self.fade.stop()
        self.fade.setStartValue(self.alpha)
        self.fade.setEndValue(target)
        self.fade.start()

    def faded(self):
        if self.alpha <= 0.0:
            self.hide()

    def show_keys(self, keys, opacity):
        self.keys, self.opacity = dict(keys), max(30, min(100, int(opacity))) / 100
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
                self.show_keys(message.get("keys", {}), message.get("opacity", 90))
            else:
                self.hide_keys()
        elif event == "status":
            self.gone = 0 if message.get("running", True) else self.gone + 1
            if self.gone >= GONE_AFTER:  # the service is gone for good: nothing left to show
                QApplication.instance().quit()

    # ---------------------------------------------------------------- drawing
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

        title = QFont(self.font())
        title.setPointSizeF(max(9.0, title.pointSizeF() + 1))
        title.setBold(True)
        painter.setFont(title)
        painter.setPen(colour("primary"))
        painter.drawText(QRectF(PAD, PAD - 4, self.width() - 2 * PAD, TITLE_H), Qt.AlignLeft | Qt.AlignVCenter,
                         "Layer")

        name_font, action_font = QFont(self.font()), QFont(self.font())
        name_font.setBold(True)
        name_font.setPointSizeF(max(9.0, name_font.pointSizeF() + 1))
        action_font.setPointSizeF(max(8.0, action_font.pointSizeF() - 1))
        for key, row, column, span in ui_common.LAYOUT:
            x = PAD + column * (CELL_W + GAP)
            y = PAD + TITLE_H + row * (CELL_H + GAP)
            height = span * CELL_H + (span - 1) * GAP
            used = key in self.keys
            painter.setPen(Qt.NoPen)
            painter.setBrush(colour("secondaryContainer" if used else "surfaceContainerHigh",
                                    min(1.0, self.opacity + 0.1)))
            painter.drawRoundedRect(QRectF(x, y, CELL_W, height), 16, 16)
            painter.setFont(name_font)
            painter.setPen(colour("onSecondaryContainer" if used else "onSurfaceVariant", 1.0 if used else 0.7))
            painter.drawText(QRectF(x, y + 8, CELL_W, 24), Qt.AlignHCenter | Qt.AlignVCenter,
                             ui_common.KEY_LABELS.get(key, key))
            painter.setFont(action_font)
            text = self.keys.get(key, "—")
            elided = QFontMetrics(action_font).elidedText(text, Qt.ElideRight, CELL_W - 14)
            painter.setPen(colour("onSecondaryContainer" if used else "onSurfaceVariant", 1.0 if used else 0.45))
            painter.drawText(QRectF(x + 7, y + 34, CELL_W - 14, 28), Qt.AlignHCenter | Qt.AlignTop, elided)
        painter.end()


def run():
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NumpadPilot key map")
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
