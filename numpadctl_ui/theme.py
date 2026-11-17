"""Material 3 look for the settings window: tokens (tokens.py) -> Qt palette and stylesheet."""

import subprocess
import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import QEvent, QFileSystemWatcher, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPalette, QPen, QPixmap

from numpadctl import config
from numpadctl.platform import paths
from . import custom_theme, motion, tokens

current = {}  # the colours in use, for widgets that paint themselves (the numpad keys)
look = dict(config.LOOK_DEFAULTS)   # Settings → Appearance in use (config.look_settings)
status = {"origin": "", "error": ""}   # where the colours came from / why the chosen ones couldn't be used
SHAPES = {   # corner radii (px) per shape setting; "full" is a button's radius (None: a full pill)
    "round": dict(tokens.SHAPE),
    "rounded": {"xs": 4, "s": 6, "m": 10, "l": 12, "xl": 16, "full": 12},
    "square": {"xs": 2, "s": 2, "m": 4, "l": 4, "xl": 6, "full": 4},
}
SHAPE_FACTOR = {"round": 1.0, "rounded": 0.6, "square": 0.25}   # for things with their own radii (the numpad keys)
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


def material():
    """True while the Material 3 design is on; self-painting widgets draw Qt's classic look when it's off."""
    return bool(look.get("material", True))


def painted():
    """The colours for a widget that paints its own Material look, or {} for Qt's classic drawing."""
    return current if material() else {}


def button_radius(height):
    """A button's corner radius for the shape setting: a full pill (round), or the shape's fixed radius."""
    if look.get("shape", "round") == "round":
        return height / 2
    return min(height / 2, SHAPES[look["shape"]]["full"])


def shape_factor():
    return SHAPE_FACTOR.get(look.get("shape", "round"), 1.0)


def resolve_colors(accent, dark, contrast="standard", settings=None):
    """The M3 roles from the colour source in `settings` (a look dict), falling back to the accent when that
    source can't give colours right now (its error is kept in `status` for Settings to show)."""
    settings = settings or look
    try:
        colors, origin = custom_theme.colors(settings, dark, contrast, accent)
        status.update(origin=origin, error="")
    except custom_theme.ThemeError as e:
        colors = tokens.colors(accent, dark, contrast)
        status.update(origin=f"{accent} accent", error=str(e))
    return colors


def style_colors(accent, dark, contrast="standard", base=None):
    """The tokens the stylesheet needs: M3 roles plus the state-layer mixes of the controls that have them."""
    c = dict(base) if base else tokens.colors(accent, dark, contrast)
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
    c["primaryHover"] = tokens.rgba(c["primary"], hover)
    c["primaryPressed"] = tokens.rgba(c["primary"], pressed)
    return c


def _draw_images(c):
    """Stylesheets need image files for arrows and checkmarks; draw them in the theme's colors."""
    folder = paths.state_dir() / "qt-theme"
    folder.mkdir(parents=True, exist_ok=True)
    images = {}
    load_fonts()
    from . import icons
    file = folder / f"arrow18-{c['onSurfaceVariant'].strip('#')}.png"   # the size is in the name: a new size, a new file
    if not file.exists():   # drop-downs use Material's own arrow_drop_down, like Google's menus
        icons.pixmap("arrow_drop_down", c["onSurfaceVariant"], 18, ratio=2.0).save(str(file))
    images["arrow"] = file.as_posix()
    for name, color, points in (("check", c["onPrimary"], [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)]),):
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
        if not file.exists():  # the colour is in the name
            pixmap.save(str(file))
        images[name] = file.as_posix()  # forward slashes, also on Windows
    return images


_fonts_loaded = []


def load_fonts():
    """Register the bundled Google Sans and JetBrains Mono files, so the look doesn't depend on what the OS has
    (on Windows the fallback was a pixelated bitmap font)."""
    if _fonts_loaded:  # apply() runs often (Disco...): the font files are read once
        return
    _fonts_loaded.append(True)
    for file in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(file))


def monospace():
    """The font for code and logs: bundled JetBrains Mono, else the system fixed font."""
    if "JetBrains Mono" in QFontDatabase.families():
        font = QFont("JetBrains Mono")
        font.setStyleHint(QFont.Monospace)
        return font
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


_base_point_size = []


def _font(app, family="", scale=100):
    """The UI font: your choice (Settings → Appearance) if it is installed, else the bundled Google Sans."""
    load_fonts()
    installed = set(QFontDatabase.families())
    if not _base_point_size:
        _base_point_size.append(app.font().pointSizeF() if app.font().pointSizeF() > 0 else 10.0)
    choices = ((family,) if family else ()) + FONT_FAMILIES
    chosen = next((f for f in choices if f in installed), None) or app.font().family()
    size = round(_base_point_size[0] * scale / 100, 1)
    if app.font().family() != chosen or abs(app.font().pointSizeF() - size) > 0.05:  # re-setting relayouts everything
        font = QFont(chosen)
        font.setPointSizeF(size)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)


