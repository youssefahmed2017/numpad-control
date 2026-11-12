"""Material 3 motion: easing curves, duration tokens and the spring physics of M3 Expressive.

Every animation in the window takes its feel from here instead of its own numbers, so the whole
app moves as one thing: shapes and positions use springs (they can overshoot a little and settle,
"spatial"), colour and opacity use springs that never overshoot ("effects"), and anything on a
fixed clock uses a named duration with a named curve.

The numbers are Material 3's published tokens (as ported in the Compose / Flutter motion schemes):
  easing    emphasized, emphasized decelerate (things arriving), emphasized accelerate (things
            leaving), standard, standard decelerate / accelerate
  duration  short 50-200 ms, medium 250-400 ms, long 450-600 ms, extra long 700-1000 ms
  springs   expressive spatial: fast 800 / 0.6, default 380 / 0.8, slow 200 / 0.8 (stiffness / damping)
            effects: fast 3800, default 1600, slow 800, all damping 1.0 (no overshoot)

How it runs: a Tween or Spring owns an ordinary linear QVariantAnimation (0 to 1) and maps its
progress through the curve in plain Python. It does not use QEasingCurve for this: PySide6 crashes
(heap corruption) with Bezier-spline curves and with Python functions as curves, and with Python
subclasses of animations. Nothing here crosses into Qt except a plain timer.
"""

import functools
import math

from PySide6.QtCore import QVariantAnimation

# ---------------------------------------------------------------- duration tokens (ms)
SHORT1, SHORT2, SHORT3, SHORT4 = 50, 100, 150, 200
MEDIUM1, MEDIUM2, MEDIUM3, MEDIUM4 = 250, 300, 350, 400
LONG1, LONG2, LONG3, LONG4 = 450, 500, 550, 600
EXTRA_LONG1, EXTRA_LONG2, EXTRA_LONG3, EXTRA_LONG4 = 700, 800, 900, 1000

# ---------------------------------------------------------------- easing curves
# cubic-bezier control points (x1, y1, x2, y2). "emphasized" is a two-segment path in the spec.
_CUBIC = {
    "standard": (0.2, 0.0, 0.0, 1.0),
    "standard_decelerate": (0.0, 0.0, 0.0, 1.0),
    "standard_accelerate": (0.3, 0.0, 1.0, 1.0),
    "emphasized_decelerate": (0.05, 0.7, 0.1, 1.0),
    "emphasized_accelerate": (0.3, 0.0, 0.8, 0.15),
}
# M 0,0 C 0.05,0, 0.133333,0.06, 0.166666,0.4 C 0.208333,0.82, 0.25,1, 1,1
_EMPHASIZED = ((0.05, 0.0, 0.133333, 0.06, 0.166666, 0.4), (0.208333, 0.82, 0.25, 1.0, 1.0, 1.0))

EASINGS = tuple(_CUBIC) + ("emphasized",)


def bezier_points(name):
    """The curve's bezier segments as ((x1, y1, x2, y2, x, y), ...), each starting where the last one ended."""
    if name == "emphasized":
        return _EMPHASIZED
    x1, y1, x2, y2 = _CUBIC[name]
    return ((x1, y1, x2, y2, 1.0, 1.0),)


def _cubic(a, b, c, d, s):
    u = 1.0 - s
    return u * u * u * a + 3 * u * u * s * b + 3 * u * s * s * c + s * s * s * d


@functools.lru_cache(maxsize=None)
def ease(name):
    """A function f(progress) -> value for one of EASINGS: 0 at 0, 1 at 1 (progress is time, value is distance)."""
    segments, start = [], (0.0, 0.0)
    for x1, y1, x2, y2, x, y in bezier_points(name):
        segments.append((start, (x1, y1), (x2, y2), (x, y)))
        start = (x, y)

    def curve(progress):
        if progress <= 0.0:
            return 0.0
        if progress >= 1.0:
            return 1.0
        for (x0, y0), (x1, y1), (x2, y2), (x3, y3) in segments:
            if progress <= x3:
                low, high = 0.0, 1.0
                for _ in range(40):  # x rises with s, so bisect for the s that lands on this time
                    mid = (low + high) / 2
                    if _cubic(x0, x1, x2, x3, mid) < progress:
                        low = mid
                    else:
                        high = mid
                return _cubic(y0, y1, y2, y3, (low + high) / 2)
        return 1.0
    return curve


# ---------------------------------------------------------------- springs
# name -> (damping ratio, stiffness). Mass is 1, as in Compose's spring().
SPRINGS = {
    "fast_spatial": (0.6, 800.0),
    "default_spatial": (0.8, 380.0),
    "slow_spatial": (0.8, 200.0),
    "fast_effects": (1.0, 3800.0),
    "default_effects": (1.0, 1600.0),
    "slow_effects": (1.0, 800.0),
}
SETTLE = 0.002  # a spring is "done" when it is within this share of its target (0.2 %)


