"""Write and test your own Python templates inside the app (no terminal, no outside editor).

Profile ⋯ → Add a starter preset… → New template… / Edit…: the code on the left (Python colours, 4-space tabs),
every action on the right (search, double-click to insert a ready line such as pad.tap("1", "volume_up")), and
**Try it**, which runs the template exactly as applying would (its own limited process, the same checks;
numpadctl/templates.py) but only reports what it would add. Save writes it to the templates folder.
"""

import ast
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget)

from numpadctl import actions, templates
from . import theme
from .buttons import PushButton
from .widgets import label

ID_ROLE = Qt.UserRole + 1


class PythonColours(QSyntaxHighlighter):
    """Keywords, strings, comments, numbers and pad.* calls in the theme's colours (no extra library)."""

    RULES = [(r"\b(def|return|for|in|if|elif|else|and|or|not|while|import|from|as|True|False|None|with|range|"
              r"lambda|break|continue|pass)\b", "primary"),
             (r"\bpad(\.layer)?\.\w+|\bstep\b", "tertiary"),
             (r"\b\d+(\.\d+)?\b", "secondary"),
             (r"(\"[^\"\n]*\"|'[^'\n]*')", "ok"),
             (r"#[^\n]*", "outline")]

    def __init__(self, document):
        super().__init__(document)
        self.rules = [(re.compile(pattern), role) for pattern, role in self.RULES]

    def highlightBlock(self, text):
        colours = theme.current or {}
        for pattern, role in self.rules:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colours.get(role, "#888888")))
            if role == "outline":
                fmt.setFontItalic(True)
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


def line_for(action):
    """A ready-to-edit line for an action, with its settings and their defaults."""
    settings = "".join(f", {p.name}={p.default!r}" for p in action.params
                       if p.kind not in ("macro",) and p.name not in ("then", "otherwise", "steps"))
    if action.id == "macro":
        return 'pad.macro("1", [step("press_keys", keys="ctrl+c"), step("press_keys", keys="ctrl+v")])'
    if action.id == "if_mode":
        return 'pad.if_mode("1", "Stream mode", [step("mic_mute")], [step("media_play_pause")])'
    return f'pad.tap("1", "{action.id}"{settings})'


