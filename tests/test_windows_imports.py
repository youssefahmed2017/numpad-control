"""The service must load on Windows without Linux-only modules (simulated on Linux)."""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

SIMULATION = textwrap.dedent("""
    import asyncio, subprocess, ctypes, json, logging, threading, socket, secrets, select, re, struct, webbrowser
    import sys
    sys.platform = "win32"   # the real standard library is loaded; the project's code sees Windows
    class Block:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in {"evdev", "gi", "fcntl", "resource"}:
                raise ImportError("Linux-only module " + name + " loaded at import time")
    sys.meta_path.insert(0, Block())
    from numpadctl.platform import numpad_input, system
    import numpadctl.daemon, numpadctl.actions, numpadctl.config, numpadctl.modes
    from numpadctl.platform import windows_tray
    from numpadctl import actions, desktop
    print(numpad_input.open_numpad.__module__, system.press_keys.__module__,
          desktop.screenshot.__module__, desktop.current(), actions.audio.__name__)
""")


class WindowsImportTest(unittest.TestCase):
    def test_service_loads_with_windows_backends(self):
        done = subprocess.run([sys.executable, "-c", SIMULATION], capture_output=True, text=True,
                              cwd=Path(__file__).parent.parent, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split(),
                         ["numpadctl.platform.windows_rawinput", "numpadctl.platform.windows_system",
                          "numpadctl.platform.windows_desktop", "windows", "numpadctl.platform.windows_audio"])


if __name__ == "__main__":
    unittest.main()
