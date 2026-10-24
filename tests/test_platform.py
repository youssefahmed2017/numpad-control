import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from numpadctl.platform import paths


class PathsTest(unittest.TestCase):
    def test_linux_folders(self):
        env = {"XDG_CONFIG_HOME": "/c", "XDG_STATE_HOME": "/s", "XDG_RUNTIME_DIR": "/r"}
        with mock.patch.object(paths, "IS_WINDOWS", False), mock.patch.dict(os.environ, env):
            self.assertEqual(paths.config_dir(), Path("/c/numpad-control"))
            self.assertEqual(paths.state_dir(), Path("/s/numpad-control"))
            self.assertEqual(paths.runtime_dir(), Path("/r"))

    def test_windows_folders(self):
        env = {"APPDATA": "/AppData/Roaming", "LOCALAPPDATA": "/AppData/Local"}
        with mock.patch.object(paths, "IS_WINDOWS", True), mock.patch.dict(os.environ, env):
            self.assertEqual(paths.config_dir(), Path("/AppData/Roaming/numpad-control"))
            self.assertEqual(paths.state_dir(), Path("/AppData/Local/numpad-control/state"))
            self.assertEqual(paths.runtime_dir(), Path("/AppData/Local/numpad-control/run"))


class FileLockTest(unittest.TestCase):
    def test_second_holder_waits(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "x.lock"
            order = []

            def other():
                with paths.file_lock(lock):
                    order.append("other")
            with paths.file_lock(lock):
                thread = threading.Thread(target=other)
                thread.start()
                time.sleep(0.2)
                order.append("first")
            thread.join(2)
            self.assertEqual(order, ["first", "other"])


if __name__ == "__main__":
    unittest.main()
