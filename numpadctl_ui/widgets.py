"""The editor's building blocks. Every field writes straight into the binding it
edits (no separate "collect the fields before saving" step)."""

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget)

from numpadctl import actions, sandbox, ui_common
from . import theme
from .buttons import ComboBox, Menu, PushButton, ToolButton
from .picker import ActionPicker


class Dispatcher(QObject):
    """Run a function on the UI thread, from any thread: dispatch(fn, *args)."""
    _call = Signal(object)

    def __init__(self):
        super().__init__()
        self._call.connect(lambda fn: fn())

    def __call__(self, fn, *args):
        self._call.emit(lambda: fn(*args))


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    return frame, layout


class SearchCombo(ComboBox):
    """A dropdown you can type into; typing filters by any part of the name."""
    picked = Signal(int)

    def __init__(self, names, current=0):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(20)
        self.addItems(names)
        self.setCurrentIndex(current)
        self._last = current
        completer = self.completer()
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.currentIndexChanged.connect(self._changed)
        self.lineEdit().editingFinished.connect(self._restore)

    def _changed(self, index):
        if index >= 0 and index != self._last:
            self._last = index
            self.picked.emit(index)

    def _restore(self):
        """Typed text that isn't a choice: show the current choice again."""
        if self.currentText() != self.itemText(self._last):
            self.blockSignals(True)
            self.setCurrentIndex(self._last)
            self.blockSignals(False)


class TextField(QWidget):
    """A labelled text field, optionally with a list button and a placeholder button."""

    def __init__(self, param, value, on_change, window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(label(param.label, "small"))
        row = QHBoxLayout()
        self.edit = QLineEdit(str(value))
        self.edit.setAccessibleName(param.label)
        self.edit.textChanged.connect(on_change)
        row.addWidget(self.edit)
        if param.suggest:
            row.addWidget(self._picker(param.suggest, window))
        if param.placeholders:
            row.addWidget(self._placeholders())
        layout.addLayout(row)
        self.get_params = lambda: {}  # set by the editor: the other fields' values

    def _picker(self, suggest, window):
        button = ToolButton(text="☰", toolTip="Pick from a list")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = Menu(button)
        button.setMenu(menu)

        def fill(names, error):
            menu.clear()
            if error:
                menu.addAction(str(error)).setEnabled(False)
            elif not names:
                menu.addAction("Nothing to pick from right now").setEnabled(False)
            for name in names or []:
                menu.addAction(name, lambda n=name: self.edit.setText(n))

        def load():
            menu.clear()
            menu.addAction("Loading…").setEnabled(False)
            params = self.get_params()
            ui_common.run_in_background(lambda: actions.SUGGESTIONS[suggest](window.cfg, params),
                                        fill, window.dispatch)
        menu.aboutToShow.connect(load)
        return button

    def _placeholders(self):
        button = ToolButton(text="{…}", toolTip="Insert a placeholder")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = Menu(button)
        for token, description in actions.PLACEHOLDERS.items():
            menu.addAction(f"{token}    {description}", lambda t=token: self.edit.insert(t))
        button.setMenu(menu)
        return button


class AppField(QWidget):
    """Pick an installed app (Linux: .desktop id; Windows: Start-menu shortcut)."""

    def __init__(self, param, value, on_change):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(label(param.label, "small"))
        apps = ui_common.installed_apps()
        ids = [app_id for _, app_id in apps]
        current = ids.index(value) if value in ids else 0
        combo = SearchCombo([name for name, _ in apps], current)
        combo.picked.connect(lambda i: on_change(ids[i]))
        layout.addWidget(combo)
        if apps and value not in ids:
            on_change(ids[0])  # the first app is what the dropdown shows


class CodeField(QWidget):
    """Python code (Run Python), with the sandbox rules and a check button."""

    def __init__(self, param, value, on_change, window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(param.label, "small"))
        edit = QPlainTextEdit(str(value))
        edit.setFont(theme.monospace())
        edit.setMinimumHeight(180)
        edit.textChanged.connect(lambda: on_change(edit.toPlainText()))
        layout.addWidget(edit)
        layout.addWidget(label(ui_common.PYTHON_HELP, "small", wrap=True))
        check = PushButton("Check code")
        check.clicked.connect(lambda: window.show_problems(sandbox.validate(edit.toPlainText()), "Code looks OK"))
        layout.addWidget(check, alignment=Qt.AlignLeft)


class BoolField(QCheckBox):
    """A checkbox setting."""

    def __init__(self, param, value, on_change):
        super().__init__(param.label)
        self.setChecked(actions._truthy(value))
        self.toggled.connect(on_change)


def param_widget(param, params, window, on_change):
    """The widget for one setting of an action; edits params[param.name] in place."""
    value = params.get(param.name, param.default)

    def changed(new):
        params[param.name] = new
        on_change()
    if param.kind == "bool":
        return BoolField(param, value, changed)
    if param.kind == "app":
        return AppField(param, value, changed)
    if param.kind == "code":
        return CodeField(param, value, changed, window)
    if param.kind == "macro":
        return StepList(params.setdefault(param.name, []), window, on_change)
    return TextField(param, value, changed, window)


def add_param_widgets(layout, action, params, window, on_change):
    """All of an action's settings; text fields' list buttons see the other values."""
    fields = []
    for param in action.params:
        widget = param_widget(param, params, window, on_change)
        if param.kind == "macro" and sum(p.kind == "macro" for p in action.params) > 1:
            layout.addWidget(label(param.label, "heading"))  # if / otherwise: name each list
        layout.addWidget(widget)
        fields.append(widget)
    for widget in fields:
        if isinstance(widget, TextField):
            widget.get_params = lambda: dict(params)
    return fields


class StepCard(QFrame):
    """One step of a macro (or of an if/otherwise list), expandable."""

    def __init__(self, steps, index, owner):
        super().__init__()
        self.setObjectName("card")
        self.steps, self.index, self.owner = steps, index, owner
        step = steps[index]
        action = actions.BY_ID.get(step.get("action"), actions.WAIT)
        if action.id not in actions.STEP_IDS:
            action = actions.WAIT
        self.action = action
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        header = QHBoxLayout()
        self.toggle = ToolButton(text="▾" if owner.expanded == index else "▸")
        self.toggle.clicked.connect(lambda: owner.expand(None if owner.expanded == index else index))
        header.addWidget(self.toggle)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label(f"{index + 1}.  {ui_common.action_name(action)}"))
        self.summary = label(ui_common.step_summary(step, action), "small")
        titles.addWidget(self.summary)
        header.addLayout(titles, 1)
        remove = PushButton("Remove")
        remove.setObjectName("flat")
        remove.clicked.connect(lambda: owner.change(lambda: steps.pop(index), None))
        header.addWidget(remove)
        layout.addLayout(header)

        if owner.expanded == index:
            body = QVBoxLayout()
            body.setContentsMargins(26, 4, 0, 4)
            combo = ActionPicker(actions.STEP_ACTIONS, actions.STEP_ACTIONS.index(action), ui_common.STEP_NAMES)
            combo.picked.connect(self._action_changed)
            body.addWidget(label("Action", "small"))
            body.addWidget(combo)
            add_param_widgets(body, action, step.setdefault("params", {}), owner.window, self._param_changed)
            if len(steps) > 1:
                order = QHBoxLayout()
                order.addWidget(label("Order", "dim"))
                order.addStretch()
                for text, delta, enabled in (("Move up", -1, index > 0), ("Move down", 1, index < len(steps) - 1)):
                    button = PushButton(text)
                    button.setEnabled(enabled)
                    button.clicked.connect(lambda _=False, d=delta: owner.move(index, d))
                    order.addWidget(button)
                body.addLayout(order)
            layout.addLayout(body)

    def _param_changed(self):
        self.summary.setText(ui_common.step_summary(self.steps[self.index], self.action))
        self.owner.on_change()

    def _action_changed(self, i):
        new = ui_common.new_binding(actions.STEP_ACTIONS[i])
        self.owner.change(lambda: self.steps.__setitem__(self.index, new), self.index)


