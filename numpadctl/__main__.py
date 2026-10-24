"""numpadctl [gui [--hidden]|run|detect|list]"""

import sys


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "gui"
    if command == "gui":
        from . import gui
        gui.run(sys.argv[2:])
    elif command == "run":
        from . import daemon
        daemon.run()
    elif command == "detect":
        from . import daemon
        print("Press a key on your numpad…")
        print(daemon.detect_device() or "nothing pressed")
    elif command == "list":
        import evdev
        for path in evdev.list_devices():
            d = evdev.InputDevice(path)
            print(f"{path}  {d.info.vendor:04x}:{d.info.product:04x}  {d.name}")
    else:
        print(__doc__)
        sys.exit(1)


main()
