# Linux desktops

Part of the [NumpadControl docs](../README.md).

## Hyprland, KDE Plasma and X11 desktops
The desktop is detected automatically (`XDG_CURRENT_DESKTOP`; any other desktop running on X11 is an "X11
desktop", e.g. XFCE) and each feature uses that desktop's own tools:

| Feature | Hyprland | KDE Plasma | X11 desktops (XFCE, Cinnamon, MATE, i3...) |
|---|---|---|---|
| Window actions, per-app profiles, Wait for window | `hyprctl` | kdotool | the window manager's standard calls, through python-xlib (nothing else to install) |
| Workspaces | Hyprland workspaces | virtual desktops | the window manager's workspaces |
| Toggle floating, scratchpad | yes | not available (Hyprland only) | not available (Hyprland only) |
| Hide all windows (Privacy panic) | an empty workspace | minimises every window | "show desktop" |
| On-screen popups, volume | SwayOSD | Plasma's own popups (also for volume: it is asked to show its slider) | a notification (needs a notification daemon: XFCE's `xfce4-notifyd`, or dunst); volume shows as one that replaces itself |
| Do not disturb | dunst | Plasma's Do Not Disturb | dunst, or XFCE's own notification daemon |
| Screenshots | grim + slurp | Spectacle | the first installed of maim, scrot, xfce4-screenshooter, gnome-screenshot, Spectacle |
| Lock screen | hyprlock | KDE's screen locker (`loginctl lock-session`) | `xflock4` (XFCE), else `loginctl lock-session` |
| Settings window at login | Hyprland autostart | KDE autostart (`~/.config/autostart`) | the same autostart entry |
| Hidden settings window | listed by your bar (PID file) | system tray icon | system tray icon |

**GNOME on Wayland** doesn't let programs read the focused window, list windows or switch workspaces, and
NumpadControl installs no shell extension. So it presses GNOME's own shortcuts for you (it reads the ones you have set,
custom ones included, and presses them with ydotool): next / previous workspace, go to or move a window to workspace N
(GNOME ships a shortcut for only some of them), close window, fullscreen and hide-all-windows (GNOME has no default
shortcut for these two: set one in *Settings → Keyboard → Keyboard Shortcuts*, and the action says where when it is
missing). **Not possible on GNOME:** per-app profiles, Focus a window, and Force-quit. Do not disturb uses GNOME's own
setting, popups are GNOME notifications, screenshots need `gnome-screenshot`, and the settings window has no tray icon
(GNOME has none without an extension): open it from the app grid.