class StepList(QWidget):
    """Edits a list of steps in place: add, remove, reorder, expand one at a time."""

    def __init__(self, steps, window, on_change):
        super().__init__()
        self.steps, self.window, self.on_change = steps, window, on_change
        self.expanded = None
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.rebuild()

    def rebuild(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())
        if not self.steps:
            self.layout_.addWidget(label("No steps yet. Add actions and waits; they run top to bottom.", "dim", wrap=True))
        for i in range(len(self.steps)):
            self.layout_.addWidget(StepCard(self.steps, i, self))
        buttons = QHBoxLayout()
        add = PushButton("＋ Add action")
        add.clicked.connect(lambda: self.add("open_browser"))
        wait = PushButton("⏱ Add wait")
        wait.clicked.connect(lambda: self.add("wait"))
        buttons.addWidget(add)
        buttons.addWidget(wait)
        buttons.addStretch()
        self.layout_.addLayout(buttons)

    def expand(self, index):
        self.expanded = index
        self.rebuild()

    def change(self, mutate, expand):
        mutate()
        self.expanded = expand
        self.on_change()
        self.rebuild()

    def add(self, action_id):
        new = ui_common.new_binding(actions.BY_ID[action_id])
        self.change(lambda: self.steps.append(new), len(self.steps))

    def move(self, index, delta):
        def swap():
            self.steps[index], self.steps[index + delta] = self.steps[index + delta], self.steps[index]
        self.change(swap, index + delta)


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())
