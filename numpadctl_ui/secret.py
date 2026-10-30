"""The secret "admin console": 5 tabs of 5 silly options. Type "out" to leave (a 2 s loading bar, then everything is put back).

Everything that changes how the app looks is undone on the way out. Options that close or restart things save your
work first, and the destructive one backs the config up and only changes the open window (Discard brings it back)."""

import base64
import hashlib
import hmac
import math
import random
import shutil
import subprocess
import sys

import shiboken6
from PySide6.QtCore import QEasingCurve, QPoint, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from numpadctl import actions, config, keys, presets, ui_common

from . import egg, theme, tokens

LEAVE_MS = 2000  # the loading bar before going back to normal
RICKROLL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
GREEN = "#38ff7a"

# The SuperRoot tab. Only a salted hash of the password is in the source: finding it takes the clues.
LOCK_TITLE = "SUPERDUPERGIGASECRET"
SALT = b"numpad-superroot:"
PASSWORD_HASH = "2990914a0f21da96520852562d2fcee9688fd69cd9439dd8a40cfd3e03dd3354"
OUTSIDE = 4  # this fragment is not in the console: it is in the soda script (tools/soda)
MAX_WRONG = 4  # the fourth wrong password gets you kicked out
KICK_MS = 3000
# the seven pieces of the password, in order (the clues hand them out one by one)
_ENCODED = ['MTIz', 'QWRtaW4=', 'U3VwZXI=', 'U29kYQ==', 'QA==', 'NDQ0', 'Y2Fubm90c2Vl']  # (base64: not readable at a glance; anyone determined can still decode it)
FRAGMENTS = [base64.b64decode(piece).decode() for piece in _ENCODED]
HINTS = ["there are 7 fragments. most hide behind an option that doesn't change anything for good.",
         "read the console. read the blue screen. be patient with the rain.",
         "the fragments are numbered, and the numbers are the order. capitals matter.",
         "try these, in any order: hack the planet, spy report, credits, fortune, blue screen, self-destruct, matrix rain.",
         "six fragments are in here. the seventh lives outside, in your shell: something that fizzes."]
EIGHT_BALL = [("It is certain.", "Enter"), ("Without a doubt.", "Enter"), ("Ask again later.", "5"), ("Cannot predict now.", "5"),
              ("Don't count on it.", "Backspace"), ("My sources say no.", "Backspace"), ("Signs point to yes.", "Enter")]

STYLE = f"""
* {{ font-family: "JetBrains Mono", monospace; font-size: 13px; }}
QDialog {{ background: #0a0f0a; }}
QLabel {{ color: {GREEN}; }}
QLabel#title {{ font-size: 20px; font-weight: bold; }}
QLabel#hint {{ color: #1f9d4c; }}
QTabWidget::pane {{ border: 1px solid #1f6f3a; top: -1px; }}
QTabBar::tab {{ background: #0f1a10; color: {GREEN}; padding: 8px 14px; border: 1px solid #1f6f3a; }}
QTabBar::tab:selected {{ background: #143d1f; }}
QPushButton {{ background: #0f1a10; color: {GREEN}; border: 1px solid #1f6f3a; border-radius: 6px;
               padding: 9px 12px; text-align: left; }}
QPushButton:hover {{ background: #143d1f; }}
QPushButton:checked {{ background: {GREEN}; color: #04120a; }}
QPlainTextEdit {{ background: #050805; color: {GREEN}; border: 1px solid #1f6f3a; }}
QProgressBar {{ border: 1px solid #1f6f3a; background: #050805; color: {GREEN}; text-align: center; min-height: 22px; }}
QProgressBar::chunk {{ background: {GREEN}; }}
"""

FORTUNES = [
    "You will press the wrong key at the worst moment.",
    "A numpad is just a tiny keyboard with big dreams.",
    "The fourth piece is not in here. It fizzes in your shell. Try: soda --help",
    "Today's lucky key: 5. It is in the middle of everything.",
    "There is no key 10. We checked.",
    "Beware of the 000 key. It is three times as brave.",
    "Someone will ask what this thing is for. Say \"productivity\".",
]
HACK = ["connecting to the mainframe...", "bypassing the firewall (it was a sticky note)...",
        "decrypting 0x4E554D504144...", "downloading more RAM...", "injecting jokes into kernel...",
        "access granted. (to nothing in particular)", "FRAGMENT:1"]
