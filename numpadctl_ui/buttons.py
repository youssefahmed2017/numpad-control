"""Material 3 Expressive controls that paint and animate themselves.

Buttons morph their shape like Google's M3 Expressive buttons: a full pill at rest, squeezed to
small corners while pressed, then springing back (all animated, with the ripple following the
shape). Hover only lays the state colour over it. Icons come from Material Symbols (icons.py) and
are drawn in the button's own content colour. Drop-downs and menus open with a
short reveal and the scroll area scrolls smoothly. Everything is drawn here because a Qt
stylesheet can't animate a corner radius.
"""

import time

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractScrollArea, QComboBox, QMenu, QPushButton, QScrollArea, QSpinBox, QStyledItemDelegate, QToolButton

from . import icons, motion, theme, tokens

PRESSED_RADIUS = 8    # corner radius while pressed (px); at rest a button is a full pill
PRESS_HOLD_MS = 150   # the squeeze stays at least this long, so even a quick click is seen over many frames
SCROLL_PX_PER_NOTCH = 72


class _Morph:
    """Mixin for QPushButton / QToolButton: an animated rounded background, then the usual text and icon."""

    def _morph_setup(self):  # call once from __init__
        self._hover = 0.0
        self._press = 0.0
        self._hover_anim = self._spring(lambda v: setattr(self, "_hover", v), "default_spatial")
        self._press_anim = self._spring(lambda v: setattr(self, "_press", v), "fast_effects")
        self._press_target = 0.0
        self._press_since = 0.0
        self._watch = QTimer(self, interval=20)
        self._watch.timeout.connect(self._watch_press)

    def _spring(self, apply, name):
        return motion.Spring(self, name, lambda value: (apply(value), self.update()))

    @staticmethod
    def _go(spring, current, target):
        spring.go(current, target)

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
            self._press_anim.set_spring("fast_effects")  # down: quick, no overshoot
            self._go(self._press_anim, self._press, 1)
            self._watch.start()  # the release is decided here, not in paint: nothing may repaint a button after a click

    def _watch_press(self):
        """Let go after the minimum hold once the button is up, then spring back with a little overshoot."""
        if self.isDown() or time.monotonic() - self._press_since < PRESS_HOLD_MS / 1000:
            return
        self._watch.stop()
        self._press_target = 0.0
        self._press_anim.set_spring("fast_spatial")  # up: springs back past rest and settles
        self._go(self._press_anim, self._press, 0)

    def current_radius(self):
        """A full pill at rest, small corners while pressed: used for painting and the ripple's clip."""
        full = self.height() / 2
        return full + (min(PRESSED_RADIUS, full) - full) * self._press

    def _sync_icon(self, content):
        """Draw the button's Material Symbol (set_symbol) in its content colour; a selected segment shows a tick."""
        name = self.property("symbol")
        if self.objectName() == "segment":
            name = "check" if self.isChecked() else None
        if not name:
            if getattr(self, "_icon_key", None):
                self._icon_key = None
                self.setIcon(icons.QIcon())
            return
        size = self.iconSize().height() or icons.SIZE
        key = (name, content, size)
        if getattr(self, "_icon_key", None) != key:
            self._icon_key = key
            self.setIcon(icons.icon(name, content, size, fill=1.0 if self.isCheckable() and self.isChecked() else 0.0))

    def ripple_color(self):
        return QColor(self._look()[1])

    def _look(self):
        """(container colour or None, content colour) for this kind of button."""
        c = theme.current
        if not c:
            return None, "#000000"
        if not self.isEnabled():
            if isinstance(self, QToolButton) or self.objectName() in ("flat", "segment", "icon"):
                return None, c["onSurfaceVariant"]
            return tokens.blend(c["surfaceContainer"], c["onSurface"], 0.12), c["onSurfaceVariant"]
        name = self.objectName()
        if name == "icon":   # M3 standard icon button: no container, a tonal one while its menu is open
            return (c["secondaryContainer"], c["onSecondaryContainer"]) if self.isChecked() else (None, c["onSurfaceVariant"])
        if isinstance(self, QToolButton):
            return (c["secondaryContainer"], c["onSecondaryContainer"]) if self.isChecked() else (None, c["primary"])
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
        self._sync_icon(content)
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


def reveal(popup, ms=motion.MEDIUM1):
    """Open a popup window with a short grow instead of appearing at once (Wayland has no window opacity)."""
    final = popup.geometry()
    if final.height() < 24:
        return

    def step(v):
        popup.resize(final.width(), max(12, round(final.height() * (0.55 + 0.45 * v))))

    tween = motion.Tween(popup, ms, "emphasized_decelerate", step)
    tween.when_done(lambda: popup.resize(final.size()))
    step(0.0)
    tween.go(0.0, 1.0)


def scroll_page(widget, event):
    """Give a wheel event to the scroll area around `widget` (the page), not to the widget."""
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QAbstractScrollArea):
        parent = parent.parentWidget()
    if parent is None:
        event.ignore()
        return
    parent.wheelEvent(event)
    event.accept()


class ComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(QStyledItemDelegate(self))  # so the stylesheet styles the rows (rounded, tonal)
        self.setFocusPolicy(Qt.StrongFocus)  # the wheel doesn't give it focus either

    def wheelEvent(self, event):
        scroll_page(self, event)  # scrolling over it scrolls the page; choosing takes a click

    def showPopup(self):
        super().showPopup()
        reveal(self.view().window())


class SpinBox(QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        scroll_page(self, event)  # like ComboBox: the wheel scrolls the page; type or use the arrows


class Menu(QMenu):
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: reveal(self))


class SmoothScrollArea(QScrollArea):
    """Mouse-wheel scrolling glides to its target instead of jumping."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bar = self.verticalScrollBar()
        self._glide = motion.Tween(self, motion.MEDIUM1, "standard_decelerate", lambda v: bar.setValue(round(v)))
        self._glide_target = 0

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if event.pixelDelta().y() or not event.angleDelta().y() or bar.maximum() == 0:
            return super().wheelEvent(event)  # touchpads already scroll smoothly
        start = self._glide_target if self._glide.running() else bar.value()
        target = max(0, min(bar.maximum(), int(start) - round(event.angleDelta().y() / 120 * SCROLL_PX_PER_NOTCH)))
        self._glide_target = target
        self._glide.go(bar.value(), target)
        event.accept()