def apply(app, appearance="auto", accent=tokens.DEFAULT_ACCENT, contrast="standard", settings=None):
    """Colour and style the whole app. `settings` is Settings → Appearance (config.look_settings; None keeps
    the defaults): the colour source, Material on/off, shape, font, motion, transparency."""
    look.clear()
    look.update(settings if settings is not None else config.LOOK_DEFAULTS)
    motion.configure(look["animations"], look["speed"])
    dark = is_dark(app, appearance)
    c = style_colors(accent, dark, contrast, base=resolve_colors(accent, dark, contrast))
    if not _styled:   # once: a styled app's style no longer reports "fusion", and re-setting it costs ~0.2 s
        app.setStyle("Fusion")
        _styled.append(True)
    _font(app, look["font"], look["font_scale"])
    _install_translucency(app)
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
    shape = {f"r_{name}": f"{px}px" for name, px in SHAPES[look["shape"]].items()}
    type_ = {}
    for name, (px, weight) in tokens.TYPE.items():
        type_[f"{name}_size"], type_[f"{name}_weight"] = f"{round(px * look['font_scale'] / 100)}px", weight
    opacity = look["opacity"] / 100
    see_through = {   # the window's background shows the desktop (blurred by the compositor) below 100 %
        "windowBg": tokens.rgba(c["surface"], opacity) if opacity < 1 else c["surface"],
        "cardBg": tokens.rgba(c["surfaceContainer"], min(1.0, opacity + 0.12)) if opacity < 1 else c["surfaceContainer"],
    }
    current.clear()
    current.update(c)
    sheet = Template(STYLE if material() else CLASSIC_STYLE).substitute(**c, **shape, **type_, **see_through,
                                                                       **_draw_images(c))
    if sheet != app.styleSheet():   # re-styling repolishes every widget (about a second): only when it changed
        app.setStyleSheet(sheet)
    for widget in app.allWidgets():  # the self-painted ones (keys, buttons) read `current` when they paint
        widget.update()
    for listener in list(listeners):
        listener(c)
    return c


class _Translucency(QObject):
    """Below 100 % opacity, windows are made see-through as they are created (Qt can only do it before a window
    exists on screen, so turning it on takes effect for windows opened afterwards; Settings says so)."""

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Polish and look.get("opacity", 100) < 100 and obj.isWidgetType()
                and obj.isWindow() and (obj.inherits("QMainWindow") or obj.inherits("QDialog"))
                and not obj.testAttribute(Qt.WA_WState_Created)):   # a window that isn't on screen yet
            obj.setAttribute(Qt.WA_TranslucentBackground)
        return False


_translucency = []
_styled = []


def _install_translucency(app):
    """The filter sees every event of the app, so it is only there while transparency is on."""
    want = look.get("opacity", 100) < 100
    if want and not _translucency:
        _translucency.append(_Translucency(app))
        app.installEventFilter(_translucency[0])
    elif not want and _translucency:
        app.removeEventFilter(_translucency.pop())


def watch_look(app, settings):
    """Re-colour the app when the theme file, the picture or pywal's colours change (a wallpaper script ran).

    settings() -> the whole config (unsaved changes too). Editors and pywal replace a file rather than write
    into it, which ends a file watch, so the folder is watched too and the file is added back each time."""
    watcher = QFileSystemWatcher(app)
    timer = QTimer(app, singleShot=True, interval=300)   # one re-colour for a burst of writes

    def rewatch():
        cfg = settings()
        files = custom_theme.watched_files(config.look_settings(cfg))
        old = watcher.files() + watcher.directories()
        if old:
            watcher.removePaths(old)
        for file in files:
            folder = str(Path(file).parent)
            if Path(folder).is_dir():
                watcher.addPath(folder)
            if Path(file).exists():
                watcher.addPath(file)

    def changed(*_):
        timer.start()

    def reapply():
        cfg = settings()
        apply(app, cfg.get("appearance", "auto"), cfg.get("accent", tokens.DEFAULT_ACCENT),
              cfg.get("contrast", "standard"), config.look_settings(cfg))
        rewatch()

    watcher.fileChanged.connect(changed)
    watcher.directoryChanged.connect(changed)
    timer.timeout.connect(reapply)
    rewatch()
    return rewatch


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
            apply(app, "auto", settings.get("accent", tokens.DEFAULT_ACCENT), settings.get("contrast", "standard"),
                  config.look_settings(settings))

    app.styleHints().colorSchemeChanged.connect(lambda _scheme: check())
    timer = None
    if sys.platform.startswith("linux") and app.styleHints().colorScheme() == Qt.ColorScheme.Unknown:
        timer = QTimer(app)
        timer.timeout.connect(check)
        timer.start(SYSTEM_POLL_MS)
    return check, timer


