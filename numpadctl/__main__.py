"""numpadctl [gui [--hidden]|run|tray|detect [--json]|list|check|usb-info]"""

import sys


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "gui"
    if command == "gui":
        from . import gui
        sys.exit(gui.run(sys.argv[2:]))
    elif command == "tray":
        from .platform import IS_WINDOWS
        if not IS_WINDOWS:
            sys.exit("The tray app is for Windows; on Linux the service runs under systemd "
                     "(systemctl --user status numpad-control).")
        from .platform import windows_tray
        windows_tray.main()
    elif command == "run":
        from . import daemon
        daemon.run()
    elif command == "detect":
        from . import daemon
        if "--json" in sys.argv:  # for install.sh
            import json
            print(json.dumps(daemon.detect_device()))
        else:
            print("Press a key on your numpad…")
            print(daemon.detect_device() or "nothing pressed")
    elif command == "list":
        from .platform import numpad_input
        for device, vendor, product, name in numpad_input.list_devices():
            print(f"{device}  {vendor}:{product}  {name}")
    elif command == "check":
        from . import check
        sys.exit(check.main())
    elif command == "usb-info":
        # For install-usb-fix.sh: which USB port the configured numpad is on.
        from pathlib import Path
        from . import config
        device = config.load()["device"]
        print(f"VENDOR={device['vendor']}\nPRODUCT={device['product']}")
        for dev in Path("/sys/bus/usb/devices").iterdir():
            try:
                if ((dev / "idVendor").read_text().strip(), (dev / "idProduct").read_text().strip()) \
                        == (device["vendor"], device["product"]):
                    print(f"PORT={dev.name}")
                    break
            except OSError:
                continue
    else:
        print(__doc__)
        sys.exit(1)


main()
