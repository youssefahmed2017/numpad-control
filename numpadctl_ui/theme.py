"""Material 3 look for the settings window: tokens (tokens.py) -> Qt palette and stylesheet."""

import subprocess
import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPalette, QPen, QPixmap

from numpadctl.platform import paths
from . import tokens

current = {}  # the colours in use, for widgets that paint themselves (the numpad keys)
listeners = []  # called with the colours after every apply(), for looks set up once (shadows)
SYSTEM_POLL_MS = 4000  # Linux desktops that don't tell Qt (Hyprland): how often to ask the portal
FONT_FAMILIES = ("Google Sans", "Roboto", "Inter", "Segoe UI", "Noto Sans")  # the first one installed is used
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def system_prefers_dark(app):
    """Qt's own answer first; on Linux desktops that don't tell Qt (e.g. Hyprland),
    ask the desktop portal or GNOME's setting, like GTK apps do."""
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    if sys.platform.startswith("linux"):
        try:
            portal = subprocess.run(
                ["busctl", "--user", "call", "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                 "org.freedesktop.portal.Settings", "ReadOne", "ss", "org.freedesktop.appearance", "color-scheme"],
                capture_output=True, text=True, timeout=2).stdout.split()
            if portal[-1:] in (["1"], ["2"]):
                return portal[-1] == "1"  # 1 = prefer dark, 2 = prefer light
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
        try:
            setting = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                                     capture_output=True, text=True, timeout=2).stdout
            return "dark" in setting
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def is_dark(app, appearance="auto"):
    return appearance == "dark" or (appearance == "auto" and system_prefers_dark(app))


def style_colors(accent, dark, contrast="standard"):
    """The tokens the stylesheet needs: M3 roles plus the state-layer mixes of the controls that have them."""
    c = tokens.colors(accent, dark, contrast)
    hover, pressed = tokens.STATE["hover"], tokens.STATE["pressed"]
    for name, base, content in (("tonal", "secondaryContainer", "onSecondaryContainer"),
                                ("filled", "primary", "onPrimary"),
                                ("key", "surfaceContainerHigh", "onSurface"),
                                ("keysel", "primaryContainer", "onPrimaryContainer"),
                                ("card", "surfaceContainer", "onSurface")):
        c[name + "Hover"] = tokens.blend(c[base], c[content], hover)
        c[name + "Pressed"] = tokens.blend(c[base], c[content], pressed)
    c["stateHover"] = tokens.rgba(c["onSurface"], hover)       # over transparent: text buttons, menu items
    c["statePressed"] = tokens.rgba(c["onSurface"], pressed)
    # a barely-there tonal gradient (lighter at the top) for the app bar and the primary button
    c["barTop"], c["primaryTop"] = tokens.blend(c["surfaceContainer"], c["onSurface"], 0.06), tokens.blend(c["primary"], "#ffffff", 0.14)
    c["primaryHover"] = tokens.rgba(c["primary"], hover)
    c["primaryPressed"] = tokens.rgba(c["primary"], pressed)
    return c


def _draw_images(c):
    """Stylesheets need image files for arrows and checkmarks; draw them in the theme's colors."""
    folder = paths.state_dir() / "qt-theme"
    folder.mkdir(parents=True, exist_ok=True)
    images = {}
    for name, color, points in (("arrow", c["onSurfaceVariant"], [(3, 6), (8, 11), (13, 6)]),
                                ("check", c["onPrimary"], [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)])):
        pixmap = QPixmap(32, 32)  # drawn at 2x for sharp edges on HiDPI
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(QPointF(*[v * 2 for v in points[0]]))
        for x, y in points[1:]:
            path.lineTo(x * 2, y * 2)
        painter.drawPath(path)
        painter.end()
        file = folder / f"{name}-{color.strip('#')}.png"
        pixmap.save(str(file))
        images[name] = file.as_posix()  # forward slashes, also on Windows
    return images


def load_fonts():
    """Register the bundled Google Sans and JetBrains Mono files, so the look doesn't depend on what the OS has
    (on Windows the fallback was a pixelated bitmap font)."""
    for file in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(file))


