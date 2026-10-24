"""Settings window (GTK4 + libadwaita): pick what each numpad key does."""

import copy
import json
import os
import socket
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import actions, config, obs, sandbox  # noqa: E402

APP_ID = "dev.numpadctl.NumpadControl"
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCKET_PATH = os.path.join(RUNTIME_DIR, "numpad-control.sock")
# Lets other tools (e.g. a "hidden apps" bar module) see that the window app is running.
PID_PATH = os.path.join(RUNTIME_DIR, "numpad-control-window.pid")

LAYOUT = [  # (key, row, column, rowspan)
    ("NumLock", 0, 0, 1), ("/", 0, 1, 1), ("*", 0, 2, 1), ("Backspace", 0, 3, 1),
    ("7", 1, 0, 1), ("8", 1, 1, 1), ("9", 1, 2, 1), ("-", 1, 3, 1),
    ("4", 2, 0, 1), ("5", 2, 1, 1), ("6", 2, 2, 1), ("+", 2, 3, 1),
    ("1", 3, 0, 1), ("2", 3, 1, 1), ("3", 3, 2, 1), ("Enter", 3, 3, 2),
    ("0", 4, 0, 1), ("000", 4, 1, 1), (".", 4, 2, 1),
]
KEY_LABELS = {"NumLock": "Num", "Backspace": "⌫", "Enter": "⏎"}
LAYER_KEY_CHOICES = [k for k, *_ in LAYOUT if k not in config.TAP_ONLY_KEYS]

SLOT_TITLES = {"tap": "Press", "hold": "Hold", "double": "Double tap"}

def action_name(a):
    return f"{a.group} · {a.label}" if a.group not in ("General", "Macro") else a.label


ACTION_NAMES = [action_name(a) for a in actions.ACTIONS]
STEP_NAMES = [action_name(a) for a in actions.STEP_ACTIONS]

PYTHON_HELP = (
    "Allowed imports: " + ", ".join(sorted(sandbox.ALLOWED_MODULES)) + ".\n"
    "Helpers: open_url(url), notify(title, body). print() output goes to the log.\n"
    "Banned: eval, exec, open, os, sys, subprocess, any other import, names starting with _."
)

CSS = """
.numkey { min-width: 84px; min-height: 64px; border-radius: 14px; padding: 6px; }
.numkey .keyname { font-size: 20px; font-weight: 800; }
.numkey .keyaction { font-size: 11px; }
.numkey.flash { box-shadow: inset 0 0 0 3px var(--accent-color);
                background-color: color-mix(in srgb, var(--accent-bg-color) 30%, transparent); }
.code { font-family: monospace; padding: 10px; }
"""

NONE_BINDING = {"action": "none", "params": {}}


def in_background(work, done):
    """Run work() in a thread, then done(result, error) on the GTK thread."""
    def runner():
        try:
            result, error = work(), None
        except Exception as e:
            result, error = None, e
        GLib.idle_add(done, result, error)
    threading.Thread(target=runner, daemon=True).start()


def open_windows():
    """[(class, title)] of open Hyprland windows, for picking a profile's app."""
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                             text=True, timeout=2).stdout
        seen, result = set(), []
        for c in json.loads(out):
            if c.get("class") and c["class"] not in seen:
                seen.add(c["class"])
                result.append((c["class"], c.get("title", "")))
        return result
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