CREDITS = ["NUMPADPILOT", "a cheap numpad, a lot of ideas", "", "directed by you", "written with a very patient robot",
           "tested on one (1) numpad", "", "special thanks to the key that does nothing", "FRAGMENT:3", "",
           "no keys were harmed", "THE END"]


class MatrixRain(QWidget):
    """Falling green characters over the window, until it is turned off."""
    GLYPHS = "01$#%&@*+=<>"
    TRAIL = 14

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        self.step = 16
        columns = self.width() // self.step + 1
        self.rows = self.height() // self.step + self.TRAIL
        self.heads = [random.uniform(-self.rows, 0) for _ in range(columns)]
        self.speeds = [random.uniform(0.7, 1.7) for _ in range(columns)]  # rows per frame: ~20 to 50 rows a second
        self.glyphs = [[random.choice(self.GLYPHS) for _ in range(self.rows + 1)] for _ in range(columns)]
        self.timer = QTimer(self, interval=33)
        self.timer.timeout.connect(self.advance)
        self.timer.start()
        self.show()
        self.raise_()
        theme.listeners.append(self.after_restyle)

    def after_restyle(self, _colors):
        """A new theme repolishes every widget, this one too: keep it see-through, on top and repainted."""
        try:
            self.setAttribute(Qt.WA_NoSystemBackground)
            self.setAutoFillBackground(False)
            self.raise_()
            self.update()
        except RuntimeError:  # deleted
            theme.listeners.remove(self.after_restyle)

    def advance(self):
        for i, speed in enumerate(self.speeds):
            self.heads[i] += speed
            if self.heads[i] > self.rows:
                self.heads[i] = random.randint(-20, 0)
            self.glyphs[i][random.randrange(len(self.glyphs[i]))] = random.choice(self.GLYPHS)  # one glitch per frame
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        font = QFont(theme.monospace())
        font.setPixelSize(14)
        painter.setFont(font)
        green = QColor(GREEN)
        for i, head in enumerate(self.heads):
            for trail in range(self.TRAIL):
                row = int(head) - trail
                if row < 0 or row >= len(self.glyphs[i]):
                    continue
                if trail:
                    green.setAlphaF(max(0.0, 0.85 - trail * 0.06))
                    painter.setPen(green)
                else:
                    painter.setPen(QColor("#ffffff"))
                painter.drawText(i * self.step, row * self.step + 12, self.glyphs[i][row])
        painter.end()


class FakeCrash(QLabel):
    """A fake blue screen over the window for a few seconds (click to dismiss). At 100% it holds a moment,
    long enough to read the stop code (fragment 5 of the SuperRoot password is in it)."""

    def __init__(self, parent, on_fragment=None):
        super().__init__(parent)
        self.on_fragment = on_fragment
        self.setGeometry(parent.rect())
        self.setStyleSheet("background: #0078d7; color: white; font-size: 22px; padding: 60px;")
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.percent = 0
        self.hold = 28  # ticks to stay at 100%
        self.timer = QTimer(self, interval=60)
        self.timer.timeout.connect(self.tick)
        self.tick()
        self.timer.start()
        self.show()
        self.raise_()

    def tick(self):
        if self.percent < 100:
            self.percent += 2
        else:
            self.hold -= 1
            if self.hold <= 0:
                self.deleteLater()
                return
        text = (":(\n\nYour numpad ran into a problem and needs to rest.\n"
                f"We're just collecting some error info.\n\n{self.percent}% complete\n\n")
        if self.percent >= 100:
            text += f"STOP CODE: SYMBOL_NOT_FOUND\nfragment 5/7: {FRAGMENTS[4]}\n\n"
            if self.on_fragment:
                self.on_fragment(5)
                self.on_fragment = None
        self.setText(text + "(this is fake, click to close)")

    def mousePressEvent(self, _):
        self.deleteLater()


