"""Material 3 snackbar: a short message that rises from the bottom edge, waits, and leaves.

M3 spec: an inverse-surface container with inverse-on-surface body text (bodyMedium), 4 px corners,
48 px tall for one line, 344-560 px wide, 16 px from the bottom, elevation 3. It arrives with
emphasized-decelerate (fade and a short rise, medium 1) and leaves with emphasized-accelerate (a
quick fade, short 3). A new message replaces the old one in place instead of stacking.

It paints itself (no child labels, no graphics effect), so fading it is just painter opacity.
"""

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from . import motion, theme, tokens

SHOW_MS = 4000          # how long it stays
MIN_WIDTH, MAX_WIDTH = 344, 560
MIN_HEIGHT = 48
PAD_X, PAD_Y = 16, 14   # text inset (14 + one 20 px line + 14 = 48)
RADIUS = tokens.SHAPE["xs"]
BOTTOM_GAP = 16
RISE = 24               # px it travels up while arriving
SHADOW = 18             # room around the container for the elevation shadow


class Snackbar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # a message, not something to click through
        self.setAccessibleName("Message")
        self._text = ""
        self._alpha = 0.0   # 0..1: fade
        self._lift = 0.0    # 0..1: how far up it has risen
        self._timer = QTimer(self, singleShot=True, interval=SHOW_MS)
        self._timer.timeout.connect(self.dismiss)
        self._arrive = motion.Tween(self, motion.MEDIUM1, "emphasized_decelerate", self._arriving)
        self._leave = motion.Tween(self, motion.SHORT3, "emphasized_accelerate", self._leaving)
        self._leave.when_done(self._gone)
        self.hide()

    # ---------------------------------------------------------------- what it says
    def text(self):
        """The message being shown (or about to be), empty once it has gone."""
        return self._text

    def show_message(self, text, ms=SHOW_MS):
        """Show `text`; a message already showing is replaced where it is."""
        self._text = text
        self._leave.stop()
        self._layout()
        replacing = self._alpha > 0.0
        self.show()
        self.raise_()
        if not replacing:
            self._arrive.go(0.0, 1.0)
        else:
            self._arrive.stop()
            self._alpha = self._lift = 1.0
            self._place()
            self.update()
        self._timer.start(ms)

    def dismiss(self):
        """Leave now (also what the timer does)."""
        self._timer.stop()
        if self._text and not self._leave.running():
            self._arrive.stop()
            self._leave.go(self._alpha, 0.0)

    def clear(self):
        """Gone at once, without the leaving motion."""
        self._timer.stop()
        self._arrive.stop()
        self._leave.stop()
        self._text, self._alpha = "", 0.0
        self.hide()

    # ---------------------------------------------------------------- motion
    def _arriving(self, progress):
        self._alpha = self._lift = progress
        self._place()
        self.update()

    def _leaving(self, alpha):
        self._alpha = alpha
        self.update()

    def _gone(self):
        if self._alpha <= 0.001:
            self._text = ""
            self.hide()

    # ---------------------------------------------------------------- geometry
    def _font(self):
        font = self.font()
        size, weight = tokens.TYPE["bodyMedium"]
        font.setPixelSize(size)
        font.setWeight(font.Weight.Normal if weight < 500 else font.Weight.Medium)
        return font

    def _text_width(self):
        return min(MAX_WIDTH, max(MIN_WIDTH, QFontMetrics(self._font()).horizontalAdvance(self._text) + 2 * PAD_X)) - 2 * PAD_X

    def _text_rect(self):
        metrics = QFontMetrics(self._font())
        return metrics.boundingRect(QRect(0, 0, self._text_width(), 1000), Qt.TextWordWrap, self._text)

    def _layout(self):
        """Size the widget to its text: one line is 48 px, more lines grow it."""
        text = self._text_rect()
        body_w = self._text_width() + 2 * PAD_X
        body_h = max(MIN_HEIGHT, text.height() + 2 * PAD_Y)
        self.resize(body_w + 2 * SHADOW, body_h + 2 * SHADOW)
        self._place()

    def _place(self):
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() + SHADOW - BOTTOM_GAP + round(RISE * (1.0 - self._lift))
        self.move(x, y)

    def reposition(self):
        """Call when the window is resized."""
        if self.isVisible():
            self._place()

    # ---------------------------------------------------------------- painting
    def paintEvent(self, event):
        c = theme.current
        if not c or not self._text or self._alpha <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(max(0.0, min(1.0, self._alpha)))
        body = QRectF(SHADOW, SHADOW, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW)
        painter.setPen(Qt.NoPen)
        for grow, alpha in ((9, 0.025), (6, 0.04), (3, 0.06)):  # elevation 3: a soft shadow, a little below
            shade = QColor(c.get("shadow", "#000000"))
            shade.setAlphaF(alpha)
            painter.setBrush(shade)
            painter.drawRoundedRect(body.adjusted(-grow, -grow + 3, grow, grow + 3), RADIUS + grow, RADIUS + grow)
        painter.setBrush(QColor(c["inverseSurface"]))
        painter.drawRoundedRect(body, RADIUS, RADIUS)
        painter.setPen(QColor(c["inverseOnSurface"]))
        painter.setFont(self._font())
        painter.drawText(QRectF(body.left() + PAD_X, body.top(), body.width() - 2 * PAD_X, body.height()),
                         int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap), self._text)