def spring_value(damping, stiffness, seconds):
    """Where a spring that starts at 0 and is pulled towards 1 is after `seconds` (the unit step response)."""
    if seconds <= 0:
        return 0.0
    omega = math.sqrt(stiffness)
    if damping < 1.0:
        wd = omega * math.sqrt(1.0 - damping * damping)
        decay = math.exp(-damping * omega * seconds)
        return 1.0 - decay * (math.cos(wd * seconds) + damping * omega / wd * math.sin(wd * seconds))
    if damping == 1.0:
        return 1.0 - math.exp(-omega * seconds) * (1.0 + omega * seconds)
    root = math.sqrt(damping * damping - 1.0)  # over-damped: two real decays
    r1, r2 = omega * (-damping + root), omega * (-damping - root)
    return 1.0 - (r2 * math.exp(r1 * seconds) - r1 * math.exp(r2 * seconds)) / (r2 - r1)


@functools.lru_cache(maxsize=None)
def spring_duration(damping, stiffness):
    """Milliseconds until the spring stays within SETTLE of its target (so the animation can stop there)."""
    step = 0.002
    last_outside = 0.0
    seconds = 0.0
    while seconds < 4.0:
        seconds += step
        if abs(1.0 - spring_value(damping, stiffness, seconds)) > SETTLE:
            last_outside = seconds
    return max(1, round((last_outside + step) * 1000))


def overshoot(damping):
    """How far past its target a spring goes, as a share of the distance (0 for damping 1 or more)."""
    return math.exp(-math.pi * damping / math.sqrt(1.0 - damping * damping)) if damping < 1.0 else 0.0


# ---------------------------------------------------------------- the user's motion settings
# Settings → Appearance (config.look_settings): "animations" off makes every move jump to its end at once
# (its done-callbacks still run, so nothing waits for an animation that never comes); "speed" scales every
# duration (2.0 = twice as fast). Springs keep their shape: only the clock they run on is sped up or slowed.
SETTINGS = {"enabled": True, "speed": 1.0}


def configure(enabled=True, speed=1.0):
    SETTINGS["enabled"] = bool(enabled)
    SETTINGS["speed"] = max(0.25, min(3.0, float(speed)))


# ---------------------------------------------------------------- moving values
class _Move:
    """Moves a value from one number to another, calling apply(value) every frame. Retarget with go()."""

    def __init__(self, parent, ms, apply):
        self._apply = apply
        self._from = self._to = 0.0
        self._base = ms           # the token's duration; the running one is scaled by SETTINGS["speed"]
        self._done = []
        self._animation = QVariantAnimation(parent, startValue=0.0, endValue=1.0)
        self._animation.setDuration(ms)
        self._animation.valueChanged.connect(lambda progress, move=self: move._step(progress))

    @property
    def duration(self):
        return self._animation.duration()

    def fraction(self, progress):
        """How much of the distance is covered at `progress` (0 to 1) of the time."""
        raise NotImplementedError

    def running(self):
        return self._animation.state() == QVariantAnimation.Running

    def go(self, current, target):
        """Move from `current` to `target`, starting now (also fine in the middle of a move)."""
        self._animation.stop()
        self._from, self._to = float(current), float(target)
        if not SETTINGS["enabled"]:   # animations off: straight to the end, and say it's done
            self._step(1.0)
            for callback in list(self._done):
                callback()
            return
        self._animation.setDuration(max(1, round(self._base / SETTINGS["speed"])))
        self._animation.start()

    def stop(self):
        self._animation.stop()

    def when_done(self, callback):
        """Call callback() each time a move ends."""
        self._done.append(callback)
        self._animation.finished.connect(callback)

    def set_time(self, ms):
        """Jump to `ms` into the move (for tests and for stepping by hand)."""
        self._animation.setCurrentTime(ms)

    def value_at(self, progress):
        return self._from + (self._to - self._from) * self.fraction(progress)

    def _step(self, progress):
        self._apply(self.value_at(float(progress)))


class Tween(_Move):
    """A move on a clock: a duration token and a named easing curve.

        Tween(widget, motion.MEDIUM1, "emphasized_decelerate", lambda v: ...).go(0, 1)"""

    def __init__(self, parent, ms, curve, apply):
        super().__init__(parent, ms, apply)
        self._ease = ease(curve)

    def fraction(self, progress):
        return self._ease(progress)


class Spring(_Move):
    """A move that follows the named spring in SPRINGS. A spatial spring runs past its target a little
    before it settles; an effects spring does not."""

    def __init__(self, parent, name, apply):
        self.damping, self.stiffness = SPRINGS[name]
        super().__init__(parent, spring_duration(self.damping, self.stiffness), apply)

    def set_spring(self, name):
        """Follow another spring from now on (a button squeezes with one and bounces back with another)."""
        self.damping, self.stiffness = SPRINGS[name]
        self._base = spring_duration(self.damping, self.stiffness)
        self._animation.setDuration(self._base)

    def fraction(self, progress):
        if progress >= 1.0:
            return 1.0
        return spring_value(self.damping, self.stiffness, progress * self._base / 1000.0)   # the spring's own time
