"""Material 3 motion and depth: touch ripples, elevation shadows and fade-in transitions.

Everything is small and short, so it is cheap even on integrated graphics: a ripple is one
clipped circle on one button for a few hundred milliseconds, and graphics effects only live
as long as an animation (or on the one app bar).
"""

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import QAbstractButton, QCheckBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget

RIPPLE_MS = 450
RIPPLE_ALPHA = 0.16      # a bit above the 10% "pressed" state layer, fading out as it spreads
FADE_MS = 160


class Ripple(QWidget):
    """Transparent layer over a button that draws the expanding ripple, clipped to the button's shape."""

    def __init__(self, button):
        super().__init__(button)
        self.button = button
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.center = None
        self.progress = 1.0
        self.animation = QVariantAnimation(self, duration=RIPPLE_MS, startValue=0.0, endValue=1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._step)
        self.animation.finished.connect(self.update)
        self.setGeometry(button.rect())

    def start(self, point):
        self.center = point
        self.setGeometry(self.button.rect())
        self.raise_()
        self.animation.stop()
        self.animation.start()

    def _step(self, value):
        self.progress = value
        self.update()

    def corner_radius(self):
        morph = getattr(self.button, "current_radius", None)
        if morph:  # morphing buttons: the ripple is clipped to the shape as it is right now
            return float(morph())
        r = self.button.property("rippleRadius")  # a button can state its own corner radius
        if r is None:
            r = 22 if self.button.objectName() == "numkey" else self.height() / 2  # pills are fully round
        return float(r)

    def paintEvent(self, event):
        if self.center is None or self.animation.state() != QVariantAnimation.Running:
            return
        color_for = getattr(self.button, "ripple_color", None)
        color = QColor(color_for() if color_for else self.button.palette().color(QPalette.ButtonText))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()), self.corner_radius(), self.corner_radius())
        p.setClipPath(shape)
        far = max(((self.center.x() - x) ** 2 + (self.center.y() - y) ** 2) ** 0.5
                  for x in (0, self.width()) for y in (0, self.height()))
        color.setAlphaF(RIPPLE_ALPHA * (1 - self.progress ** 2))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(self.center, far * self.progress, far * self.progress)


class RippleFilter(QObject):
    """Install on the QApplication: every push button, tool button and key gets a ripple when pressed."""

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.MouseButtonPress and isinstance(obj, QAbstractButton) \
                and not isinstance(obj, QCheckBox) and obj.isEnabled() and event.button() == Qt.LeftButton:
            layer = obj.findChild(Ripple, options=Qt.FindDirectChildrenOnly) or Ripple(obj)
            layer.show()
            layer.start(event.position())
        elif kind == QEvent.Resize and isinstance(obj, QAbstractButton):
            layer = obj.findChild(Ripple, options=Qt.FindDirectChildrenOnly)
            if layer:
                layer.setGeometry(obj.rect())
        return False


def elevate(widget, level=1, dark=True):
    """A soft drop shadow, M3 elevation level 1-3 (one widget only: shadows cost a repaint of the widget)."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius({1: 14, 2: 22, 3: 30}[level])
    shadow.setOffset(0, {1: 2, 2: 4, 3: 6}[level])
    shadow.setColor(QColor(0, 0, 0, 150 if dark else 55))
    widget.setGraphicsEffect(shadow)


def fade_in(widget, ms=FADE_MS):
    """Fade a widget in; the effect removes itself afterwards so it costs nothing at rest."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(ms)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)

    def done():
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
    animation.finished.connect(done)
    animation.start(QPropertyAnimation.DeleteWhenStopped)
    return animation