class TemplateEditor(QDialog):
    def __init__(self, parent, window, path=None):
        super().__init__(parent)
        self.window, self.path = window, Path(path) if path else None
        self.setWindowTitle("Edit template" if path else "New template")
        self.resize(1040, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Edit template" if path else "New template", "title"))
        layout.addWidget(label("build(pad) fills keys: pad.tap / pad.hold / pad.double(key, action, setting=value), the "
                               "same on pad.layer for the layer keys. Double-click an action on the right to insert "
                               "it. Like a preset, a template only fills keys that have nothing yet.", "dim", wrap=True))
        split = QSplitter(Qt.Horizontal)
        self.code = QPlainTextEdit()
        mono = theme.monospace()
        mono.setPointSizeF(max(10.0, QFont().pointSizeF()))
        self.code.setFont(mono)
        self.code.setTabStopDistance(QFontMetricsF(mono).horizontalAdvance(" ") * 4)
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code.setAccessibleName("Template code")
        self.colours = PythonColours(self.code.document())
        text = self.path.read_text(encoding="utf-8") if self.path else templates.EXAMPLE.replace("{name}", "My template")
        self.code.setPlainText(text)
        split.addWidget(self.code)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(8, 0, 0, 0)
        side_layout.addWidget(label("Actions", "heading"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: volume, obs, screenshot…")
        self.search.textChanged.connect(self.filter)
        side_layout.addWidget(self.search)
        self.list = QListWidget()
        for action in actions.ACTIONS:
            if action.id == "none":
                continue
            item = QListWidgetItem(f"{action.label}\n{action.id}")
            item.setData(ID_ROLE, action.id)
            item.setToolTip(line_for(action))
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(self.insert)
        self.list.currentItemChanged.connect(lambda item, _: self.hint.setText(
            line_for(actions.BY_ID[item.data(ID_ROLE)]) if item else ""))
        side_layout.addWidget(self.list, 1)
        self.hint = label("", "small", wrap=True)
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        side_layout.addWidget(self.hint)
        insert = PushButton("Insert")
        insert.clicked.connect(lambda: self.insert(self.list.currentItem()))
        side_layout.addWidget(insert, 0, Qt.AlignLeft)
        split.addWidget(side)
        split.setSizes([680, 340])
        layout.addWidget(split, 1)

        self.result = label("", "small", wrap=True)   # what "Try it" found
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.result)
        buttons = QDialogButtonBox()
        try_it = PushButton("Try it")
        try_it.setToolTip("Run it now and see what it would add to this profile (nothing changes)")
        try_it.clicked.connect(self.try_it)
        buttons.addButton(try_it, QDialogButtonBox.ActionRole)
        save = PushButton("Save")
        save.setObjectName("primary")
        buttons.addButton(save, QDialogButtonBox.AcceptRole)
        buttons.addButton(PushButton("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- actions list
    def filter(self, text):
        words = text.lower().split()
        for row in range(self.list.count()):
            item = self.list.item(row)
            self.list.setRowHidden(row, not all(w in item.text().lower() for w in words))

    def insert(self, item):
        """Put the action's line under the cursor's line, indented like it (one level deeper after a ':')."""
        if item is None:
            return
        cursor = self.code.textCursor()
        block = cursor.block().text()
        indent = re.match(r"\s*", block).group(0)
        if block.rstrip().endswith(":"):
            indent += "    "
        elif not indent:
            indent = "    "   # top level: the line belongs inside build(pad)
        line = indent + line_for(actions.BY_ID[item.data(ID_ROLE)])
        if block.strip():
            cursor.movePosition(cursor.MoveOperation.EndOfBlock)
            cursor.insertText("\n" + line)
        else:   # an empty line: fill it
            cursor.movePosition(cursor.MoveOperation.StartOfBlock)
            cursor.movePosition(cursor.MoveOperation.EndOfBlock, cursor.MoveMode.KeepAnchor)
            cursor.insertText(line)
        self.code.setTextCursor(cursor)
        self.code.setFocus()

    # ---------------------------------------------------------------- checking and saving
    def _problem(self):
        """A sentence when the code can't even be read (checked before running or saving)."""
        try:
            tree = ast.parse(self.code.toPlainText())
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}"
        if not any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body):
            return "It needs a build(pad) function."
        return ""

    def _write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.code.toPlainText().rstrip() + "\n", encoding="utf-8")

    def try_it(self):
        problem = self._problem()
        if problem:
            self.result.setText(f"✗ {problem}")
            return
        scratch = templates.folder() / ".try-it.py"   # a dot file: never listed as a template
        try:
            self._write(scratch)
            result = templates.run(scratch, self.window.cfg, self.window.profile)
        except (OSError, templates.TemplateError) as e:
            self.result.setText(f"✗ {str(e).replace('.try-it.py: ', '').replace('.try-it.py', 'it')}")
            return
        finally:
            scratch.unlink(missing_ok=True)
        lines = []
        for layer, title in (("bindings", "Keys"), ("layer_bindings", "Layer keys")):
            found = getattr(result, layer)
            if found:
                parts = [f"{k}: {actions.BY_ID[b['action']].label}" + (f" ({s})" if s != "tap" else "")
                         for k, slots in sorted(found.items()) for s, b in slots.items()]
                lines.append(f"{title}: " + ", ".join(parts))
        if result.dropped:
            lines.append("Left out: " + "; ".join(result.dropped[:6]))
        lines += result.notes
        self.result.setText("✓ " + ("\n".join(lines) if lines else "It runs, but adds nothing."))

    def _target(self):
        """Where Save writes: the file being edited, else a free file name made from NAME."""
        if self.path:
            return self.path
        name = templates.describe_text(self.code.toPlainText())
        return templates.free_path(name)

    def save(self):
        problem = self._problem()
        if problem and QMessageBox.question(self, "Save template", f"{problem}\nSave it anyway (to finish later)?") \
                != QMessageBox.Yes:
            return
        try:
            self.path = self._target()
            self._write(self.path)
        except OSError as e:
            QMessageBox.warning(self, "Save template", f"Couldn't save it: {e}")
            return
        self.accept()
