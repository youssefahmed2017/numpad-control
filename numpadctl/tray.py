"""System tray icon (StatusNotifierItem over D-Bus), with a small right-click menu.

GTK4 has no tray API, so this speaks the protocol KDE Plasma (and most bars)
use directly: an org.kde.StatusNotifierItem object for the icon, and a minimal
com.canonical.dbusmenu object for its menu.
"""

import os

from gi.repository import Gio, GLib

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

INTERFACES = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
    </method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="AboutToShowGroup">
      <arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/>
    </method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
  </interface>
</node>
"""


class TrayIcon:
    """menu: [(label, callback)]; on_activate: called on a left click."""

    def __init__(self, title, icon_name, tooltip, on_activate, menu):
        self.title, self.icon_name, self.tooltip = title, icon_name, tooltip
        self.on_activate = on_activate
        self.menu = menu  # item ids are 1..len(menu); 0 is the root
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        info = Gio.DBusNodeInfo.new_for_xml(INTERFACES)
        self.bus.register_object(ITEM_PATH, info.lookup_interface("org.kde.StatusNotifierItem"),
                                 self._item_call, self._item_property, None)
        self.bus.register_object(MENU_PATH, info.lookup_interface("com.canonical.dbusmenu"),
                                 self._menu_call, self._menu_property, None)
        Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        # (Re-)register whenever the panel's tray host appears, e.g. after plasmashell restarts.
        Gio.bus_watch_name_on_connection(self.bus, "org.kde.StatusNotifierWatcher",
                                         Gio.BusNameWatcherFlags.NONE, self._register, None)

    def _register(self, *_):
        self.bus.call("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                      "org.kde.StatusNotifierWatcher", "RegisterStatusNotifierItem",
                      GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 5000, None, None)

    # ---------------------------------------------------------------- the icon
    def _item_property(self, _bus, _sender, _path, _iface, prop):
        values = {
            "Category": ("s", "ApplicationStatus"), "Id": ("s", "numpad-control"),
            "Title": ("s", self.title), "Status": ("s", "Active"), "WindowId": ("i", 0),
            "IconName": ("s", self.icon_name), "IconPixmap": ("a(iiay)", []),
            "OverlayIconName": ("s", ""), "AttentionIconName": ("s", ""),
            "ToolTip": ("(sa(iiay)ss)", (self.icon_name, [], self.title, self.tooltip)),
            "ItemIsMenu": ("b", False), "Menu": ("o", MENU_PATH),
        }
        kind, value = values[prop]
        return GLib.Variant(kind, value)

    def _item_call(self, _bus, _sender, _path, _iface, method, _params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self.on_activate)
        invocation.return_value(None)

    # ---------------------------------------------------------------- its menu
    def _item_layout(self, item_id):
        label, _ = self.menu[item_id - 1]
        return GLib.Variant("(ia{sv}av)", (item_id, {"label": GLib.Variant("s", label)}, []))

    def _menu_property(self, _bus, _sender, _path, _iface, prop):
        return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"), "IconThemePath": GLib.Variant("as", [])}[prop]

    def _menu_call(self, _bus, _sender, _path, _iface, method, params, invocation):
        ids = range(1, len(self.menu) + 1)
        if method == "GetLayout":
            children = [GLib.Variant("v", self._item_layout(i)) for i in ids]
            root = (0, {"children-display": GLib.Variant("s", "submenu")}, children)
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (1, root)))
        elif method == "GetGroupProperties":
            wanted = params.unpack()[0]
            items = [(i, {"label": GLib.Variant("s", self.menu[i - 1][0])}) for i in wanted if i in ids]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (items,)))
        elif method == "GetProperty":
            item_id, name = params.unpack()
            label = self.menu[item_id - 1][0] if item_id in ids and name == "label" else ""
            invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", label),)))
        elif method == "Event":
            item_id, event = params.unpack()[:2]
            if event == "clicked" and item_id in ids:
                GLib.idle_add(self.menu[item_id - 1][1])
            invocation.return_value(None)
        elif method == "EventGroup":
            for item_id, event, _data, _time in params.unpack()[0]:
                if event == "clicked" and item_id in ids:
                    GLib.idle_add(self.menu[item_id - 1][1])
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_value(None)