class ServiceLink:
    """Talks to the background service over its Unix socket (reconnects forever)."""

    def __init__(self, on_message):
        self.on_message = on_message
        self.sock = None
        self.lock = threading.Lock()
        threading.Thread(target=self.loop, daemon=True).start()

    @property
    def connected(self):
        return self.sock is not None

    def loop(self):
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(SOCKET_PATH)
            except OSError:
                GLib.idle_add(self.on_message, {"event": "status", "running": False})
                time.sleep(2)
                continue
            self.sock = sock
            try:
                for line in sock.makefile("r"):
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    message.setdefault("running", True)
                    GLib.idle_add(self.on_message, message)
            except OSError:
                pass
            self.sock = None
            sock.close()

    def send(self, message):
        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall((json.dumps(message) + "\n").encode())
                except OSError:
                    pass


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=1080, default_height=720)
        self.cfg = config.load()
        self.profile_index = 0
        self.layer = False
        self.selected = None
        self.param_widgets = {}  # slot -> {param name: widget}
        self.key_buttons = {}
        self.dirty = False
        self.on_detected = None
        self.expanded_step = None  # macro step to show opened after a rebuild

        self.title_widget = Adw.WindowTitle(title="Numpad Control")
        header = Adw.HeaderBar(title_widget=self.title_widget)
        save = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save.connect("clicked", lambda *_: self.save())
        header.pack_end(save)
        settings = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Settings")
        settings.connect("clicked", lambda *_: SettingsDialog(self).present(self))
        header.pack_end(settings)
        self.learn = Gtk.ToggleButton(icon_name="input-keyboard-symbolic",
                                      tooltip_text="Learn mode: press a numpad key to select it "
                                                   "here (its action won't run)")
        self.learn.connect("toggled", self.on_learn_toggled)
        header.pack_start(self.learn)

        self.banner = Adw.Banner(title="The background service isn't running, so the numpad does nothing.",
                                 button_label="Start service")
        self.banner.connect("button-clicked", self.start_service)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.append(self._build_left())
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.editor = Adw.Bin(hexpand=True)
        body.append(self.editor)

        self.toasts = Adw.ToastOverlay(child=body)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        self.set_content(view)

        self._install_profile_actions()
        self.set_hide_on_close(True)  # the app keeps running in the background
        self.connect("close-request", self.on_close_request)
        self.connect("notify::visible", self.on_visibility_changed)
        self.refresh_layer_switch()
        self.select("1")
        self.link = ServiceLink(self.on_service_message)

    # ---------------------------------------------------------------- left column
    def _build_left(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)

        profile_row = Gtk.Box(spacing=6)
        profile_row.append(Gtk.Label(label="Profile", css_classes=["heading"]))
        self.profile_dropdown = Gtk.DropDown(hexpand=True)
        self.refresh_profiles()
        self.profile_dropdown.connect("notify::selected", self.on_profile_changed)
        profile_row.append(self.profile_dropdown)
        menu = Gio.Menu()
        menu.append("New profile…", "win.new-profile")
        menu.append("Edit profile…", "win.edit-profile")
        menu.append("Delete profile", "win.delete-profile")
        profile_row.append(Gtk.MenuButton(icon_name="document-edit-symbolic", menu_model=menu,
                                          tooltip_text="Profiles: different keys per app"))
        box.append(profile_row)

        self.layer_switch = Adw.ToggleGroup(css_classes=["round"])
        self.layer_switch.add(Adw.Toggle(label="Normal", name="normal"))
        self.layer_switch.add(Adw.Toggle(label="Layer (key held)", name="layer"))
        self.layer_switch.set_active_name("normal")
        self.layer_switch.connect("notify::active-name", self.on_layer_changed)
        box.append(self.layer_switch)

        grid = Gtk.Grid(row_spacing=8, column_spacing=8, row_homogeneous=True,
                        column_homogeneous=True, margin_top=4)
        for key, row, col, span in LAYOUT:
            name = Gtk.Label(label=KEY_LABELS.get(key, key), css_classes=["keyname"])
            action = Gtk.Label(css_classes=["keyaction", "dim-label"], ellipsize=3,
                               max_width_chars=11)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                            valign=Gtk.Align.CENTER)
            inner.append(name)
            inner.append(action)
            button = Gtk.Button(child=inner, css_classes=["numkey"], tooltip_text=key)
            button.connect("clicked", lambda _b, k=key: self.select(k))
            grid.attach(button, col, row, 1, span)
            self.key_buttons[key] = (button, action)
        box.append(grid)

        self.status = Gtk.Label(xalign=0, margin_top=6, label="●  Connecting to the service…",
                                css_classes=["dim-label"])
        box.append(self.status)
        box.append(Gtk.Label(xalign=0, wrap=True, max_width_chars=44, css_classes=["dim-label", "caption"],
                             label="Click a key to choose what it does, or turn on learn mode "
                                   "(keyboard icon) and press it on the numpad."))
        return box

    # ---------------------------------------------------------------- model helpers
    @property
    def profile(self):
        return self.cfg["profiles"][self.profile_index]

    def keymap(self):
        return self.profile["layer_bindings" if self.layer else "bindings"]

    def slot_binding(self, key, slot):
        return self.keymap().get(key, {}).get(slot) or NONE_BINDING

    def slots_for(self, key):
        return ("tap",) if key in config.TAP_ONLY_KEYS else config.SLOTS

    # ---------------------------------------------------------------- pad
    def refresh_pad(self):
        layer_key = self.cfg.get("layer_key")
        for key, (button, label) in self.key_buttons.items():
            if key == layer_key:
                label.set_label("Layer key")
            else:
                tap = actions.BY_ID.get(self.slot_binding(key, "tap")["action"], actions.BY_ID["none"])
                extra = sum(actions.is_set(self.slot_binding(key, s)) for s in ("hold", "double"))
                text = "—" if tap.id == "none" else tap.label
                if extra:
                    text = ("" if tap.id == "none" else text + " ") + f"+{extra}"
                label.set_label(text)
            if key == self.selected:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")

    def flash(self, key):
        if key not in self.key_buttons:
            return
        button = self.key_buttons[key][0]
        button.add_css_class("flash")
        GLib.timeout_add(220, lambda: button.remove_css_class("flash") or False)

    def select(self, key):
        self.commit_params()
        self.selected = key
        self.expanded_step = None
        self.refresh_pad()
        self.build_editor()

    def refresh_layer_switch(self):
        has_layer = bool(self.cfg.get("layer_key"))
        self.layer_switch.set_visible(has_layer)
        if not has_layer and self.layer:
            self.layer_switch.set_active_name("normal")

    # ---------------------------------------------------------------- editor
    def build_editor(self):
        self.param_widgets = {}
        key = self.selected
        page = Adw.PreferencesPage()

        context = self.profile["name"] + (" profile" if self.profile_index else " profile · applies everywhere")
        if self.layer:
            context += " · layer"
        header = Adw.PreferencesGroup(title=f"Key  {key}", description=context)
        page.add(header)

        if key == self.cfg.get("layer_key"):
            header.add(Adw.ActionRow(
                title="This is your layer key",
                subtitle="Hold it and press another key to run that key's Layer actions. "
                         "Change or turn it off in Settings."))
            self.editor.set_child(page)
            return

        slots = self.slots_for(key)
        has_extra = any(actions.is_set(self.slot_binding(key, s)) for s in slots if s != "tap")
        for slot in slots:
            page.add(self.build_slot(key, slot, has_extra))
        if self.profile_index:
            note = Adw.PreferencesGroup(
                description="Anything left as “(nothing)” here uses the Default profile's action.")
            page.add(note)
        if key == "000":
            page.add(Adw.PreferencesGroup(
                description="The 000 key sends three 0s at once, so it can't be held or double-tapped."))
        self.editor.set_child(page)

    def build_slot(self, key, slot, has_extra):
        binding = self.slot_binding(key, slot)
        action = actions.BY_ID.get(binding["action"], actions.BY_ID["none"])
        description = {
            "tap": "Runs when released, because this key also has Hold or Double tap"
                   if has_extra else "Runs instantly",
            "hold": "Runs after holding the key for about half a second",
            "double": "Runs on two quick presses",
        }[slot]
        group = Adw.PreferencesGroup(title=SLOT_TITLES[slot], description=description)

        combo = Adw.ComboRow(title="Action", model=Gtk.StringList(strings=ACTION_NAMES),
                             enable_search=True, search_match_mode=Gtk.StringFilterMatchMode.SUBSTRING,
                             expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        combo.set_selected(actions.ACTIONS.index(action))
        if action.repeat and slot != "double":
            combo.set_subtitle("Repeats while held")
        if action.confirm:
            how = {"tap": "Press once, then again", "hold": "Hold once, then hold again",
                   "double": "Double-tap, then double-tap again"}[slot]
            combo.set_subtitle(f"{how} within {actions.CONFIRM_MAX_SECONDS:g} s to confirm")
        combo.connect("notify::selected", self.on_action_changed, slot)
        group.add(combo)

        params = binding.get("params", {})
        widgets = self.param_widgets[slot] = {}
        for p in action.params:
            value = params.get(p.name, p.default)
            if p.kind == "text":
                row = Adw.EntryRow(title=p.label, text=value)
                row.connect("changed", lambda *_: self.mark_dirty())
                group.add(row)
                widgets[p.name] = row
            elif p.kind == "app":
                widgets[p.name] = self.app_row(p.label, value)
                group.add(widgets[p.name])
            elif p.kind == "macro":
                group.add(self.macro_editor(binding["params"].setdefault(p.name, [])))
            elif p.kind == "code":
                view = Gtk.TextView(monospace=True, css_classes=["code"], wrap_mode=Gtk.WrapMode.NONE)
                view.get_buffer().set_text(value)
                view.get_buffer().connect("changed", lambda *_: self.mark_dirty())
                frame = Gtk.Frame(child=Gtk.ScrolledWindow(child=view, min_content_height=200),
                                  css_classes=["view"], margin_top=8)
                group.add(frame)
                group.add(Gtk.Label(label=PYTHON_HELP, xalign=0, wrap=True, margin_top=6,
                                    css_classes=["dim-label", "caption"]))
                check = Gtk.Button(label="Check code", halign=Gtk.Align.START, margin_top=6)
                check.connect("clicked", lambda _b, v=view: self.check_code(v))
                group.add(check)
                widgets[p.name] = view

        if action.id != "none":
            test = Adw.ButtonRow(title="Test now", start_icon_name="media-playback-start-symbolic")
            test.connect("activated", lambda *_: self.test(slot))
            group.add(test)
        return group

    # ---------------------------------------------------------------- macro editor
    def macro_editor(self, steps):
        """Steps are edited in place in the binding (no commit_params needed)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=10)
        if steps:
            listbox = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
            for i in range(len(steps)):
                listbox.append(self.step_row(steps, i))
            box.append(listbox)
        else:
            box.append(Gtk.Label(label="No steps yet. Add actions and waits; they run top to bottom.",
                                 xalign=0, wrap=True, css_classes=["dim-label"]))
        buttons = Gtk.Box(spacing=8)
        add = Gtk.Button(child=Adw.ButtonContent(label="Add action", icon_name="list-add-symbolic"))
        add.connect("clicked", lambda *_: self.add_step(steps, "open_browser"))
        wait = Gtk.Button(child=Adw.ButtonContent(label="Add wait", icon_name="alarm-symbolic"))
        wait.connect("clicked", lambda *_: self.add_step(steps, "wait"))
        buttons.append(add)
        buttons.append(wait)
        box.append(buttons)
        return box

    @staticmethod
    def step_summary(step, action):
        params = step.get("params", {})
        if action.id == "wait":
            return f"Wait {params.get('seconds', '1')} s"
        values = [str(params.get(p.name, p.default)).removesuffix(".desktop")
                  for p in action.params if params.get(p.name, p.default)]
        return ", ".join(values)

    def step_row(self, steps, i):
        step = steps[i]
        action = actions.BY_ID.get(step.get("action"), actions.WAIT)
        if action.id not in actions.STEP_IDS:
            action = actions.WAIT
        row = Adw.ExpanderRow(title=f"{i + 1}.  {action_name(action)}", use_markup=False,
                              subtitle=self.step_summary(step, action),
                              expanded=i == self.expanded_step)
        remove = Gtk.Button(icon_name="edit-delete-symbolic", tooltip_text="Remove step",
                            valign=Gtk.Align.CENTER, css_classes=["flat"])
        remove.connect("clicked", lambda *_: self.change_steps(steps, lambda: steps.pop(i), None))
        row.add_suffix(remove)

        combo = Adw.ComboRow(title="Action", model=Gtk.StringList(strings=STEP_NAMES),
                             enable_search=True, search_match_mode=Gtk.StringFilterMatchMode.SUBSTRING,
                             expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        combo.set_selected(actions.STEP_ACTIONS.index(action))
        combo.connect("notify::selected", self.on_step_action_changed, steps, i)
        row.add_row(combo)

        params = step.setdefault("params", {})
        for p in action.params:
            value = params.get(p.name, p.default)
            if p.kind == "app":
                widget = self.app_row(p.label, value)
                params[p.name] = self.widget_value(widget)
                widget.connect("notify::selected",
                               lambda w, _ps, n=p.name: params.__setitem__(n, self.widget_value(w)))
            else:
                widget = Adw.EntryRow(title=p.label, text=value)
                widget.connect("changed", lambda w, n=p.name: self.on_step_param(params, n, w, row, step, action))
            row.add_row(widget)

        if len(steps) > 1:
            order = Adw.ActionRow(title="Order")
            for label, delta, enabled in (("Move up", -1, i > 0), ("Move down", 1, i < len(steps) - 1)):
                button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, sensitive=enabled)
                button.connect("clicked", lambda _b, d=delta: self.move_step(steps, i, d))
                order.add_suffix(button)
            row.add_row(order)
        return row

    def on_step_param(self, params, name, entry, row, step, action):
        params[name] = entry.get_text()
        row.set_subtitle(self.step_summary(step, action))
        self.mark_dirty()

    def change_steps(self, steps, change, expand):
        change()
        self.expanded_step = expand
        self.mark_dirty()
        GLib.idle_add(self.build_editor)  # don't destroy widgets inside their own signal

    def add_step(self, steps, action_id):
        action = actions.BY_ID[action_id]
        new = {"action": action_id, "params": {p.name: copy.deepcopy(p.default) for p in action.params}}
        self.change_steps(steps, lambda: steps.append(new), len(steps))

    def move_step(self, steps, i, delta):
        def swap():
            steps[i], steps[i + delta] = steps[i + delta], steps[i]
        self.change_steps(steps, swap, i + delta)

    def on_step_action_changed(self, combo, _pspec, steps, i):
        action = actions.STEP_ACTIONS[combo.get_selected()]
        if action.id == steps[i].get("action"):
            return
        new = {"action": action.id, "params": {p.name: copy.deepcopy(p.default) for p in action.params}}
        self.change_steps(steps, lambda: steps.__setitem__(i, new), i)

    def app_row(self, title, current):
        apps = sorted((a for a in Gio.AppInfo.get_all() if a.should_show()),
                      key=lambda a: a.get_display_name().lower())
        ids = [a.get_id() for a in apps]
        combo = Adw.ComboRow(title=title, enable_search=True, search_match_mode=Gtk.StringFilterMatchMode.SUBSTRING,
                             model=Gtk.StringList(strings=[a.get_display_name() for a in apps]),
                             expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        combo.app_ids = ids
        if current in ids:
            combo.set_selected(ids.index(current))
        elif ids:
            self.mark_dirty()  # the first app is now chosen
        combo.connect("notify::selected", lambda *_: self.mark_dirty())
        return combo

    def on_action_changed(self, combo, _pspec, slot):
        action = actions.ACTIONS[combo.get_selected()]
        if action.id == self.slot_binding(self.selected, slot)["action"]:
            return
        self.commit_params()
        self.keymap().setdefault(self.selected, {})[slot] = {
            "action": action.id, "params": {p.name: copy.deepcopy(p.default) for p in action.params}}
        self.mark_dirty()
        self.refresh_pad()
        GLib.idle_add(self.build_editor)  # don't destroy the combo inside its own signal

    @staticmethod
    def widget_value(widget):
        if isinstance(widget, Gtk.TextView):
            buf = widget.get_buffer()
            return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if isinstance(widget, Adw.ComboRow):
            index = widget.get_selected()
            return widget.app_ids[index] if index < len(widget.app_ids) else ""
        return widget.get_text()

    def commit_params(self):
        if self.selected is None:
            return
        for slot, widgets in self.param_widgets.items():
            binding = self.keymap().get(self.selected, {}).get(slot)
            if binding and widgets:
                binding["params"] = {n: self.widget_value(w) for n, w in widgets.items()}

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.title_widget.set_subtitle("Unsaved changes")

    # ---------------------------------------------------------------- profiles & layer
    def refresh_profiles(self):
        names = [p["name"] for p in self.cfg["profiles"]]
        self.profile_dropdown.set_model(Gtk.StringList(strings=names))
        self.profile_dropdown.set_selected(min(self.profile_index, len(names) - 1))

    def on_profile_changed(self, dropdown, _pspec):
        index = dropdown.get_selected()
        if index == Gtk.INVALID_LIST_POSITION or index == self.profile_index:
            return
        self.commit_params()
        self.profile_index = index
        self.refresh_pad()
        self.build_editor()

    def on_layer_changed(self, group, _pspec):
        self.commit_params()
        self.layer = group.get_active_name() == "layer"
        self.refresh_pad()
        self.build_editor()

    def _install_profile_actions(self):
        for name, handler in (("new-profile", lambda *_: self.profile_dialog(None)),
                              ("edit-profile", lambda *_: self.profile_dialog(self.profile_index)),
                              ("delete-profile", lambda *_: self.delete_profile())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def profile_dialog(self, index):
        if index == 0:
            self.toast("The Default profile always applies and can't be edited.")
            return
        profile = self.cfg["profiles"][index] if index else {"name": "", "match": ""}
        dialog = Adw.AlertDialog(heading="Edit profile" if index else "New profile",
                                 body="A profile's keys apply while one of its apps is focused. "
                                      "Keys it doesn't set use the Default profile.")
        group = Adw.PreferencesGroup()
        name = Adw.EntryRow(title="Name", text=profile["name"])
        classes = Adw.EntryRow(title="Window classes (comma-separated)", text=profile["match"])
        group.add(name)
        group.add(classes)
        windows = open_windows()
        if windows:
            picker = Adw.ComboRow(title="Add an open window",
                                  model=Gtk.StringList(strings=["—"] + [f"{t[:40]}  ({c})" for c, t in windows]))

            def picked(row, _pspec):
                i = row.get_selected()
                if i > 0:
                    current = [c.strip() for c in classes.get_text().split(",") if c.strip()]
                    if windows[i - 1][0] not in current:
                        classes.set_text(", ".join(current + [windows[i - 1][0]]))
                    if not name.get_text():
                        name.set_text(windows[i - 1][0].split(".")[-1])
            picker.connect("notify::selected", picked)
            group.add(picker)
        dialog.set_extra_child(group)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Save" if index else "Create")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_d, response):
            if response != "ok" or not name.get_text().strip():
                return
            if index:
                profile["name"], profile["match"] = name.get_text().strip(), classes.get_text().strip()
            else:
                self.commit_params()
                self.cfg["profiles"].append({"name": name.get_text().strip(),
                                             "match": classes.get_text().strip(),
                                             "bindings": {}, "layer_bindings": {}})
                self.profile_index = len(self.cfg["profiles"]) - 1
            self.mark_dirty()
            self.refresh_profiles()
            self.refresh_pad()
            self.build_editor()
        dialog.connect("response", on_response)
        dialog.present(self)

    def delete_profile(self):
        if self.profile_index == 0:
            self.toast("The Default profile can't be deleted.")
            return
        dialog = Adw.AlertDialog(heading=f"Delete “{self.profile['name']}”?",
                                 body="Its key setup will be removed.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_d, response):
            if response == "delete":
                del self.cfg["profiles"][self.profile_index]
                self.profile_index = 0
                self.param_widgets = {}
                self.mark_dirty()
                self.refresh_profiles()
                self.refresh_pad()
                self.build_editor()
        dialog.connect("response", on_response)
        dialog.present(self)

    # ---------------------------------------------------------------- service link
    def on_service_message(self, message):
        event = message.get("event")
        if event == "status":
            self.update_status(message)
        elif event == "key":
            self.flash(message["key"])
            if self.learn.get_active():
                self.select(message["key"])
        elif event == "detected" and self.on_detected:
            callback, self.on_detected = self.on_detected, None
            callback(message.get("spec"), None)
        return False

    def update_status(self, message):
        for cls in ("success", "warning", "error", "dim-label"):
            self.status.remove_css_class(cls)
        if not message.get("running"):
            self.status.set_label("●  Service not running")
            self.status.add_css_class("error")
            self.banner.set_revealed(True)
            if self.learn.get_active():
                self.learn.set_active(False)
            return
        self.banner.set_revealed(False)
        if message.get("connected"):
            devices = message.get("devices") or ["numpad"]
            self.status.set_label(f"●  Running · {min(devices, key=len)} connected")
            self.status.add_css_class("success")
        else:
            self.status.set_label("●  Running · numpad not plugged in")
            self.status.add_css_class("warning")
        if self.learn.get_active():  # reconnected: re-enable capture
            self.link.send({"cmd": "capture", "on": True})

    def on_learn_toggled(self, button):
        if button.get_active() and not self.link.connected:
            self.toast("Learn mode needs the background service running.")
            button.set_active(False)
            return
        self.link.send({"cmd": "capture", "on": button.get_active()})
        if button.get_active():
            self.toast("Learn mode: press a key on the numpad")

    def start_service(self, _banner):
        subprocess.run(["systemctl", "--user", "start", "numpad-control"], check=False)
        self.toast("Starting the service…")

    def detect(self, done):
        """Find the numpad: via the service if it runs (it owns the device), else directly."""
        if self.link.connected:
            self.on_detected = done
            self.link.send({"cmd": "detect"})
        else:
            from . import daemon
            in_background(daemon.detect_device, done)

    # ---------------------------------------------------------------- feedback
    def toast(self, message):
        self.toasts.add_toast(Adw.Toast(title=message, use_markup=False, timeout=3))

    def error(self, heading, body):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.present(self)

    def check_code(self, view):
        problems = sandbox.validate(self.widget_value(view))
        if problems:
            self.error("Code rejected", "\n".join(problems))
        else:
            self.toast("Code looks OK")

    def test(self, slot):
        self.commit_params()
        key, binding = self.selected, self.slot_binding(self.selected, slot)
        if actions.BY_ID[binding["action"]].confirm:
            self.toast("Not run from here, to keep your session safe. On the numpad: "
                       "press once, then again to confirm.")
            return
        self.toast(f"Running key {key} ({SLOT_TITLES[slot].lower()})…")

        def done(output, error):
            if error:
                self.error(f"Key {key} failed", str(error))
            else:
                self.toast(f"Key {key} ran OK" + (f": {output}" if output else ""))
        in_background(lambda: actions.run(self.cfg, binding), done)

    # ---------------------------------------------------------------- save / close
    def all_bindings(self):
        for profile in self.cfg["profiles"]:
            for kind in ("bindings", "layer_bindings"):
                for key, slots in profile[kind].items():
                    for slot, binding in slots.items():
                        yield profile, kind, key, slot, binding

    def save(self):
        self.commit_params()
        for profile, kind, key, slot, binding in self.all_bindings():
            problems = actions.binding_problems(binding)
            if problems:
                self.error(f"{profile['name']}: key {key} ({SLOT_TITLES[slot]}): can't save",
                           "\n".join(problems))
                return False
            if binding.get("action") == "run_python":
                problems = sandbox.validate(binding["params"].get("code", ""))
                if problems:
                    self.error(f"{profile['name']}: key {key} ({SLOT_TITLES[slot]}): code rejected",
                               "\n".join(problems))
                    return False
        for profile in self.cfg["profiles"]:  # drop empty slots and keys
            for kind in ("bindings", "layer_bindings"):
                profile[kind] = {
                    key: kept for key, slots in profile[kind].items()
                    if (kept := {s: b for s, b in slots.items() if actions.is_set(b)})}
        config.save(self.cfg)
        self.dirty = False
        self.title_widget.set_subtitle("")
        self.toast("Saved. The service picks it up automatically.")
        return True

    def on_visibility_changed(self, *_):
        if not self.get_visible() and self.learn.get_active():
            self.learn.set_active(False)  # never leave the numpad blocked while hidden

    def discard_changes(self):
        self.cfg = config.load()
        self.dirty = False
        self.title_widget.set_subtitle("")
        self.profile_index = min(self.profile_index, len(self.cfg["profiles"]) - 1)
        self.param_widgets = {}
        self.refresh_profiles()
        self.refresh_layer_switch()
        self.refresh_pad()
        self.build_editor()

    def on_close_request(self, _window):
        self.commit_params()
        if not self.dirty:
            return False
        dialog = Adw.AlertDialog(heading="Save changes?",
                                 body="Your key setup has unsaved changes.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("discard", "Discard")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        def on_response(_d, response):
            if response == "discard":
                self.discard_changes()
                self.close()
            elif response == "save" and self.save():
                self.close()
        dialog.connect("response", on_response)
        dialog.present(self)
        return True


class SettingsDialog(Adw.PreferencesDialog):
    def __init__(self, win):
        super().__init__(title="Settings")
        self.win = win
        cfg = win.cfg
        page = Adw.PreferencesPage()

        device = Adw.PreferencesGroup(title="Device")
        self.device_row = Adw.ActionRow(title="Numpad")
        self.update_device_row()
        self.detect_button = Gtk.Button(label="Detect…", valign=Gtk.Align.CENTER)
        self.detect_button.connect("clicked", self.detect)
        self.device_row.add_suffix(self.detect_button)
        device.add(self.device_row)
        self.grab = Adw.SwitchRow(title="Stop numpad from typing",
                                  subtitle="Keys only trigger actions, no digits get typed",
                                  active=cfg["grab"])
        device.add(self.grab)
        page.add(device)

        keys = Adw.PreferencesGroup(title="Keys")
        self.layer_choices = [None] + LAYER_KEY_CHOICES
        self.layer_key = Adw.ComboRow(
            title="Layer key",
            subtitle="Hold it to give every other key a second set of actions",
            model=Gtk.StringList(strings=["Off"] + LAYER_KEY_CHOICES))
        self.layer_key.set_selected(self.layer_choices.index(cfg.get("layer_key")))
        keys.add(self.layer_key)
        self.feedback = Adw.SwitchRow(title="On-screen confirmations",
                                      subtitle="e.g. “Recording” when OBS starts recording",
                                      active=cfg.get("feedback", True))
        keys.add(self.feedback)
        page.add(keys)

        s = cfg["obs"]
        group = Adw.PreferencesGroup(
            title="OBS",
            description="In OBS: Tools → WebSocket Server Settings → Enable WebSocket server. "
                        "Use “Show Connect Info” to see the password.")
        self.host = Adw.EntryRow(title="Host", text=s.get("host", "localhost"))
        self.port = Adw.SpinRow.new_with_range(1, 65535, 1)
        self.port.set_title("Port")
        self.port.set_value(int(s.get("port", 4455)))
        self.password = Adw.PasswordEntryRow(title="Password", text=s.get("password", ""))
        test = Adw.ButtonRow(title="Test connection")
        test.connect("activated", self.test_obs)
        for row in (self.host, self.port, self.password, test):
            group.add(row)
        page.add(group)

        self.add(page)
        self.connect("closed", self.on_closed)

    def obs_values(self):
        return {"host": self.host.get_text().strip() or "localhost",
                "port": int(self.port.get_value()),
                "password": self.password.get_text()}

    def update_device_row(self):
        d = self.win.cfg["device"]
        self.device_row.set_subtitle(f"{d.get('name', 'USB numpad')}  ({d['vendor']}:{d['product']})")

    def detect(self, _button):
        self.detect_button.set_sensitive(False)
        self.device_row.set_subtitle("Press any key on your numpad (15 s)…")

        def done(spec, error):
            self.detect_button.set_sensitive(True)
            if error:
                self.update_device_row()
                self.add_toast(Adw.Toast(title=str(error), use_markup=False))
            elif spec is None:
                self.update_device_row()
                self.add_toast(Adw.Toast(title="No numpad key press was seen.", use_markup=False))
            else:
                self.win.cfg["device"] = spec
                self.win.mark_dirty()
                self.update_device_row()
        self.win.detect(done)

    def test_obs(self, _row):
        settings = self.obs_values()

        def done(version, error):
            message = str(error) if error else f"Connected to OBS {version}"
            self.add_toast(Adw.Toast(title=message, use_markup=False))
        in_background(lambda: obs.test_connection(settings), done)

    def on_closed(self, _dialog):
        cfg = self.win.cfg
        new = {"obs": self.obs_values(), "grab": self.grab.get_active(),
               "feedback": self.feedback.get_active(),
               "layer_key": self.layer_choices[self.layer_key.get_selected()]}
        if any(cfg.get(k) != v for k, v in new.items()):
            self.win.commit_params()
            cfg.update(new)
            self.win.mark_dirty()
            self.win.refresh_layer_switch()
            self.win.refresh_pad()
            self.win.build_editor()


class App(Adw.Application):
    """Stays running in the background: closing the window only hides it."""

    def __init__(self, hidden=False):
        super().__init__(application_id=APP_ID)
        self.start_hidden = hidden
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        with open(PID_PATH, "w") as f:
            f.write(str(os.getpid()))
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.request_quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_shutdown(self):
        try:
            os.remove(PID_PATH)
        except FileNotFoundError:
            pass
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        if self.window is None:
            self.window = Window(self)
            if self.start_hidden:  # started at login: wait in the background
                self.start_hidden = False
                return
        elif self.window.get_visible() and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            # Launched again while open: Hyprland ignores present() by default
            # (misc:focus_on_activate), so ask it directly to jump to the window.
            subprocess.run(["hyprctl", "dispatch",
                            f'hl.dsp.focus({{ window = "class:{APP_ID}" }})'],
                           capture_output=True, timeout=5)
        self.window.present()

    def request_quit(self):
        if self.window and self.window.dirty:
            self.window.present()
            self.window.toast("Save or discard your changes before quitting.")
        else:
            self.quit()


def run(args=()):
    hidden = "--hidden" in args
    app = App(hidden)
    if hidden:
        app.register(None)
        if app.get_is_remote():
            return  # already running; don't pop the window up
    app.run([])
