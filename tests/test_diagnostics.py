"""The diagnostics report: complete, and without secrets."""

import unittest
from unittest import mock

from numpadctl import diagnostics


CFG = {"device": {"vendor": "c0f4", "product": "05f5"}, "grab": True,
       "obs": {"host": "localhost", "port": 4455, "password": "hunter2"},
       "profiles": [{"name": "Default", "bindings": {
           "1": {"tap": {"action": "press_keys", "params": {"keys": "ctrl+banana"}}},
           "2": {"tap": {"action": "media_next", "params": {}}}}}]}


class DiagnosticsTest(unittest.TestCase):
    def report(self, status):
        with mock.patch.object(diagnostics, "devices", return_value=["→ c0f4:05f5  Usb KeyBoard"]), \
                mock.patch.object(diagnostics, "log_tail", return_value=["line one"]), \
                mock.patch.object(diagnostics, "usb_errors", return_value=(["usb 1-8: device descriptor read/64, error -71"], 9)), \
                mock.patch.object(diagnostics, "version", return_value="abc1234"):
            return diagnostics.collect(CFG, status)

    def test_report_has_every_section_and_no_password(self):
        text = self.report({"running": True, "connected": False})
        for part in ("abc1234", "running, numpad NOT connected", "c0f4:05f5", "line one",
                     "failed 9 times", "Default · 1 tap:"):
            self.assertIn(part, text)
        self.assertNotIn("hunter2", text)

    def test_service_states(self):
        self.assertIn("Service: not running", self.report({"running": False}))
        self.assertIn("numpad connected", self.report({"running": True, "connected": True}))

    def test_no_problems_is_said_plainly(self):
        cfg = {**CFG, "profiles": [{"name": "Default", "bindings": {}}]}
        with mock.patch.object(diagnostics, "devices", return_value=[]), mock.patch.object(diagnostics, "log_tail", return_value=[]), \
                mock.patch.object(diagnostics, "usb_errors", return_value=([], 0)):
            self.assertIn("Key problems: none", diagnostics.collect(cfg, {}))


if __name__ == "__main__":
    unittest.main()