STYLE = """
* { font-size: ${bodyMedium_size}; }
QMainWindow, QDialog { background: ${windowBg}; color: ${onSurface}; }
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

QFrame#appbar { background: ${cardBg}; border-radius: ${r_xl}; }  /* M3 bars are flat: tone, not gradients */
QFrame#card { background: ${cardBg}; border: none; border-radius: ${r_xl}; }
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
QPushButton#numkey[compact="true"] { padding: 1px; min-width: 18px; min-height: 34px; }
QPushButton#numkey[compact="true"] QLabel#keyname { font-size: ${bodySmall_size}; font-weight: 500; }
QPushButton#numkey[bound="true"] QLabel#keyname { color: ${onSecondaryContainer}; }
QPushButton#numkey[bound="true"][selected="true"] QLabel#keyname { color: ${onPrimaryContainer}; }
QLabel#keyname { font-size: ${titleLarge_size}; font-weight: 600; color: ${onSurface}; }
QLabel#keyname[small="true"] { font-size: ${labelMedium_size}; font-weight: 600; }   /* above the action's icon */
QLabel#keyaction { font-size: ${bodySmall_size}; color: ${onSurfaceVariant}; }

QToolButton { color: ${primary}; padding: 8px 14px; font-size: ${labelLarge_size}; font-weight: ${labelLarge_weight}; }
QToolButton:checked { color: ${onSecondaryContainer}; }
QToolButton#icon { padding: 0; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; }
QPushButton#picker { text-align: left; padding: 0 16px; min-height: 56px; color: ${onSurface};
    font-size: ${bodyLarge_size}; font-weight: ${bodyLarge_weight}; }
QToolButton::menu-indicator { image: none; }

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget { background: transparent; color: ${onSurface};
    border: 1px solid ${outline}; border-radius: ${r_xs}; padding: 8px 14px;
    selection-background-color: ${primary}; selection-color: ${onPrimary}; }
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: ${onSurface}; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus {
    border: 2px solid ${primary}; padding: 7px 13px; }
QComboBox::drop-down { border: none; width: 32px; }
QComboBox::down-arrow { image: url("${arrow}"); width: 18px; height: 18px; }
QComboBox QAbstractItemView { background: ${surfaceContainerHigh}; color: ${onSurface}; border: none;
    border-radius: ${r_s}; padding: 6px; outline: none; }
QComboBox QAbstractItemView::item { padding: 10px 14px; border-radius: ${r_s}; min-height: 24px; }
QComboBox QAbstractItemView::item:hover { background: ${stateHover}; }
QComboBox QAbstractItemView::item:selected { background: ${secondaryContainer}; color: ${onSecondaryContainer}; }
QListWidget { padding: 4px; }
QListWidget::item { padding: 8px 12px; border-radius: ${r_s}; }
QListWidget::item:hover { background: ${stateHover}; }
QListWidget::item:selected { background: ${secondaryContainer}; color: ${onSecondaryContainer}; }
QListWidget::item:disabled { color: ${onSurfaceVariant}; font-style: italic; }   /* e.g. a template with a mistake */

QCheckBox { spacing: 12px; color: ${onSurface}; }
QCheckBox::indicator { width: 18px; height: 18px; border: none; background: transparent; image: none; }  /* numpadctl_ui/checkbox.py draws it */
QCheckBox[switch="true"] { spacing: 16px; min-height: 40px; padding-left: 4px; }  /* room for the 40 px halo */
QCheckBox[switch="true"]::indicator { width: 52px; height: 32px; }   /* checkbox.Switch draws the M3 switch */

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
QTabWidget::pane { border: none; border-top: 1px solid ${outlineVariant}; top: -1px; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: ${onSurfaceVariant}; border: none; border-bottom: 3px solid transparent;
    padding: 12px 20px 9px 20px; font-size: ${titleSmall_size}; font-weight: ${titleSmall_weight}; min-width: 96px; }
QTabBar::tab:hover { background: ${stateHover}; color: ${onSurface}; }
QTabBar::tab:selected { color: ${primary}; border-bottom: 3px solid ${primary}; }   /* M3 primary tabs */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QDialogButtonBox QPushButton { min-width: 72px; }
"""


# Material 3 off (Settings → Appearance): Qt's own Fusion drawing in the theme's colours (the palette does the
# colouring); only the type scale and the status chips are kept, so headings still read as headings.
CLASSIC_STYLE = """
QLabel#title, QLabel#appname { font-size: ${titleLarge_size}; font-weight: ${titleLarge_weight}; }
QLabel#heading { font-size: ${titleMedium_size}; font-weight: ${titleMedium_weight}; }
QLabel#dim, QLabel#small { color: ${onSurfaceVariant}; }
QLabel#small { font-size: ${bodySmall_size}; }
QLabel#keyname { font-size: ${titleMedium_size}; font-weight: 600; }
QLabel#keyaction { font-size: ${bodySmall_size}; }
QPushButton#numkey { min-width: 76px; min-height: 60px; }
QPushButton#numkey[compact="true"] { min-width: 18px; min-height: 34px; }
QLabel#ok { background: ${okContainer}; color: ${onOkContainer}; }
QLabel#warn { background: ${warnContainer}; color: ${onWarnContainer}; }
QLabel#bad { background: ${errorContainer}; color: ${onErrorContainer}; }
QMainWindow, QDialog { background: ${windowBg}; }
QFrame#banner { background: ${errorContainer}; }
QFrame#banner QLabel { color: ${onErrorContainer}; }
"""
