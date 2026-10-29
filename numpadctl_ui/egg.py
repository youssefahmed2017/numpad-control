"""Easter eggs: the Konami code on the numpad (8 8 2 2 4 6 4 6) throws confetti and a giant KONAMI;
1 1 Enter on the numpad, then u l c s m on the keyboard, opens the secret panel (secret.py)."""

import math
import random
import time
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QEasingCurve, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from . import theme

SEQUENCE = ["8", "8", "2", "2", "4", "6", "4", "6"]  # up up down down left right left right
LOGO = Path(__file__).resolve().parent.parent / "assets" / "icon-256.png"
DURATION = 3200  # ms
PIECES = 150
COMBO = [("pad", "1"), ("pad", "1"), ("pad", "Enter"), ("key", "u"), ("key", "l"), ("key", "c"), ("key", "s"), ("key", "m")]
COMBO_GAP = 1.6  # seconds allowed between two steps


class Matcher:
    """Feed it every pressed key; it says when the last ones spell the sequence."""

    def __init__(self, sequence=SEQUENCE):
        self.sequence = list(sequence)
        self.recent = []

    def press(self, key):
        self.recent = (self.recent + [key])[-len(self.sequence):]
        if self.recent == self.sequence:
            self.recent = []
            return True
        return False


class Combo:
    """A sequence across the numpad ("pad") and the keyboard ("key"); each step must follow the last within `gap` seconds."""

    def __init__(self, steps=COMBO, gap=COMBO_GAP, clock=time.monotonic):
        self.steps, self.gap, self.clock = list(steps), gap, clock
        self.progress, self.last = 0, 0.0

    def press(self, source, key):
        now = self.clock()
        if self.progress and now - self.last > self.gap:
            self.progress = 0
        step = (source, key)
        if step == self.steps[self.progress]:
            self.progress += 1
        else:
            self.progress = 1 if step == self.steps[0] else 0
        self.last = now
        if self.progress == len(self.steps):
            self.progress = 0
            return True
        return False


class Confetti(QWidget):
    """A see-through layer over the window: confetti falls and a giant `text` (or the logo) pops up, then it removes itself."""

    def __init__(self, parent, text=None, pieces=PIECES, duration=DURATION):
        super().__init__(parent)
        self.text, self.duration = text, duration
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        colors = [theme.current.get(name, "#ffffff") for name in ("primary", "secondary", "tertiary", "primaryContainer")]
        self.pieces = [{
            "x": random.random(), "delay": random.random() * 0.45, "speed": 0.35 + random.random() * 0.5,
            "sway": random.random() * 6.28, "size": 6 + random.random() * 8, "spin": random.random() * 6.28,
            "color": QColor(random.choice(colors)),
        } for _ in range(pieces)]
        self.logo = QPixmap(str(LOGO))
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.show()
        self.raise_()

    def progress(self):
        return min(1.0, self.clock.elapsed() / self.duration)

    def paintEvent(self, _):
        t = self.progress()
        if t >= 1.0:
            self.timer.stop()
            self.deleteLater()
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        width, height = self.width(), self.height()
        for piece in self.pieces:
            local = (t - piece["delay"]) / (1 - piece["delay"])
            if local <= 0:
                continue
            y = -20 + local * piece["speed"] * (height + 80) * 1.5
            x = piece["x"] * width + math.sin(local * 7 + piece["sway"]) * 24
            painter.save()
            painter.translate(x, y)
            painter.rotate(math.degrees(piece["spin"] + local * 9))
            color = QColor(piece["color"])
            color.setAlphaF(max(0.0, min(1.0, (1 - t) * 3)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(-piece["size"] / 2, -piece["size"] / 4, piece["size"], piece["size"] / 2, 2, 2)
            painter.restore()
        # The title pops in with a bounce, stays, then fades.
        pop = QEasingCurve(QEasingCurve.OutBack).valueForProgress(min(1.0, t / 0.25))
        fade = 1.0 if t < 0.7 else max(0.0, (1 - t) / 0.3)
        painter.setOpacity(fade)
        if self.text:
            self.draw_text(painter, pop, width, height)
        elif self.text is None:
            size = 200 * pop
            painter.drawPixmap(int((width - size) / 2), int((height - size) / 2 - 30), int(size), int(size), self.logo)
        painter.end()

    def draw_text(self, painter, pop, width, height):
        font = QFont(painter.font())
        font.setBold(True)
        size = height * 0.4
        font.setPixelSize(int(size))
        while QFontMetrics(font).horizontalAdvance(self.text) > width * 0.9 and size > 24:
            size *= 0.95
            font.setPixelSize(int(size))
        painter.setFont(font)
        painter.translate(width / 2, height / 2)
        painter.scale(pop, pop)
        metrics = QFontMetrics(font)
        wide, tall = metrics.horizontalAdvance(self.text) + 20, metrics.height()
        box = QRect(-wide // 2, -tall // 2, wide, tall)  # centred on the origin
        painter.setPen(QColor(0, 0, 0, 90))
        painter.drawText(box.translated(5, 7), Qt.AlignCenter, self.text)
        painter.setPen(QColor(theme.current.get("primary", "#6750a4")))
        painter.drawText(box, Qt.AlignCenter, self.text)
