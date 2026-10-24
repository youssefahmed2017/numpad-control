#!/bin/sh
# Installs the udev rule (needs sudo), the user service and the menu entry.
set -e
cd "$(dirname "$0")"
sudo install -m 644 dist/70-numpad-control.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=input
install -Dm 644 dist/numpad-control.service ~/.config/systemd/user/numpad-control.service
install -Dm 755 dist/numpad-control ~/.local/bin/numpad-control
mkdir -p ~/.local/share/applications
sed "s|@HOME@|$HOME|g" dist/numpad-control.desktop > ~/.local/share/applications/numpad-control.desktop
# KDE: start the settings window hidden at login (it shows a tray icon).
# Hyprland users start it from their Hyprland config instead (see README).
mkdir -p ~/.config/autostart
sed "s|@HOME@|$HOME|g" dist/numpad-control-autostart.desktop > ~/.config/autostart/numpad-control.desktop
systemctl --user daemon-reload
systemctl --user enable --now numpad-control
echo "Done. Open 'Numpad Control' from your app launcher to set up keys."
echo "Logs: journalctl --user -u numpad-control -f"
