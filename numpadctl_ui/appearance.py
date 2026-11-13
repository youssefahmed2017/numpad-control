"""Settings → Appearance: everything about how the window looks and moves.

Design (Material 3 on/off, shape), colours (light/dark, where the colours come from: a built-in accent, any
colour, a picture, pywal or a theme file; the scheme style and contrast), motion (on/off, speed, ripples) and
the window (transparency, font, text size). Every change is shown at once on the whole app (`changed` →
SettingsDialog → MainWindow.preview_look); like the rest of Settings it is kept with Save.
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QColorDialog, QFileDialog, QHBoxLayout, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from numpadctl import config, icon_packs
from . import custom_theme, icon_pack_ui, theme, tokens
from .buttons import ComboBox, PushButton, SpinBox
from .checkbox import Switch
from .widgets import card, label

APPEARANCES = [("auto", "Follow the system"), ("light", "Light"), ("dark", "Dark")]
SOURCES = [("accent", "Built-in accent"), ("color", "Any colour you pick"),
           ("image", "A picture (your wallpaper)"), ("pywal", "pywal (follows your wallpaper)"),
           ("file", "Theme file (Material Theme Builder, matugen)")]
SHAPES = [("round", "Round (Material 3 Expressive)"), ("rounded", "Rounded"), ("square", "Square")]
SPEEDS = [(0.5, "Slower"), (0.75, "Slow"), (1.0, "Normal"), (1.5, "Fast"), (2.0, "Faster")]
FONT_SCALES = [85, 90, 100, 110, 120, 130]
PICTURES = "Pictures (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


def swatch(color, size=16):
    picture = QPixmap(size, size)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(picture)


def _combo(items, current):
    box = ComboBox()
    box.addItems([text for _, text in items])
    keys = [key for key, _ in items]
    box.setCurrentIndex(keys.index(current) if current in keys else 0)
    return box


class AppearancePage(QWidget):
    changed = Signal()

    def __init__(self, cfg):
        super().__init__()
        self.look = config.look_settings(cfg)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # ------------------------------------------------ design
        frame, box = card()
        box.addWidget(label("Design", "heading"))
        self.material = Switch("Material 3 design")
        self.material.setChecked(self.look["material"])
        self.material.setToolTip("Off: Qt's classic look (plain buttons and checkboxes), still in your colours")
        box.addWidget(self.material)
        box.addWidget(label("Off gives Qt's classic look, still in your colours. The key map overlay always "
                            "stays Material.", "small", wrap=True))
        self.action_icons = Switch("Icons for actions on keys")
        self.action_icons.setChecked(self.look["action_icons"])
        self.action_icons.setToolTip("OBS + a red dot for start recording, a moon for sleep... A sticker you chose wins")
        box.addWidget(self.action_icons)
        box.addWidget(label("Icon pack", "small"))
        pack_row = QHBoxLayout()
        self.icon_pack = ComboBox()
        self.icon_pack.setToolTip("A style for every action's icon. Install a pack (a .zip), then pick it here")
        pack_row.addWidget(self.icon_pack, 1)
        self.install_pack_button = PushButton("Install pack…")
        self.install_pack_button.clicked.connect(lambda: self.install_pack())
        pack_row.addWidget(self.install_pack_button)
        self.remove_pack_button = PushButton("Remove")
        self.remove_pack_button.clicked.connect(lambda: self.remove_pack())
        pack_row.addWidget(self.remove_pack_button)
        box.addLayout(pack_row)
        self.pack_note = label("", "small", wrap=True)
        box.addWidget(self.pack_note)
        self._fill_packs(self.look["icon_pack"])
        box.addWidget(label("Shape", "small"))
        self.shape = _combo(SHAPES, self.look["shape"])
        box.addWidget(self.shape)
        layout.addWidget(frame)

        # ------------------------------------------------ colours
        frame, box = card()
        box.addWidget(label("Colours", "heading"))
        box.addWidget(label("Light or dark", "small"))
        self.appearance = _combo(APPEARANCES, cfg.get("appearance", "auto"))
        box.addWidget(self.appearance)
        box.addWidget(label("Where the colours come from", "small"))
        self.source = _combo(SOURCES, self.look["source"])
        box.addWidget(self.source)
        self.source_pages = QStackedWidget()   # one row per source, in SOURCES order
        self.accent = ComboBox()
        for name, seed in tokens.SEEDS.items():
            self.accent.addItem(swatch(seed), name)
        self.accent.setCurrentText(cfg.get("accent", tokens.DEFAULT_ACCENT))
        self.source_pages.addWidget(self.accent)
        self.seed_button = PushButton()
        self.seed_button.clicked.connect(self.pick_color)
        self.source_pages.addWidget(self._row(self.seed_button))
        self.image_label = label("", "dim")
        image_button = PushButton("Choose picture…")
        image_button.clicked.connect(self.pick_image)
        self.source_pages.addWidget(self._row(self.image_label, image_button))
        self.source_pages.addWidget(label(f"Reads {custom_theme.PYWAL}: run wal -i <picture> and the window "
                                          "follows along.", "dim", wrap=True))
        self.file_label = label("", "dim")
        file_button = PushButton("Choose file…")
        file_button.clicked.connect(self.pick_file)
        self.source_pages.addWidget(self._row(self.file_label, file_button))
        box.addWidget(self.source_pages)
        self.variant_label = label("Scheme style (how one colour becomes a whole theme)", "small")
        box.addWidget(self.variant_label)
        self.variant = _combo(list(custom_theme.VARIANTS.items()), self.look["variant"])
        box.addWidget(self.variant)
        box.addWidget(label("Contrast", "small"))
        self.contrast = ComboBox()
        self.contrast.addItems(["Standard", "Medium", "High"])
        self.contrast.setCurrentIndex(tokens.CONTRASTS.index(cfg.get("contrast", "standard")))
        box.addWidget(self.contrast)
        self.status = label("", "small", wrap=True)   # where the colours came from, or why they couldn't be used
        box.addWidget(self.status)
        export = PushButton("Export theme…")
        export.setObjectName("flat")
        export.setToolTip("Save these colours (light and dark) as a Material Theme Builder-style JSON file")
        export.clicked.connect(self.export)
        box.addWidget(export, 0, Qt.AlignLeft)
        layout.addWidget(frame)

        # ------------------------------------------------ motion
        frame, box = card()
        box.addWidget(label("Motion", "heading"))
        self.animations = Switch("Animations")
        self.animations.setChecked(self.look["animations"])
        box.addWidget(self.animations)
        box.addWidget(label("Speed", "small"))
        self.speed = ComboBox()
        self.speed.addItems([text for _, text in SPEEDS])
        speeds = [value for value, _ in SPEEDS]
        self.speed.setCurrentIndex(min(range(len(speeds)), key=lambda i: abs(speeds[i] - self.look["speed"])))
        box.addWidget(self.speed)
        self.ripples = Switch("Ripples when you press a button")
        self.ripples.setChecked(self.look["ripples"])
        box.addWidget(self.ripples)
        layout.addWidget(frame)

        # ------------------------------------------------ window
        frame, box = card()
        box.addWidget(label("Window", "heading"))
        row = QHBoxLayout()
        row.addWidget(label("Opacity", "small"))
        self.opacity = SpinBox()
        self.opacity.setRange(*config.LOOK_RANGES["opacity"])
        self.opacity.setSuffix(" %")
        self.opacity.setValue(self.look["opacity"])
        self.opacity.setAccessibleName("Window opacity")
        row.addWidget(self.opacity)
        row.addStretch()
        box.addLayout(row)
        box.addWidget(label("Below 100 % your desktop shows through (blurred, if your compositor blurs windows: "
                            "KDE, Hyprland). Turning it on applies to windows opened after you save; restart "
                            "NumpadControl for the main window. On X11 it needs a compositor.", "small", wrap=True))
        box.addWidget(label("Font", "small"))
        self.font = ComboBox()
        self.font_families = [""] + sorted(f for f in QFontDatabase.families() if not f.startswith("Material Symbols"))
        self.font.addItems(["Google Sans (built in)"] + self.font_families[1:])
        self.font.setCurrentIndex(self.font_families.index(self.look["font"]) if self.look["font"] in
                                  self.font_families else 0)
        box.addWidget(self.font)
        box.addWidget(label("Text size", "small"))
        self.font_scale = ComboBox()
        self.font_scale.addItems([f"{n} %" for n in FONT_SCALES])
        self.font_scale.setCurrentIndex(min(range(len(FONT_SCALES)),
                                            key=lambda i: abs(FONT_SCALES[i] - self.look["font_scale"])))
        box.addWidget(self.font_scale)
        layout.addWidget(frame)

        reset = PushButton("Reset appearance")
        reset.setObjectName("flat")
        reset.clicked.connect(self.reset)
        layout.addWidget(reset, 0, Qt.AlignLeft)

        self._refresh()
        for widget in (self.material, self.animations, self.ripples, self.action_icons):
            widget.toggled.connect(self._edited)
        for widget in (self.shape, self.appearance, self.source, self.accent, self.variant, self.contrast,
                       self.speed, self.font, self.font_scale):
            widget.currentIndexChanged.connect(self._edited)
        self.opacity.valueChanged.connect(self._edited)
        self.icon_pack.currentIndexChanged.connect(self._pack_chosen)

    @staticmethod
    def _row(*widgets):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        for i, widget in enumerate(widgets):
            row.addWidget(widget, 1 if i == 0 and len(widgets) > 1 else 0)
        return holder

    # ---------------------------------------------------------------- reading it back
    def values(self):
        """The top-level settings (as before) and the "look" dict (config.look_settings)."""
        look = dict(self.look)
        look.update(
            material=self.material.isChecked(), shape=SHAPES[self.shape.currentIndex()][0],
            source=SOURCES[self.source.currentIndex()][0], variant=list(custom_theme.VARIANTS)[self.variant.currentIndex()],
            animations=self.animations.isChecked(), speed=SPEEDS[self.speed.currentIndex()][0],
            ripples=self.ripples.isChecked(), opacity=self.opacity.value(), action_icons=self.action_icons.isChecked(),
            icon_pack=self.icon_pack.currentData() or "",
            font=self.font_families[self.font.currentIndex()], font_scale=FONT_SCALES[self.font_scale.currentIndex()])
        return {"appearance": APPEARANCES[self.appearance.currentIndex()][0], "accent": self.accent.currentText(),
                "contrast": tokens.CONTRASTS[self.contrast.currentIndex()], "look": config.look_settings({"look": look})}

    # ---------------------------------------------------------------- icon packs
    def _fill_packs(self, select=""):
        """List the built-in icons and the installed packs, with `select` (a pack's slug, "" = built-in) chosen."""
        self.icon_pack.blockSignals(True)
        self.icon_pack.clear()
        self.icon_pack.addItem("Built-in icons", "")
        for pack in icon_packs.installed():
            self.icon_pack.addItem(pack["name"], pack["slug"])
        self.icon_pack.setCurrentIndex(next((i for i in range(self.icon_pack.count()) if self.icon_pack.itemData(i) == select), 0))
        self.icon_pack.blockSignals(False)
        self._pack_info()

    def _pack_info(self):
        slug = self.icon_pack.currentData() or ""
        self.remove_pack_button.setEnabled(bool(slug))
        pack = next((p for p in icon_packs.installed() if p["slug"] == slug), None)
        if pack is None:
            self.pack_note.setText("")
            return
        parts = [f"{pack['count']} icons"] + ([f"by {pack['author']}"] if pack["author"] else []) \
            + ([f"license: {pack['license']}"] if pack["license"] else [])
        self.pack_note.setText(", ".join(parts) + ". Actions it has no picture for keep the built-in icon.")

    def _pack_chosen(self, *_):
        self._pack_info()
        self._edited()

    def install_pack(self, path=None, confirm=None):
        """Install an icon pack (a zip or folder) and switch to it. True when it was installed."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Choose an icon pack", "", "Icon packs (*.zip);;All files (*)")
            if not path:
                return False
        try:
            result = icon_pack_ui.install(path, confirm or self._confirm_pack)
        except icon_packs.PackError as e:
            QMessageBox.warning(self, "Icon pack", f"This pack can't be used: {e}.")
            return False
        if result is None:
            return False
        self._fill_packs(result.slug)
        if not self.action_icons.isChecked():
            self.action_icons.blockSignals(True)
            self.action_icons.setChecked(True)      # installing one means wanting to see it
            self.action_icons.blockSignals(False)
        self._edited()
        if result.failed:
            QMessageBox.information(self, "Icon pack", f"{len(result.failed)} picture(s) couldn't be used and keep the built-in "
                                    "icon:\n\n" + "\n".join(result.failed[:6]))
        return True

    def _confirm_pack(self, pack, missing):
        box = QMessageBox(self)
        box.setWindowTitle("Install icon pack")
        box.setText(f"Install {('“' + pack.name + '”') if pack.name else 'this icon pack'} and use it?")
        lines = [f"{len(pack.files)} actions get a new icon."]
        if missing:
            lines.append(f"{len(missing)} actions have no picture in it and keep the built-in icon.")
        if pack.author:
            lines.append(f"By {pack.author}.")
        if pack.license:
            lines.append(f"License: {pack.license}.")
        lines.append("The pictures stay on this computer. You can go back to the built-in icons any time.")
        box.setInformativeText("\n".join(lines))
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Install")
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Ok

    def remove_pack(self, confirm=None):
        """Delete the pack chosen in the list (and go back to the built-in icons). True when it was removed."""
        slug = self.icon_pack.currentData() or ""
        if not slug:
            return False
        name = self.icon_pack.currentText()
        if confirm is None:
            answer = QMessageBox.question(self, "Remove icon pack", f"Remove the icon pack “{name}” from this computer?")
            confirm = lambda: answer == QMessageBox.Yes  # noqa: E731
        if not confirm() or not icon_packs.remove(slug):
            return False
        self._fill_packs("")
        self._edited()
        return True

    # ---------------------------------------------------------------- reacting
    def _edited(self, *_):
        self.look = self.values()["look"]
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        """Show the row of the chosen source, and say where the colours come from (after the app re-coloured)."""
        source = self.look["source"]
        self.source_pages.setCurrentIndex([key for key, _ in SOURCES].index(source))
        self.seed_button.setText(f"  {self.look['seed']}  ·  Change colour…")
        self.seed_button.setIcon(swatch(self.look["seed"], 18))
        self.image_label.setText(Path(self.look["image"]).name if self.look["image"] else "No picture chosen")
        self.file_label.setText(Path(self.look["file"]).name if self.look["file"] else "No file chosen")
        generated = source in ("color", "image", "pywal", "file")
        self.variant.setEnabled(generated)
        self.variant_label.setEnabled(generated)
        self.animations_dependent()

    def animations_dependent(self):
        self.speed.setEnabled(self.animations.isChecked())

    def show_status(self):
        """Called after the app took the new look: where its colours came from, or what went wrong."""
        if theme.status["error"]:
            self.status.setObjectName("bad")
            self.status.setText(f"{theme.status['error']}. Showing the {theme.status['origin']} for now.")
        else:
            self.status.setObjectName("small")
            self.status.setText(f"Colours from {theme.status['origin']}.")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if not custom_theme.available():
            for index in (1, 2, 3):   # the sources that need Google's colour maths
                item = self.source.model().item(index)
                if item is not None:
                    item.setEnabled(False)

    def _set(self, **changes):
        self.look.update(changes)
        self._refresh()
        self.changed.emit()

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.look["seed"]), self, "Your colour")
        if color.isValid():
            self._set(seed=color.name())

    def pick_image(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, "A picture for the colours",
                                                   str(Path(self.look["image"] or Path.home()).parent
                                                       if self.look["image"] else Path.home() / "Pictures"),
                                                   PICTURES)[0]
        if path:
            self._set(image=path)

    def pick_file(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, "A Material theme (JSON)", str(Path.home()),
                                                   "Theme files (*.json)")[0]
        if path:
            self._set(file=path)

    def export(self, path=None):
        values = self.values()
        path = path or QFileDialog.getSaveFileName(self, "Export theme", str(Path.home() / "numpadcontrol-theme.json"),
                                                   "Theme files (*.json)")[0]
        if not path:
            return
        try:
            data = custom_theme.export(values["look"], values["contrast"], values["accent"])
            Path(path).write_text(json.dumps(data, indent=2) + "\n")
            self.status.setText(f"Saved {Path(path).name}: load it again under Theme file, or share it.")
        except (OSError, custom_theme.ThemeError) as e:
            self.status.setText(f"Couldn't export: {e}")

    def reset(self):
        self.look = dict(config.LOOK_DEFAULTS)
        widgets = (self.material, self.shape, self.source, self.variant, self.animations, self.speed, self.ripples,
                   self.opacity, self.font, self.font_scale, self.action_icons)
        for widget in widgets:
            widget.blockSignals(True)
        self.material.setChecked(True)
        self.action_icons.setChecked(True)
        self._fill_packs("")
        self.shape.setCurrentIndex(0)
        self.source.setCurrentIndex(0)
        self.variant.setCurrentIndex(0)
        self.animations.setChecked(True)
        self.speed.setCurrentIndex([v for v, _ in SPEEDS].index(1.0))
        self.ripples.setChecked(True)
        self.opacity.setValue(100)
        self.font.setCurrentIndex(0)
        self.font_scale.setCurrentIndex(FONT_SCALES.index(100))
        for widget in widgets:
            widget.blockSignals(False)
        self._edited()
