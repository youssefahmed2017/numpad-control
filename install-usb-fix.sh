#!/bin/sh
# Installs the boot/resume "virtual replug" for numpads that aren't detected at
# boot or go silent after sleep. Plug the numpad in before running this.
set -e
cd "$(dirname "$0")"
info=$(.venv/bin/python -m numpadctl usb-info)   # VENDOR=… PRODUCT=… PORT=…
echo "$info" | grep -q '^PORT=.' || { echo "Numpad not found - plug it in and try again."; exit 1; }
echo "Numpad: $(echo $info)"
sudo install -d /etc/numpad-control
echo "$info" | sudo tee /etc/numpad-control/usb.conf > /dev/null
sudo install -m 755 dist/numpad-control-usb-kick /usr/local/bin/numpad-control-usb-kick
sudo install -m 644 dist/numpad-control-usb.service /etc/systemd/system/numpad-control-usb.service
sudo install -m 755 dist/numpad-control-sleep-hook /usr/lib/systemd/system-sleep/numpad-control
sudo systemctl daemon-reload
sudo systemctl enable numpad-control-usb.service
echo "Done. The numpad will be re-detected at boot if it was missed, and after sleep."
