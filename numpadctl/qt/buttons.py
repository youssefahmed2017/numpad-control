"""Material 3 Expressive controls that paint and animate themselves.

Buttons morph their shape: soft corners at rest, fully round on hover, squeezed small while
pressed (all animated, with the ripple following the shape). Drop-downs and menus open with a
short reveal and the scroll area scrolls smoothly. Everything is drawn here because a Qt
stylesheet can't animate a corner radius.
"""

import time

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QComboBox, QMenu, QPushButton, QScrollArea, QStyledItemDelegate, QToolButton

from . import theme, tokens

REST_RADIUS = 10      # corner radius at rest (px)
PRESSED_RADIUS = 4    # ...while pressed
MORPH_MS = 170
PRESS_MS = 130        # the squeeze while pressed...
PRESS_HOLD_MS = 150   # ...stays at least this long, so even a quick click is seen over many frames
RELEASE_MS = 340      # then it springs back with a little overshoot
REVEAL_MS = 150
SCROLL_MS = 220
SCROLL_PX_PER_NOTCH = 72


class _Morph:
    """Mixin for QPushButton / QToolButton: an animated rounded background, then the usual text and icon."""

    def _morph_setup(self):  # call once from __init__
        self._hover = 0.0
        self._press = 0.0
        self._hover_anim = self._anim(lambda v: setattr(self, "_hover", v), MORPH_MS)
        self._press_anim = self._anim(lambda v: setattr(self, "_press", v), PRESS_MS)
        self._press_target = 0.0
        self._press_since = 0.0
        self._watch = QTimer(self, interval=20)
        self._watch.timeout.connect(self._watch_press)

    def _anim(self, apply, ms):
        animation = QVariantAnimation(self, duration=ms)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.valueChanged.connect(lambda value: (apply(value), self.update()))
        return animation

    @staticmethod
    def _go(animation, current, target):
        animation.stop()
        animation.setStartValue(float(current))
        animation.setEndValue(float(target))
        animation.start()

    def enterEvent(self, event):
        if self.isEnabled():
            self._go(self._hover_anim, self._hover, 1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(self._hover_anim, self._hover, 0)
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self._hover = 0.0
        super().changeEvent(event)

    def _update_press(self):
        """Start the squeeze when the button goes down (also true while a tool button's menu is open)."""
        if self.isDown() and self._press_target == 0.0:
            self._press_target, self._press_since = 1.0, time.monotonic()
            self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._press_anim.setDuration(PRESS_MS)
            self._go(self._press_anim, self._press, 1)
            self._watch.start()  # the release is decided here, not in paint: nothing may repaint a button after a click

    def _watch_press(self):
        """Let go after the minimum hold once the button is up, then spring back with a little overshoot."""
        if self.isDown() or time.monotonic() - self._press_since < PRESS_HOLD_MS / 1000:
            return
        self._watch.stop()
        self._press_target = 0.0
        self._press_anim.setEasingCurve(QEasingCurve.OutBack)
        self._press_anim.setDuration(RELEASE_MS)
        self._go(self._press_anim, self._press, 0)

    def current_radius(self):
        """Soft at rest, fully round on hover, small while pressed: used for painting and the ripple's clip."""
        full = self.height() / 2
        radius = REST_RADIUS + (full - REST_RADIUS) * self._hover
        return radius + (PRESSED_RADIUS - radius) * self._press

    def ripple_color(self):
        return QColor(self._look()[1])

    def _look(self):
        """(container colour or None, content colour) for this kind of button."""
        c = theme.current
        if not c:
            return None, "#000000"
        if not self.isEnabled():
            if isinstance(self, QToolButton) or self.objectName() in ("flat", "segment"):
                return None, c["onSurfaceVariant"]
            return tokens.blend(c["surfaceContainer"], c["onSurface"], 0.12), c["onSurfaceVariant"]
        name = self.objectName()
        if isinstance(self, QToolButton):
            return (c["tertiaryContainer"], c["onTertiaryContainer"]) if self.isChecked() else (None, c["primary"])
        if name == "primary":
            return c["primary"], c["onPrimary"]
        if name == "flat":
            return None, c["primary"]
        if name == "segment":
            return (c["secondaryContainer"], c["onSecondaryContainer"]) if self.isChecked() else (None, c["onSurface"])
        return c["secondaryContainer"], c["onSecondaryContainer"]

    def paintEvent(self, event):
        c = theme.current
        if not c:
            return super().paintEvent(event)
        self._update_press()
        container, content = self._look()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        rect = QRectF(self.rect())
        radius = self.current_radius()
        if container is not None:
            painter.setBrush(QColor(container))
            painter.drawRoundedRect(rect, radius, radius)
        state = tokens.STATE["hover"] * self._hover + tokens.STATE["pressed"] * self._press
        if state > 0 and self.isEnabled():
            layer = QColor(content)
            layer.setAlphaF(min(state, 0.2))
            painter.setBrush(layer)
            painter.drawRoundedRect(rect, radius, radius)
        painter.end()
        super().paintEvent(event)  # text and icon (the stylesheet draws no background of its own)


class PushButton(_Morph, QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._morph_setup()


class ToolButton(_Morph, QToolButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._morph_setup()


def reveal(popup, ms=REVEAL_MS):
    """Open a popup window with a short grow instead of appearing at once (Wayland has no window opacity)."""
    final = popup.geometry()
    if final.height() < 24:
        return
    animation = QVariantAnimation(popup, duration=ms, startValue=0.0, endValue=1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)

    def step(v):
        popup.resize(final.width(), max(12, round(final.height() * (0.55 + 0.45 * v))))

    def done():
        popup.resize(final.size())
    animation.valueChanged.connect(step)
    animation.finished.connect(done)
    step(0.0)
    animation.start(QVariantAnimation.DeleteWhenStopped)


class ComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(QStyledItemDelegate(self))  # so the stylesheet styles the rows (rounded, tonal)

    def showPopup(self):
        super().showPopup()
        reveal(self.view().window())


class Menu(QMenu):
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: reveal(self))


class SmoothScrollArea(QScrollArea):
    """Mouse-wheel scrolling glides to its target instead of jumping."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._glide = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._glide.setDuration(SCROLL_MS)
        self._glide.setEasingCurve(QEasingCurve.OutCubic)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if event.pixelDelta().y() or not event.angleDelta().y() or bar.maximum() == 0:
            return super().wheelEvent(event)  # touchpads already scroll smoothly
        running = self._glide.state() == QPropertyAnimation.Running
        start = self._glide.endValue() if running else bar.value()
        target = max(0, min(bar.maximum(), int(start) - round(event.angleDelta().y() / 120 * SCROLL_PX_PER_NOTCH)))
        self._glide.stop()
        self._glide.setStartValue(bar.value())
        self._glide.setEndValue(target)
        self._glide.start()
        event.accept()
