"""A small easter egg: the Konami code on the numpad (8 8 2 2 4 6 4 6 0 Enter) throws confetti."""

import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QEasingCurve, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from . import theme

SEQUENCE = ["8", "8", "2", "2", "4", "6", "4", "6", "0", "Enter"]  # up up down down left right left right B A
LOGO = Path(__file__).resolve().parent.parent / "assets" / "icon-256.png"
DURATION = 3200  # ms
PIECES = 150


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


class Confetti(QWidget):
    """A see-through layer over the window: confetti falls and the logo pops up, then it removes itself."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        colors = [theme.current.get(name, "#ffffff") for name in ("primary", "secondary", "tertiary", "primaryContainer")]
        self.pieces = [{
            "x": random.random(), "delay": random.random() * 0.45, "speed": 0.35 + random.random() * 0.5,
            "sway": random.random() * 6.28, "size": 6 + random.random() * 8, "spin": random.random() * 6.28,
            "color": QColor(random.choice(colors)),
        } for _ in range(PIECES)]
        self.logo = QPixmap(str(LOGO))
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.show()
        self.raise_()

    def progress(self):
        return min(1.0, self.clock.elapsed() / DURATION)

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
        # The logo pops in with a bounce, stays, then fades.
        pop = QEasingCurve(QEasingCurve.OutBack).valueForProgress(min(1.0, t / 0.25))
        fade = 1.0 if t < 0.7 else max(0.0, (1 - t) / 0.3)
        size = 200 * pop
        painter.setOpacity(fade)
        top = int((height - size) / 2 - 30)
        painter.drawPixmap(int((width - size) / 2), top, int(size), int(size), self.logo)
        if pop > 0.9:
            painter.setPen(QColor(theme.current.get("onSurface", "#000000")))
            font = painter.font()
            font.setPointSize(16)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(0, top + int(size) + 12, width, 32, Qt.AlignHCenter | Qt.AlignTop, "+30 lives")
        painter.end()
