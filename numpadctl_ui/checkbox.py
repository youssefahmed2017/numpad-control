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


# ---------------------------------------------------------------- the M3 switch
TRACK_W, TRACK_H = 52.0, 32.0
THUMB_OFF, THUMB_ON, THUMB_PRESSED = 16.0, 24.0, 28.0   # M3: the thumb grows when on and again while held
HALO = 40.0                                             # the hover / press state-layer circle around the thumb


class Switch(QCheckBox):
    """Google's Material 3 switch, for settings that are simply on or off.

    Off: an outlined track with a small thumb on the left. On: a filled accent track, a bigger thumb on
    the right with a check mark in it. The thumb slides on a spring (it overshoots a hair and settles,
    like Android's) and swells while the pointer holds it. It is still a QCheckBox underneath, so
    isChecked(), toggled and the text work exactly the same as for CheckBox.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty("switch", True)   # the stylesheet makes the indicator room 52 x 32
        self._pos = 1.0 if self.isChecked() else 0.0     # 0 = off (left) .. 1 = on (right)
        self._hover = 0.0
        self._held = False
        self._slide = motion.Spring(self, "fast_spatial", self._set_pos)
        self._glow = motion.Spring(self, "default_effects", self._set_hover)
        self.toggled.connect(self._on_toggled)

    def position(self):
        return self._pos

    def _set_pos(self, value):
        self._pos = float(value)
        self.update()

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def _on_toggled(self, checked):
        if not self.isVisible():
            self._slide.stop()
            self._set_pos(1.0 if checked else 0.0)
        else:
            self._slide.go(self._pos, 1.0 if checked else 0.0)

    def enterEvent(self, event):
        if self.isEnabled():
            self._glow.go(self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._glow.go(self._hover, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._held = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._held = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)   # the text; the stylesheet leaves the indicator area empty
        c = theme.current
        if not c:
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        room = QRectF(self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self))
        track = QRectF(room.left(), room.center().y() - TRACK_H / 2, TRACK_W, TRACK_H)
        on = max(0.0, min(1.0, self._pos))   # the spring may overshoot: colours stay in range
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(DISABLED_OPACITY)
        # track: outlined surface when off, filled primary when on (cross-faded while it moves)
        fill = QColor(tokens.blend(c["surfaceContainerHighest"], c["primary"], on))
        border = QColor(c["outline"])
        border.setAlphaF(1.0 - on)
        painter.setPen(QPen(border, BORDER) if on < 1.0 else Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(track.adjusted(1, 1, -1, -1), TRACK_H / 2 - 1, TRACK_H / 2 - 1)
        # thumb: its centre slides from the left end to the right end of the track
        size = THUMB_PRESSED if self._held and self.isEnabled() else THUMB_OFF + (THUMB_ON - THUMB_OFF) * on
        x = track.left() + TRACK_H / 2 + (TRACK_W - TRACK_H) * self._pos
        centre = QPointF(x, track.center().y())
        if self._hover > 0 and self.isEnabled():
            halo = QColor(c["primary"] if self.isChecked() else c["onSurface"])
            halo.setAlphaF((tokens.STATE["pressed"] if self._held else tokens.STATE["hover"]) * self._hover)
            painter.setPen(Qt.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(centre, HALO / 2, HALO / 2)
        thumb_off = c["onSurfaceVariant"] if self._hover > 0.5 else c["outline"]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens.blend(thumb_off, c["onPrimary"], on)))
        painter.drawEllipse(centre, size / 2, size / 2)
        if on > 0.5:   # the check mark fades in on the on-thumb (M3's "with icon" switch)
            tick = QRectF(centre.x() - 8, centre.y() - 8, 16, 16)
            pen = QColor(c["onPrimaryContainer"])
            pen.setAlphaF((on - 0.5) * 2)
            painter.setPen(QPen(pen, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(tick_path(1.0, tick))
        painter.end()
