"""A checkbox that draws its own tick.

A Qt stylesheet can only show a finished image for the checked box, so the tick just appeared in one
frame. This one paints the box and the tick itself: ticking fills the box with the accent colour and
then draws the tick stroke by stroke (like a pen), un-ticking fades the fill and rubs the tick out
again, a little faster. The text, the spacing and the hit area are still the stylesheet's.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton

from . import motion, theme, tokens

TICK = [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)]   # the tick on a 16 x 16 grid
BOX_RADIUS = 4.0
BORDER = 2.0
FILL_SHARE = 0.35     # the first part of the move fills the box, the rest draws the tick
DISABLED_OPACITY = 0.38


def tick_path(share, box):
    """The tick up to `share` (0 to 1) of its length, scaled to the box (a QRectF)."""
    scale = box.width() / 16.0
    points = [QPointF(box.left() + x * scale, box.top() + y * scale) for x, y in TICK]
    lengths = [math.dist((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(points, points[1:])]
    remaining = share * sum(lengths)
    path = QPainterPath(points[0])
    for (start, end), length in zip(zip(points, points[1:]), lengths):
        if remaining <= 0:
            break
        part = min(1.0, remaining / length)
        path.lineTo(QPointF(start.x() + (end.x() - start.x()) * part, start.y() + (end.y() - start.y()) * part))
        remaining -= length
    return path


class CheckBox(QCheckBox):
    def __init__(self, *args):
        super().__init__(*args)
        self._progress = 1.0 if self.isChecked() else 0.0   # 0 = empty box, 1 = filled with the whole tick
        self._hover = False
        self._draw = motion.Tween(self, motion.MEDIUM1, "emphasized_decelerate", self._set_progress)
        self._erase = motion.Tween(self, motion.SHORT4, "emphasized_accelerate", self._set_progress)
        self.toggled.connect(self._on_toggled)

    def progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def _on_toggled(self, checked):
        self._draw.stop()
        self._erase.stop()
        if not self.isVisible():   # being filled in before the window is shown: no animation
            self._set_progress(1.0 if checked else 0.0)
        elif checked:
            self._draw.go(self._progress, 1.0)
        else:
            self._erase.go(self._progress, 0.0)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)   # the text (the stylesheet leaves the indicator itself empty)
        c = theme.current
        if not c:
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        box = QRectF(self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)
        filled = min(1.0, self._progress / FILL_SHARE)
        ticked = max(0.0, (self._progress - FILL_SHARE) / (1.0 - FILL_SHARE))
        rest = c["onSurface"] if self._hover and self.isEnabled() else c["onSurfaceVariant"]
        border = QColor(tokens.blend(rest, c["primary"], filled))
        face = QColor(c["primary"])
        face.setAlphaF(filled)
        outline = QRectF(box).adjusted(BORDER / 2, BORDER / 2, -BORDER / 2, -BORDER / 2)
        painter.setPen(QPen(border, BORDER))
        painter.setBrush(face)
        painter.drawRoundedRect(outline, BOX_RADIUS - 1, BOX_RADIUS - 1)
        if ticked > 0:
            painter.setPen(QPen(QColor(c["onPrimary"]), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(tick_path(ticked, box))
        painter.end()
