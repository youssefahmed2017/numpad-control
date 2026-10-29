"""The secret "admin console": 5 tabs of 5 silly options. Type "out" to leave (a 2 s loading bar, then everything is put back).

Everything that changes how the app looks is undone on the way out. Options that close or restart things save your
work first, and the destructive one backs the config up and only changes the open window (Discard brings it back)."""

import math
import random
import shutil
import subprocess
import sys

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from numpadctl import actions, config, presets, ui_common

from . import egg, theme, tokens

LEAVE_MS = 2000  # the loading bar before going back to normal
OUT = ["o", "u", "t"]
RICKROLL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
GREEN = "#38ff7a"

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
    "Today's lucky key: 5. It is in the middle of everything.",
    "There is no key 10. We checked.",
    "Beware of the 000 key. It is three times as brave.",
    "Someone will ask what this thing is for. Say \"productivity\".",
]
HACK = ["connecting to the mainframe...", "bypassing the firewall (it was a sticky note)...",
        "decrypting 0x4E554D504144...", "downloading more RAM...", "injecting jokes into kernel...",
        "access granted. (to nothing in particular)"]
CREDITS = ["NUMPADPILOT", "a cheap numpad, a lot of ideas", "", "directed by you", "written with a very patient robot",
           "tested on one (1) numpad", "", "no keys were harmed", "THE END"]


class MatrixRain(QWidget):
    """Falling green characters over the window, until it is turned off."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        self.step = 16
        self.heads = [random.randint(-40, 0) for _ in range(self.width() // self.step + 1)]
        self.speeds = [random.uniform(0.35, 0.9) for _ in self.heads]
        self.timer = QTimer(self, interval=50)
        self.timer.timeout.connect(self.advance)
        self.timer.start()
        self.show()
        self.raise_()

    def advance(self):
        rows = self.height() // self.step + 14
        for i, speed in enumerate(self.speeds):
            self.heads[i] += speed
            if self.heads[i] > rows:
                self.heads[i] = random.randint(-20, 0)
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        font = QFont(theme.monospace())
        font.setPixelSize(14)
        painter.setFont(font)
        for i, head in enumerate(self.heads):
            for trail in range(14):
                row = int(head) - trail
                if row < 0:
                    continue
                color = QColor(GREEN)
                color.setAlphaF(max(0.0, 0.85 - trail * 0.06))
                painter.setPen(color if trail else QColor("#ffffff"))
                painter.drawText(i * self.step, row * self.step + 12, random.choice("01$#%&@*+=<>ｱｲｳｴｵ"))
        painter.end()


class FakeCrash(QLabel):
    """A fake blue screen over the window for a few seconds (click to dismiss)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setStyleSheet("background: #0078d7; color: white; font-size: 22px; padding: 60px;")
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.percent = 0
        self.timer = QTimer(self, interval=60)
        self.timer.timeout.connect(self.tick)
        self.tick()
        self.timer.start()
        self.show()
        self.raise_()

    def tick(self):
        self.percent += 2
        if self.percent > 100:
            self.deleteLater()
            return
        self.setText(":(\n\nYour numpad ran into a problem and needs to rest.\n"
                     f"We're just collecting some error info.\n\n{self.percent}% complete\n\n"
                     "(this is fake, click to close)")

    def mousePressEvent(self, _):
        self.deleteLater()


class SecretPanel(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.app = QApplication.instance()
        self.keyrain = self.echo = False
        self.timers, self.overlays = [], []
        self.toggles = []  # (button, handler): switched off on the way out
        self.leaving = False
        self.out = egg.Matcher(OUT)
        self.setWindowTitle("root@numpad")
        self.resize(700, 600)
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
            page = QWidget()
            column = QVBoxLayout(page)
            for label, hint, handler, toggle in options:
                button = QPushButton(f"{label}   -   {hint}")
                button.setCheckable(toggle)
                if toggle:
                    button.toggled.connect(lambda on, h=handler, l=label: self.flip(l, h, on))
                    self.toggles.append((button, handler))
                else:
                    button.clicked.connect(lambda _=False, h=handler: h())
                column.addWidget(button)
            column.addStretch()
            tabs.addTab(page, name)
        layout.addWidget(tabs, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setFixedHeight(130)
        layout.addWidget(self.log)
        hint = QLabel('type "out" to log out')
        hint.setObjectName("hint")
        layout.addWidget(hint)
        self.stack.addWidget(main)

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
                ("Fortune", "wisdom from a numpad", lambda: self.say(random.choice(FORTUNES)), False),
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

    def restore_look(self):
        look = self.window.cfg
        theme.apply(self.app, look.get("appearance", "auto"), look.get("accent", tokens.DEFAULT_ACCENT),
                    look.get("contrast", "standard"))

    # -- looks
    def disco(self, on):
        if on:
            self.disco_timer = self.every(700, lambda: theme.apply(
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
        else:
            self.rain.timer.stop()
            self.rain.deleteLater()
            self.overlays.remove(self.rain)

    # -- numpad
    def confetti(self, text=None, pieces=egg.PIECES, duration=egg.DURATION):
        egg.Confetti(self.surface(), text=text, pieces=pieces, duration=duration)

    def wave(self):
        for i, button in enumerate(self.window.key_buttons.values()):
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
            others = [b for k, b in self.window.key_buttons.items() if k != key]
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
        timer = self.every(1000, tick)
        tick()

    # -- secret
    def hack(self):
        for i, line in enumerate(HACK):
            self.later(i * 450, lambda line=line: self.say(line))

    def credits(self):
        for i, line in enumerate(CREDITS):
            self.later(i * 500, lambda line=line: self.say(line or " "))

    def crash(self):
        crash = FakeCrash(self.surface())
        self.overlays.append(crash)

    def spy(self):
        cfg = self.window.cfg
        bound = sum(1 for p in cfg["profiles"] for slots in p["bindings"].values() for b in slots.values() if actions.is_set(b))
        self.say(f"profiles: {len(cfg['profiles'])}, keys with something to do: {bound}, "
                 f"extra keys learned: {len(cfg.get('extra_keys', []))}, accent: {cfg.get('accent')}.")
        self.say("verdict: a person of taste.")

    # ---------------------------------------------------------------- leaving
    def keyPressEvent(self, event):
        if self.leaving:
            return
        letter = egg.letter_of(event)
        if letter and self.out.press(letter):
            self.leave()

    def reject(self):
        self.say('the only way out is to type "out".')  # Esc and the close button don't leave

    def leave(self):
        self.leaving = True
        self.stack.setCurrentIndex(1)
        animation = QVariantAnimation(self, startValue=0, endValue=100, duration=LEAVE_MS)
        animation.valueChanged.connect(lambda v: self.bar.setValue(int(v)))
        animation.finished.connect(self.finish)
        animation.start()
        self.leave_animation = animation

    def reset(self):
        """Put everything back the way it was."""
        for button, _handler in self.toggles:
            if button.isChecked():
                button.setChecked(False)  # runs the handler's "off"
        for timer in self.timers:
            timer.stop()
        self.timers.clear()
        for overlay in self.overlays:
            overlay.deleteLater()
        self.overlays.clear()
        self.surface().layout().setContentsMargins(12, 12, 12, 8)
        self.keyrain = self.echo = False

    def finish(self):
        self.reset()
        QDialog.accept(self)

    def done(self, result):
        self.window.secret = None
        self.window.sync_capture()
        super().done(result)
