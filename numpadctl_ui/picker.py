"""The action picker: a button that opens a searchable, grouped list with a sentence for each action."""

import json

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QFrame, QLineEdit, QListWidget, QListWidgetItem, QStyle,
                               QStyledItemDelegate, QVBoxLayout)

from numpadctl import ui_common
from numpadctl.platform import paths
from .buttons import PushButton, reveal

RECENT_MAX = 5
RECENT_PATH = paths.config_dir() / "recent-actions.json"  # a UI convenience, not part of the settings
ID_ROLE, HEADER_ROLE = Qt.UserRole, Qt.UserRole + 1


def load_recent():
    try:
        ids = json.loads(RECENT_PATH.read_text())
        return [i for i in ids if isinstance(i, str)][:RECENT_MAX]
    except (OSError, ValueError):
        return []


def remember(action_id):
    if action_id == "none":
        return
    ids = [action_id] + [i for i in load_recent() if i != action_id]
    try:
        RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECENT_PATH.write_text(json.dumps(ids[:RECENT_MAX]))
    except OSError:
        pass


def haystack(action):
    return f"{action.label} {action.group} {ui_common.ACTION_HINTS.get(action.id, '')}".lower()


def matches(action, query):
    """Every word typed appears somewhere in the action's name, group or sentence."""
    text = haystack(action)
    return all(word in text for word in query.lower().split())


class _Rows(QStyledItemDelegate):
    """A group heading, or an action's name with its sentence under it."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 28 if index.data(HEADER_ROLE) else 52)

    def paint(self, painter, option, index):
        painter.save()
        palette = option.palette
        if index.data(HEADER_ROLE):
            font = QFont(option.font)
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
            font.setBold(True)
            font.setCapitalization(QFont.AllUppercase)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
            painter.setFont(font)
            painter.setPen(palette.color(palette.ColorRole.PlaceholderText))
            painter.drawText(option.rect.adjusted(14, 8, 0, 0), Qt.AlignLeft | Qt.AlignTop, index.data(Qt.DisplayRole))
            painter.restore()
            return
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        inner = option.rect.adjusted(4, 2, -4, -2)
        if selected or hovered:
            color = palette.color(palette.ColorRole.Highlight if selected else palette.ColorRole.AlternateBase)
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(inner, 12, 12)
        text = palette.color(palette.ColorRole.HighlightedText if selected else palette.ColorRole.Text)
        painter.setPen(text)
        painter.drawText(inner.adjusted(10, 6, -10, 0), Qt.AlignLeft | Qt.AlignTop, index.data(Qt.DisplayRole))
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1.5))
        painter.setFont(small)
        painter.setPen(text if selected else palette.color(palette.ColorRole.PlaceholderText))
        painter.drawText(inner.adjusted(10, 0, -10, -6), Qt.AlignLeft | Qt.AlignBottom,
                         painter.fontMetrics().elidedText(index.data(Qt.UserRole + 2) or "", Qt.ElideRight,
                                                          inner.width() - 20))
        painter.restore()


class _Popup(QFrame):
    chosen = Signal(int)

    def __init__(self, items, current):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("pickerPopup")
        self.items = items  # [Action]
        self.current = current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search actions: try “mute”, “obs”, “volume”")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search actions")
        self.search.textChanged.connect(self.fill)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setItemDelegate(_Rows(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.itemClicked.connect(self._clicked)
        layout.addWidget(self.list)
        self.fill("")

    def fill(self, query):
        self.list.clear()
        query = query.strip()
        shown = [(i, a) for i, a in enumerate(self.items) if not query or matches(a, query)]
        recent = {} if query else {a.id: i for i, a in enumerate(self.items)}
        recent_rows = [(recent[r], self.items[recent[r]]) for r in load_recent() if r in recent]
        sections = []
        if recent_rows:
            sections.append(("Recently used", recent_rows))
        groups = {}
        for i, a in shown:
            groups.setdefault(a.group, []).append((i, a))
        sections += list(groups.items())
        for title, rows in sections:
            header = QListWidgetItem(title)
            header.setData(HEADER_ROLE, True)
            header.setFlags(Qt.NoItemFlags)
            self.list.addItem(header)
            for i, a in rows:
                row = QListWidgetItem(a.label)
                row.setData(ID_ROLE, i)
                row.setData(Qt.UserRole + 2, ui_common.ACTION_HINTS.get(a.id, ""))
                self.list.addItem(row)
        self._select_first()

    def _rows(self):
        return [r for r in range(self.list.count()) if self.list.item(r).data(ID_ROLE) is not None]

    def _select_first(self):
        rows = self._rows()
        if rows:
            self.list.setCurrentRow(rows[0])
            if not self.search.text().strip():  # opened: start on the current choice
                for r in rows:
                    if self.list.item(r).data(ID_ROLE) == self.current:
                        self.list.setCurrentRow(r)
                        break

    def _step(self, delta):
        rows = self._rows()
        if not rows:
            return
        now = self.list.currentRow()
        later = [r for r in rows if (r > now if delta > 0 else r < now)]
        row = (later[0] if delta > 0 else later[-1]) if later else (rows[0] if delta > 0 else rows[-1])
        self.list.setCurrentRow(row)
        self.list.scrollToItem(self.list.item(row))

    def _clicked(self, item):
        if item.data(ID_ROLE) is not None:
            self.chosen.emit(item.data(ID_ROLE))
            self.close()

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._step(1 if key == Qt.Key_Down else -1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list.currentItem()
                if item is not None:
                    self._clicked(item)
                return True
        return super().eventFilter(obj, event)


class ActionPicker(PushButton):
    """Shows the chosen action; a click opens the searchable list. picked(index into `items`)."""
    picked = Signal(int)

    def __init__(self, items, current=0, names=None):
        super().__init__()
        self.setObjectName("picker")
        self.items = items
        self._names = names or [ui_common.action_name(a) for a in items]
        self._popup = None
        self.index = current
        self.setText(self._names[current] + "   ▾")
        self.setStyleSheet("text-align: left; padding: 8px 14px;")
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self.open)

    def open(self):
        self._popup = popup = _Popup(self.items, self.index)
        popup.chosen.connect(self.choose)
        width = max(self.width(), 400)
        below = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        height = min(460, max(220, screen.bottom() - below.y() - 12))
        popup.setGeometry(QRect(min(below.x(), screen.right() - width - 8), below.y(), width, height))
        popup.show()
        popup.search.setFocus()
        reveal(popup)

    def choose(self, index):
        """Pick action number `index` (what a click in the list does)."""
        if index == self.index:
            return
        self.index = index
        self.setText(self._names[index] + "   ▾")
        remember(self.items[index].id)
        self.picked.emit(index)