class Flashlight(QWidget):
    """The window goes dark; only a circle around the mouse is lit."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.show()
        self.raise_()

    def paintEvent(self, _):
        painter = QPainter(self)
        centre = self.mapFromGlobal(QCursor.pos())
        gradient = QRadialGradient(centre.x(), centre.y(), 170)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.65, QColor(0, 0, 0, 10))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 238))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class SecretPanel(QDialog):
    def __init__(self, window):
        super().__init__(None)  # its own window, not stuck on top of the main one
        self.setWindowFlag(Qt.Window)
        self.setModal(False)
        self.window = window
        self.tries = 0
        self.app = QApplication.instance()
        self.keyrain = self.echo = False
        self.timers, self.overlays = [], []
        self.toggles = []  # (button, handler): switched off on the way out
        self.leaving = False
        self.typed = ""  # the last letters typed, for the secret words
        self.fragments = set()  # which pieces of the password were found (1 to 7)
        self.unlocked = False
        self.wrong = 0
        self.hint_index = 0
        self.fortune_index = 0
        self.job = None  # the running Gravity animation
        self.toggle_buttons = {}
        self.setWindowTitle("root@numpad")
        self.resize(900, 640)
        self.setStyleSheet(STYLE)
        font = QFont(theme.monospace())
        font.setPixelSize(13)
        self.setFont(font)

        self.stack = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(self.stack)
        main = QWidget()
        layout = QVBoxLayout(main)
        title = QLabel("ADMIN CONSOLE  //  root@numpad")
        title.setObjectName("title")
        layout.addWidget(title)
        warning = QLabel("unauthorised access detected. (it's you. carry on.)")
        warning.setObjectName("hint")
        layout.addWidget(warning)
        tabs = QTabWidget()
        for name, options in self.tabs():
            tabs.addTab(self.option_page(options), name)
        self.tabs_widget = tabs
        self.lock_index = tabs.addTab(self.build_lock_page(), f"🔒 {LOCK_TITLE}")
        tabs.currentChanged.connect(self.tab_changed)
        layout.addWidget(tabs, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setFixedHeight(130)
        layout.addWidget(self.log)
        hint = QLabel('type "out" to log out (in this window or the main one)')
        hint.setObjectName("hint")
        layout.addWidget(hint)
        self.stack.addWidget(main)

        kicked = QWidget()
        column = QVBoxLayout(kicked)
        column.addStretch()
        self.kick_label = QLabel("")
        self.kick_label.setObjectName("title")
        self.kick_label.setAlignment(Qt.AlignCenter)
        self.kick_label.setWordWrap(True)
        self.kick_label.setStyleSheet("color: #ff4d4d; font-size: 26px;")
        column.addWidget(self.kick_label)
        column.addStretch()
        self.stack.addWidget(kicked)  # index 1

        leaving = QWidget()
        column = QVBoxLayout(leaving)
        column.addStretch()
        self.leave_label = QLabel("logging out...")
        self.leave_label.setObjectName("title")
        self.leave_label.setAlignment(Qt.AlignCenter)
        column.addWidget(self.leave_label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        column.addWidget(self.bar)
        column.addStretch()
        self.stack.addWidget(leaving)

        window.secret = self
        window.sync_capture()  # keys are reported, not run, while the console is open
        self.say("welcome, root. 25 options, no warranty.")

    def option_page(self, options):
        page = QWidget()
        column = QVBoxLayout(page)
        for label, hint, handler, toggle in options:
            button = QPushButton(f"{label}   -   {hint}")
            button.setCheckable(toggle)
            if toggle:
                button.toggled.connect(lambda on, h=handler, l=label: self.flip(l, h, on))
                self.toggles.append((button, handler))
                self.toggle_buttons[label] = button
            else:
                button.clicked.connect(lambda _=False, h=handler: h())
            column.addWidget(button)
        column.addStretch()
        return page

    # ---------------------------------------------------------------- the SuperRoot tab
    def build_lock_page(self):
        self.lock_stack = QStackedWidget()
        locked = QWidget()
        column = QVBoxLayout(locked)
        column.addStretch()
        for text, style in (("🔒", "font-size: 56px;"), (LOCK_TITLE, "font-size: 22px; font-weight: bold;"),
                            ("CANNOT OPEN UNLESS YOU ARE SUPERROOT", "color: #ff4d4d;")):
            label = QLabel(text)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(style)
            column.addWidget(label)
        self.fragment_label = QLabel()
        self.fragment_label.setAlignment(Qt.AlignCenter)
        self.fragment_label.setObjectName("hint")
        column.addWidget(self.fragment_label)
        self.refresh_fragments()
        prompt = QLabel("enter the SuperRoot password:")
        column.addWidget(prompt)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self.check_password)
        column.addWidget(self.password)
        self.lock_status = QLabel("")
        self.lock_status.setStyleSheet("color: #ff4d4d;")
        column.addWidget(self.lock_status)
        stuck = QLabel('stuck? type "hint" anywhere in the console (not in the password box).')
        stuck.setObjectName("hint")
        column.addWidget(stuck)
        column.addStretch()
        self.lock_stack.addWidget(locked)
        self.lock_stack.addWidget(self.option_page(self.super_options()))
        return self.lock_stack

    def super_options(self):
        return [
            ("Gravity", "the numpad keys fall, bounce, and come back", self.gravity, False),
            ("Logo storm", "it's raining logos", self.logo_storm, False),
            ("Flashlight", "the lights go out. you have the mouse.", self.flashlight, True),
            ("Party mode", "everything at once for 8 seconds", self.party, False),
            ("Ask the numpad", "it knows. it always knows.", self.eight_ball, False),
        ]

    def tab_changed(self, index):
        if index == self.lock_index and not self.unlocked:
            self.say("the SuperRoot tab is locked.")
            QTimer.singleShot(0, self.password.setFocus)

    def refresh_fragments(self):
        pieces = [FRAGMENTS[i] if i + 1 in self.fragments else ("(shell)" if i == OUTSIDE - 1 else "?")
                  for i in range(len(FRAGMENTS))]
        self.fragment_label.setText("fragments:  " + "  .  ".join(pieces))

    def found(self, number):
        """A piece of the password turned up (1 to 7)."""
        flavour = {1: "the beginning", 2: "who you're pretending to be", 3: "the good kind of power", 4: "drink up",
                   5: "straight from the blue screen", 6: "the real countdown", 7: "you can't see it in the rain"}
        first = number not in self.fragments
        self.fragments.add(number)
        self.refresh_fragments()
        self.say(f"fragment {number}/7 recovered: {FRAGMENTS[number - 1]}   ({flavour[number]})")
        if first and self.fragments >= set(range(1, len(FRAGMENTS) + 1)) - {OUTSIDE}:
            self.say(f"all the fragments in here are found. number {OUTSIDE} is not in the console: ask soda, in your shell.")

    def say_line(self, line):
        if line.startswith("FRAGMENT:"):
            self.found(int(line.split(":")[1]))
        else:
            self.say(line or " ")

    def check_password(self):
        if self.unlocked or self.leaving:
            return
        guess = self.password.text()
        self.password.clear()
        digest = hashlib.sha256(SALT + guess.encode()).hexdigest()
        if hmac.compare_digest(digest, PASSWORD_HASH):
            self.unlock()
            return
        self.wrong += 1
        if self.wrong >= MAX_WRONG:
            self.kick()
            return
        reply = ["ACCESS DENIED.", "ACCESS DENIED. again?", "ACCESS DENIED. this attempt has been logged."][self.wrong - 1]
        self.lock_status.setText(reply)
        self.say(f"wrong password ({self.wrong}/{MAX_WRONG - 1}). {reply}")

    def unlock(self):
        self.unlocked = True
        self.lock_stack.setCurrentIndex(1)
        self.tabs_widget.setTabText(self.lock_index, f"🔓 {LOCK_TITLE}")
        self.say("ACCESS GRANTED. welcome, SuperRoot.")
        self.confetti(text="SUPERROOT")

    def kick(self):
        self.leaving = True
        self.say("Enough Evidence.")
        self.kick_label.setText("Enough Evidence:\nyou are exposed as unauthorized.\n\nGET OUT.")
        self.stack.setCurrentIndex(1)
        QTimer.singleShot(KICK_MS, self.finish)

    # -- SuperRoot options
    def gravity(self):
        if self.job:
            return
        surface = self.surface()
        sprites = []
        for button in self.pad_keys().values():
            if not button.isVisible():
                continue
            picture = button.grab()
            label = QLabel(surface)
            label.setPixmap(picture)
            label.setGeometry(QRect(button.mapTo(surface, QPoint(0, 0)), picture.size()))
            policy = button.sizePolicy()
            kept = policy.retainSizeWhenHidden()
            policy.setRetainSizeWhenHidden(True)  # the layout must not shift while the real key is hidden
            button.setSizePolicy(policy)
            button.hide()
            label.show()
            label.raise_()
            sprites.append({"label": label, "button": button, "kept": kept, "vy": random.uniform(-2, 2),
                            "vx": random.uniform(-3, 3)})
        floor = surface.height()
        timer = QTimer(self, interval=16)

        def step():
            for sprite in sprites:
                label = sprite["label"]
                sprite["vy"] += 1.1
                x, y = label.x() + sprite["vx"], label.y() + sprite["vy"]
                if y + label.height() >= floor:
                    y, sprite["vy"], sprite["vx"] = floor - label.height(), -sprite["vy"] * 0.55, sprite["vx"] * 0.9
                x = min(max(0, x), surface.width() - label.width())
                label.move(int(x), int(y))
        timer.timeout.connect(step)
        timer.start()
        self.job = (timer, sprites)
        self.later(3800, self.stop_gravity)

    def stop_gravity(self):
        if not self.job:
            return
        timer, sprites = self.job
        self.job = None
        timer.stop()
        for sprite in sprites:
            if shiboken6.isValid(sprite["label"]):
                sprite["label"].deleteLater()
            button = sprite["button"]
            if shiboken6.isValid(button):
                policy = button.sizePolicy()
                policy.setRetainSizeWhenHidden(sprite["kept"])
                button.setSizePolicy(policy)
                button.show()

    def logo_storm(self):
        self.confetti(text="", pieces=60, duration=3600, sprite=QPixmap(str(egg.LOGO)))

    def flashlight(self, on):
        if on:
            self.light = Flashlight(self.surface())
            self.overlays.append(self.light)
        else:
            self.light.timer.stop()
            self.light.deleteLater()
            self.overlays.remove(self.light)

    def party(self):
        names = ("Disco", "Key rain")
        for name in names:
            self.toggle_buttons[name].setChecked(True)
        self.fireworks()
        self.wave()
        self.later(8000, lambda: [self.toggle_buttons[name].setChecked(False) for name in names])

    def eight_ball(self):
        answer, key = random.choice(EIGHT_BALL)
        self.say(f"the numpad says: {answer}")
        button = self.pad_keys().get(key)
        if button:
            button.flash()

    # ---------------------------------------------------------------- the options
    def tabs(self):
        """[(tab name, [(name, what it does, handler, is it an on/off switch)])]: 5 tabs of 5."""
        return [
            ("Looks", [
                ("Disco", "the accent colour changes by itself", self.disco, True),
                ("Giant text", "everything 1.5x bigger", self.giant, True),
                ("Day and night", "flips light and dark every 2 s", self.daynight, True),
                ("Earthquake", "shakes the window", self.quake, False),
                ("Matrix rain", "it's raining characters", self.matrix, True),
            ]),
            ("Numpad", [
                ("Wave", "every key lights up in turn", self.wave, False),
                ("Key rain", "each key you press throws confetti", self.set_keyrain, True),
                ("KONAMI", "the giant text again", lambda: self.confetti(text="KONAMI"), False),
                ("Fireworks", "four bursts of confetti", self.fireworks, False),
                ("Echo", "pressed keys make three others flash", self.set_echo, True),
            ]),
            ("Sound and screen", [
                ("Beep x5", "five beeps in a row", self.beeps, False),
                ("Speakers", "mute or unmute", lambda: self.act("volume_mute", {}, "speakers toggled"), False),
                ("Microphone", "mute or unmute", lambda: self.act("mic_mute", {}, "microphone toggled"), False),
                ("Screenshot", "takes one right now", lambda: self.act("screenshot_full", {}, "screenshot taken"), False),
                ("Rickroll", "opens the link. you know the link.", lambda: self.act("open_url", {"url": RICKROLL}, "never gonna"), False),
            ]),
            ("Danger", [
                ("Restart the service", "saves your work first", self.restart_service, False),
                ("Restart this app", "saves your work first", self.restart_app, False),
                ("Quit NumpadPilot", "saves your work first", self.quit_app, False),
                ("Wipe every key", "backs the config up, clears this profile (Discard brings it back)", self.wipe, False),
                ("Self-destruct", "5 second countdown. or is it.", self.self_destruct, False),
            ]),
            ("Secret", [
                ("Hack the planet", "very real hacking", self.hack, False),
                ("Roll the credits", "you earned them", self.credits, False),
                ("Fortune", "wisdom from a numpad", self.fortune, False),
                ("Blue screen", "a fake one. mostly.", self.crash, False),
                ("Spy report", "what this app knows about you", self.spy, False),
            ]),
        ]

    def say(self, text):
        self.log.appendPlainText(f"> {text}")

    def flip(self, label, handler, on):
        handler(on)
        self.say(f"{label}: {'on' if on else 'off'}")

    def later(self, ms, fn):
        timer = QTimer(self, singleShot=True, interval=ms)
        timer.timeout.connect(fn)
        timer.start()
        self.timers.append(timer)

    def every(self, ms, fn):
        timer = QTimer(self, interval=ms)
        timer.timeout.connect(fn)
        timer.start()
        self.timers.append(timer)
        return timer

    def stop(self, timer):
        timer.stop()
        if timer in self.timers:
            self.timers.remove(timer)

    def surface(self):
        return self.window.centralWidget()

    def pad_keys(self):
        """The numpad's own key buttons (not the many keys of a keyboard picture, when one is shown)."""
        return {key: button for key, button in self.window.key_buttons.items() if not keys.split(key)[0]}

    def restore_look(self):
        look = self.window.cfg
        theme.apply(self.app, look.get("appearance", "auto"), look.get("accent", tokens.DEFAULT_ACCENT),
                    look.get("contrast", "standard"))

    # -- looks
    def disco(self, on):
        if on:
            self.disco_timer = self.every(1200, lambda: theme.apply(
                self.app, self.window.cfg.get("appearance", "auto"), random.choice(tokens.ACCENTS),
                self.window.cfg.get("contrast", "standard")))
        else:
            self.stop(self.disco_timer)
            self.restore_look()

    def giant(self, on):
        font = QFont(self.app.font())
        if on:
            self.font_before = QFont(font)
            size = font.pointSizeF()
            if size > 0:
                font.setPointSizeF(size * 1.5)
            else:
                font.setPixelSize(int(font.pixelSize() * 1.5))
            self.app.setFont(font)
        else:
            self.app.setFont(self.font_before)

    def daynight(self, on):
        if on:
            night = [False]

            def flip():
                night[0] = not night[0]
                theme.apply(self.app, "dark" if night[0] else "light",
                            self.window.cfg.get("accent", tokens.DEFAULT_ACCENT), self.window.cfg.get("contrast", "standard"))
            self.daynight_timer = self.every(2000, flip)
        else:
            self.stop(self.daynight_timer)
            self.restore_look()

    def quake(self):
        layout = self.surface().layout()
        animation = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=2500)

        def shake(t):
            dx, dy = int(math.sin(t * 70) * 14 * (1 - t)), int(math.cos(t * 53) * 10 * (1 - t))
            layout.setContentsMargins(max(0, 12 + dx), max(0, 12 + dy), max(0, 12 - dx), max(0, 8 - dy))
        animation.valueChanged.connect(shake)
        animation.finished.connect(lambda: layout.setContentsMargins(12, 12, 12, 8))
        animation.start()
        self.quake_animation = animation

    def matrix(self, on):
        if on:
            self.rain = MatrixRain(self.surface())
            self.overlays.append(self.rain)
            self.later(3500, lambda: self.toggle_buttons["Matrix rain"].isChecked() and self.found(7))
        else:
            self.rain.timer.stop()
            if self.rain.after_restyle in theme.listeners:
                theme.listeners.remove(self.rain.after_restyle)
            self.rain.deleteLater()
            self.overlays.remove(self.rain)

    # -- numpad
    def confetti(self, text=None, pieces=egg.PIECES, duration=egg.DURATION, sprite=None):
        egg.Confetti(self.surface(), text=text, pieces=pieces, duration=duration, sprite=sprite)

    def wave(self):
        for i, button in enumerate(self.pad_keys().values()):
            self.later(i * 70, button.flash)

    def fireworks(self):
        for i in range(4):
            self.later(i * 450, lambda: self.confetti(text="", pieces=70, duration=2200))

    def set_keyrain(self, on):
        self.keyrain = on

    def set_echo(self, on):
        self.echo = on

    def on_pad_key(self, key):
        """A numpad key was pressed while the console is open."""
        if self.keyrain:
            self.confetti(text="", pieces=45, duration=1600)
        if self.echo:
            others = [b for k, b in self.pad_keys().items() if k != key]
            for button in random.sample(others, min(3, len(others))):
                button.flash()

    # -- sound and screen
    def beeps(self):
        for i in range(5):
            self.later(i * 220, QApplication.beep)

    def act(self, action_id, params, done):
        binding = presets.binding(action_id, params)
        ui_common.run_in_background(
            lambda: actions.run(self.window.cfg, binding),
            lambda _result, error: self.say(done if error is None else f"failed: {error}"), self.window.dispatch)

    # -- danger (save first)
    def saved(self):
        if self.window.dirty:
            if not self.window.save():
                self.say("couldn't save your work, so I stopped.")
                return False
            self.say("saved your work first.")
        return True

    def sure(self, what):
        return QMessageBox.question(self, "Really?", what, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def restart_service(self):
        if ui_common.IS_WINDOWS:
            self.say("the service is the tray app on Windows. restart it from its icon.")
            return
        if self.saved():
            ui_common.run_in_background(
                lambda: subprocess.run(["systemctl", "--user", "restart", "numpad-control"], check=False),
                lambda _result, _error: self.say("service restarted."), self.window.dispatch)

    def restart_app(self):
        if not self.sure("Restart NumpadPilot's window? Your work is saved first.") or not self.saved():
            return
        # The new copy waits a moment, so the old one has let go of its one-copy-at-a-time lock.
        subprocess.Popen([sys.executable, "-c", "import subprocess, sys, time; time.sleep(1.5); subprocess.Popen(sys.argv[1:])",
                          sys.executable, "-m", "numpadctl", "gui"])
        self.reset()
        QTimer.singleShot(200, self.app.quit)

    def quit_app(self):
        if self.sure("Quit NumpadPilot's window? Your work is saved first.") and self.saved():
            self.reset()
            QTimer.singleShot(200, self.app.quit)

    def wipe(self):
        if not self.sure("Clear every key of this profile in the open window? Your config is backed up first, "
                         "and Discard brings the keys back."):
            return
        if not self.saved():
            return
        backup = config.CONFIG_PATH.with_name("config.before-panic.json")
        try:
            shutil.copyfile(config.CONFIG_PATH, backup)
        except OSError as error:
            self.say(f"couldn't back up ({error}), so I stopped.")
            return
        profile = self.window.profile
        for kind in ("bindings", "layer_bindings"):
            profile[kind].clear()
        self.window.mark_dirty()
        self.window.refresh_pad()
        self.window.build_editor()
        self.say(f"cleared. backup: {backup.name}. close the window and choose Discard to undo.")

    def self_destruct(self):
        count = [5]

        def tick():
            if count[0] > 0:
                self.say(f"self-destruct in {count[0]}...")
                count[0] -= 1
            else:
                self.stop(timer)
                self.say("...just kidding.")
                self.fireworks()
                self.later(900, lambda: self.found(6))
        timer = self.every(1000, tick)
        tick()

    # -- secret
    def hack(self):
        for i, line in enumerate(HACK):
            self.later(i * 450, lambda line=line: self.say_line(line))

    def credits(self):
        for i, line in enumerate(CREDITS):
            self.later(i * 500, lambda line=line: self.say_line(line))

    def fortune(self):
        self.say_line(FORTUNES[self.fortune_index % len(FORTUNES)])
        self.fortune_index += 1

    def crash(self):
        crash = FakeCrash(self.surface(), on_fragment=self.found)
        self.overlays.append(crash)
        crash.destroyed.connect(lambda _=None: self.overlays.remove(crash) if crash in self.overlays else None)

    def spy(self):
        cfg = self.window.cfg
        bound = sum(1 for p in cfg["profiles"] for slots in p["bindings"].values() for b in slots.values() if actions.is_set(b))
        self.say(f"profiles: {len(cfg['profiles'])}, keys with something to do: {bound}, "
                 f"extra keys learned: {len(cfg.get('extra_keys', []))}, accent: {cfg.get('accent')}.")
        self.say("verdict: a person of taste.")
        self.found(2)

    # ---------------------------------------------------------------- leaving
    def words(self):
        return {"out": self.leave, "hint": self.hint, "help": self.help, "sudo": self.sudo, "soda": self.soda}

    def on_letter(self, letter):
        """A letter typed in this window or the main one (the main window's key hook passes it on).
        Words typed anywhere but the password box do things: out, hint, help, sudo, soda."""
        if self.leaving or self.password.hasFocus():
            return
        self.typed = (self.typed + letter)[-12:]
        for word, handler in self.words().items():
            if self.typed.endswith(word):
                self.typed = ""
                handler()
                return

    def hint(self):
        self.say(f"hint {self.hint_index % len(HINTS) + 1}/{len(HINTS)}: {HINTS[self.hint_index % len(HINTS)]}")
        self.hint_index += 1

    def help(self):
        self.say("words you can type here: out, hint, help, sudo, soda.")

    def sudo(self):
        self.say("you are not in the sudoers file. this incident will be reported. (to nobody)")

    def soda(self):
        self.say("*psssht*  fizz fizz fizz.")
        self.confetti(text="", pieces=50, duration=1800)

    def reject(self):
        """Esc and the close button: the way out is "out", but the third try leaves anyway (never a trap)."""
        if self.leaving:
            return
        self.tries += 1
        if self.tries >= 3:
            self.leave()
        else:
            self.say(f'type "out" to leave ({3 - self.tries} more tries of Esc or close also work).')

    def leave(self):
        self.leaving = True
        self.stack.setCurrentIndex(2)
        animation = QVariantAnimation(self, startValue=0, endValue=100, duration=LEAVE_MS)
        animation.valueChanged.connect(lambda v: self.bar.setValue(int(v)))
        animation.finished.connect(self.finish)
        animation.start()
        self.leave_animation = animation

    def reset(self):
        """Put everything back the way it was."""
        for button, _handler in self.toggles:
            if shiboken6.isValid(button) and button.isChecked():
                button.setChecked(False)  # runs the handler's "off"
        self.stop_gravity()
        for timer in self.timers:
            timer.stop()
        self.timers.clear()
        for overlay in self.overlays:
            if shiboken6.isValid(overlay):  # the blue screen removes itself when it is done
                overlay.deleteLater()
        self.overlays.clear()
        self.surface().layout().setContentsMargins(12, 12, 12, 8)
        self.keyrain = self.echo = False

    def finish(self):
        try:
            self.reset()
        finally:  # whatever went wrong while tidying up, the console always closes
            QDialog.accept(self)

    def done(self, result):
        self.window.secret = None
        self.window.sync_capture()
        super().done(result)
        self.deleteLater()