def monospace():
    """The font for code and logs: bundled JetBrains Mono, else the system fixed font."""
    if "JetBrains Mono" in QFontDatabase.families():
        font = QFont("JetBrains Mono")
        font.setStyleHint(QFont.Monospace)
        return font
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def _font(app):
    load_fonts()
    installed = set(QFontDatabase.families())
    family = next((f for f in FONT_FAMILIES if f in installed), None)
    if family:
        font = QFont(family)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)


def apply(app, appearance="auto", accent=tokens.DEFAULT_ACCENT, contrast="standard"):
    c = style_colors(accent, is_dark(app, appearance), contrast)
    app.setStyle("Fusion")
    _font(app)
    palette = QPalette()
    for role, key in ((QPalette.Window, "surface"), (QPalette.Base, "surfaceContainerLowest"),
                      (QPalette.AlternateBase, "surfaceContainerLow"), (QPalette.Text, "onSurface"),
                      (QPalette.WindowText, "onSurface"), (QPalette.Button, "secondaryContainer"),
                      (QPalette.ButtonText, "onSecondaryContainer"), (QPalette.ToolTipBase, "inverseSurface"),
                      (QPalette.ToolTipText, "inverseOnSurface"), (QPalette.Highlight, "primary"),
                      (QPalette.HighlightedText, "onPrimary"), (QPalette.PlaceholderText, "onSurfaceVariant")):
        palette.setColor(role, QColor(c[key]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(c["onSurfaceVariant"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["onSurfaceVariant"]))
    app.setPalette(palette)
    shape = {f"r_{name}": f"{px}px" for name, px in tokens.SHAPE.items()}
    type_ = {}
    for name, (px, weight) in tokens.TYPE.items():
        type_[f"{name}_size"], type_[f"{name}_weight"] = f"{px}px", weight
    current.clear()
    current.update(c)
    app.setStyleSheet(Template(STYLE).substitute(**c, **shape, **type_, **_draw_images(c)))
    for widget in app.allWidgets():  # the self-painted ones (keys, buttons) read `current` when they paint
        widget.update()
    for listener in list(listeners):
        listener(c)
    return c


def follow_system(app, look):
    """Re-apply when the system switches between light and dark, while the window is open.

    look() -> {"appearance", "accent", "contrast"}: the settings in use (unsaved ones too).
    Qt reports the switch on Windows, macOS and KDE; on desktops that don't tell Qt
    (Hyprland), the desktop portal is asked every few seconds instead."""
    state = {"dark": system_prefers_dark(app)}

    def check():
        settings = look()
        if settings.get("appearance", "auto") != "auto":
            return
        dark = system_prefers_dark(app)
        if dark != state["dark"]:
            state["dark"] = dark
            apply(app, "auto", settings.get("accent", tokens.DEFAULT_ACCENT), settings.get("contrast", "standard"))

    app.styleHints().colorSchemeChanged.connect(lambda _scheme: check())
    timer = None
    if sys.platform.startswith("linux") and app.styleHints().colorScheme() == Qt.ColorScheme.Unknown:
        timer = QTimer(app)
        timer.timeout.connect(check)
        timer.start(SYSTEM_POLL_MS)
    return check, timer


STYLE = """
* { font-size: ${bodyMedium_size}; }
QMainWindow, QDialog { background: ${surface}; color: ${onSurface}; }
QLabel { color: ${onSurface}; background: transparent; }
QLabel#title { font-size: ${titleLarge_size}; font-weight: ${titleLarge_weight}; }
QLabel#heading { font-size: ${titleMedium_size}; font-weight: ${titleMedium_weight}; }
QLabel#dim { color: ${onSurfaceVariant}; }
QLabel#small { color: ${onSurfaceVariant}; font-size: ${bodySmall_size}; }
QLabel#appname { font-size: ${titleLarge_size}; font-weight: ${titleLarge_weight}; }
QLabel#ok, QLabel#warn, QLabel#bad { font-size: ${labelMedium_size}; font-weight: ${labelMedium_weight};
    border-radius: 14px; }
QLabel#ok { background: ${okContainer}; color: ${onOkContainer}; }
QLabel#warn { background: ${warnContainer}; color: ${onWarnContainer}; }
QLabel#bad { background: ${errorContainer}; color: ${onErrorContainer}; }

QFrame#appbar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 ${barTop}, stop:1 ${surfaceContainer}); border-radius: ${r_xl}; }
QFrame#card { background: ${surfaceContainer}; border: none; border-radius: ${r_xl}; }
QFrame#banner { background: ${errorContainer}; border-radius: ${r_m}; }
QFrame#banner QLabel { color: ${onErrorContainer}; }
QFrame#separator { background: ${outlineVariant}; max-width: 1px; }

/* Buttons paint their own animated shape (buttons.py); the stylesheet gives text, padding and size only. */
QPushButton, QToolButton { background: transparent; border: none; }
QPushButton { color: ${onSecondaryContainer}; padding: 0 20px; min-height: 40px; font-size: ${labelLarge_size}; font-weight: ${labelLarge_weight}; }
QPushButton:disabled { color: ${onSurfaceVariant}; }
QPushButton#primary { color: ${onPrimary}; }
QPushButton#flat { color: ${primary}; padding: 0 12px; min-height: 36px; }
QPushButton#segment { color: ${onSurface}; padding: 0 16px; min-height: 36px; }
QPushButton#segment:checked { color: ${onSecondaryContainer}; }
QFrame#segments { background: transparent; border: 1px solid ${outline}; border-radius: ${r_full}; }

QPushButton#numkey { padding: 4px; min-width: 76px; min-height: 60px; }
QPushButton#numkey[selected="true"] QLabel#keyname, QPushButton#numkey[selected="true"] QLabel#keyaction { color: ${onPrimaryContainer}; }
QPushButton#numkey[layer="true"] QLabel#keyname, QPushButton#numkey[layer="true"] QLabel#keyaction { color: ${onTertiaryContainer}; }
QLabel#keyname { font-size: ${titleLarge_size}; font-weight: 600; color: ${onSurface}; }
QLabel#keyaction { font-size: ${bodySmall_size}; color: ${onSurfaceVariant}; }

QToolButton { color: ${primary}; padding: 8px 14px; font-size: ${labelLarge_size}; font-weight: ${labelLarge_weight}; }
QToolButton:checked { color: ${onTertiaryContainer}; }
QToolButton::menu-indicator { image: none; }

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget { background: transparent; color: ${onSurface};
    border: 1px solid ${outline}; border-radius: ${r_m}; padding: 8px 14px;
    selection-background-color: ${primary}; selection-color: ${onPrimary}; }
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: ${onSurface}; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus {
    border: 2px solid ${primary}; padding: 7px 13px; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: url("${arrow}"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: ${surfaceContainerHigh}; color: ${onSurface}; border: none;
    border-radius: ${r_s}; padding: 6px; outline: none; }
QComboBox QAbstractItemView::item { padding: 10px 14px; border-radius: ${r_s}; min-height: 24px; }
QComboBox QAbstractItemView::item:hover { background: ${stateHover}; }
QComboBox QAbstractItemView::item:selected { background: ${secondaryContainer}; color: ${onSecondaryContainer}; }
QListWidget { padding: 4px; }
QListWidget::item { padding: 8px 12px; border-radius: ${r_s}; }
QListWidget::item:hover { background: ${stateHover}; }
QListWidget::item:selected { background: ${secondaryContainer}; color: ${onSecondaryContainer}; }

QCheckBox { spacing: 12px; color: ${onSurface}; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: ${r_xs}; border: 2px solid ${onSurfaceVariant}; background: transparent; }
QCheckBox::indicator:hover { border-color: ${onSurface}; }
QCheckBox::indicator:checked { background: ${primary}; border-color: ${primary}; image: url("${check}"); }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle { background: ${outlineVariant}; border-radius: 4px; min-height: 32px; min-width: 32px; }
QScrollBar::handle:hover { background: ${outline}; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QMenu { background: ${surfaceContainer}; color: ${onSurface}; border: none; border-radius: ${r_l}; padding: 8px 6px; }
QMenu::item { border-radius: ${r_s}; }
QMenu::item { padding: 10px 24px; }
QMenu::item:selected { background: ${stateHover}; }
QMenu::item:disabled { color: ${onSurfaceVariant}; }
QMenu::separator { height: 1px; background: ${outlineVariant}; margin: 6px 0; }
QToolTip { background: ${inverseSurface}; color: ${inverseOnSurface}; border: none; padding: 4px 8px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStatusBar { color: ${onSurfaceVariant}; background: transparent; }
QDialogButtonBox QPushButton { min-width: 72px; }
"""
