"""Opening the settings when the app can't run (no PySide6): the settings file opens instead."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import config, gui


class GuiFallbackTest(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        for name, value in [("CONFIG_DIR", folder), ("CONFIG_PATH", folder / "config.json")]:
            patch = mock.patch.object(config, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        for patch in [mock.patch.object(gui, "app_installed", lambda: False),
                      mock.patch("numpadctl.crash.install")]:  # tested in test_crash
            patch.start()
            self.addCleanup(patch.stop)

    def test_opens_the_settings_file_creating_it_first(self):
        with mock.patch("numpadctl.platform.system.open_path") as open_path, \
                contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(gui.run([]), 0)
        open_path.assert_called_once_with(str(config.CONFIG_PATH))
        self.assertTrue(config.CONFIG_PATH.exists())
        self.assertIn("isn't installed", said.getvalue())

    def test_started_hidden_does_nothing(self):
        with mock.patch("numpadctl.platform.system.open_path") as open_path:
            self.assertEqual(gui.run(["--hidden"]), 0)
        open_path.assert_not_called()

    def test_uses_the_app_when_installed(self):
        fake_app = mock.Mock(**{"run.return_value": 7})
        with mock.patch.object(gui, "app_installed", lambda: True), \
                mock.patch.dict("sys.modules", {"numpadctl_ui": mock.Mock(app=fake_app), "numpadctl_ui.app": fake_app}):
            self.assertEqual(gui.run(["--hidden"]), 7)
        fake_app.run.assert_called_once_with(["--hidden"])


if __name__ == "__main__":
    unittest.main()
