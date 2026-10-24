"""Colors and styling: a clean look close to GNOME's, in dark or light."""

import subprocess
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap

from ..platform import paths

DARK = dict(window="#242424", panel="#2b2b2b", card="#353535", base="#1d1d1d", text="#f2f2f2",
            dim="#a0a0a0", border="#3e3e3e", button="#404040", hover="#4b4b4b",
            accent="#3584e4", accent_text="#ffffff", success="#8ff0a4", warning="#f8e45c",
            error="#ff7b63", banner="#5a4a12")
LIGHT = dict(window="#f6f5f4", panel="#ffffff", card="#ffffff", base="#ffffff", text="#1e1e1e",
             dim="#6e6e6e", border="#d8d8d8", button="#e8e8e7", hover="#dcdcdb",
             accent="#3584e4", accent_text="#ffffff", success="#1b8a3e", warning="#9c6e03",
             error="#c01c28", banner="#fdf0b8")


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


def colors_for(app, appearance="auto"):
    dark = appearance == "dark" or (appearance == "auto" and system_prefers_dark(app))
    return DARK if dark else LIGHT


def _draw_images(c):
    """Stylesheets need image files for arrows and checkmarks; draw them in the theme's colors."""
    folder = paths.state_dir() / "qt-theme"
    folder.mkdir(parents=True, exist_ok=True)
    images = {}
    for name, color, points in (("arrow", c["dim"], [(3, 6), (8, 11), (13, 6)]),
                                ("check", c["accent_text"], [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)])):
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
        file = folder / f"{name}-{c['dim'].strip('#')}.png"
        pixmap.save(str(file))
        images[name] = file.as_posix()  # forward slashes, also on Windows
    return images


def apply(app, appearance="auto"):
    c = colors_for(app, appearance)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in ((QPalette.Window, "window"), (QPalette.Base, "base"), (QPalette.AlternateBase, "panel"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "button"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "card"), (QPalette.ToolTipText, "text"),
                      (QPalette.Highlight, "accent"), (QPalette.HighlightedText, "accent_text"),
                      (QPalette.PlaceholderText, "dim")):
        palette.setColor(role, QColor(c[key]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(c["dim"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["dim"]))
    app.setPalette(palette)
    app.setStyleSheet(STYLE.format(**c, **_draw_images(c)))
    return c


STYLE = """
QWidget {{ font-size: 10pt; }}
QMainWindow, QDialog {{ background: {window}; }}
QLabel#title {{ font-size: 13pt; font-weight: 700; }}
QLabel#heading {{ font-weight: 700; }}
QLabel#dim {{ color: {dim}; }}
QLabel#small {{ color: {dim}; font-size: 9pt; }}
QLabel#ok {{ color: {success}; }}
QLabel#warn {{ color: {warning}; }}
QLabel#bad {{ color: {error}; }}
QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#banner {{ background: {banner}; border-radius: 10px; }}
QFrame#separator {{ background: {border}; max-width: 1px; }}

QPushButton {{ background: {button}; border: none; border-radius: 8px; padding: 6px 14px; color: {text}; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {dim}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {button}; color: {dim}; }}
QPushButton#flat {{ background: transparent; padding: 4px 8px; }}
QPushButton#flat:hover {{ background: {hover}; }}
QPushButton#segment {{ border-radius: 8px; padding: 6px 10px; background: transparent; }}
QPushButton#segment:checked {{ background: {hover}; font-weight: 600; }}
QFrame#segments {{ background: {button}; border-radius: 10px; }}

QPushButton#numkey {{ background: {button}; border-radius: 14px; padding: 4px; min-width: 76px; min-height: 58px; }}
QPushButton#numkey:hover {{ background: {hover}; }}
QPushButton#numkey[selected="true"] {{ background: {accent}; }}
QPushButton#numkey[selected="true"] QLabel {{ color: {accent_text}; }}
QPushButton#numkey[flash="true"] {{ border: 3px solid {accent}; }}
QLabel#keyname {{ font-size: 15pt; font-weight: 800; background: transparent; }}
QLabel#keyaction {{ font-size: 8pt; color: {dim}; background: transparent; }}

QToolButton {{ border: none; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {hover}; }}
QToolButton:checked {{ background: {accent}; color: {accent_text}; }}
QToolButton::menu-indicator {{ image: none; }}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {base}; border: 1px solid {border}; border-radius: 8px; padding: 5px 8px; color: {text};
    selection-background-color: {accent}; selection-color: {accent_text}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {border}; background: {base}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {border}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {dim}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QComboBox QAbstractItemView {{ background: {card}; border: 1px solid {border}; selection-background-color: {accent}; }}
QMenu {{ background: {card}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 16px; border-radius: 6px; }}
QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
QMenu::item:disabled {{ color: {dim}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QStatusBar {{ color: {dim}; }}
QCheckBox {{ spacing: 8px; }}
"""
