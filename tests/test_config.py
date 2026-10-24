import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import config


class ConfigTest(unittest.TestCase):
    def test_old_format_is_migrated(self):
        old = {"device": {"vendor": "c0f4", "product": "05f5"}, "grab": True,
               "obs": {"host": "localhost", "port": 4455, "password": ""},
               "bindings": {"1": {"action": "open_browser", "params": {}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(old))
            with mock.patch.object(config, "CONFIG_PATH", path):
                cfg = config.load()
        self.assertEqual(cfg["profiles"][0]["bindings"]["1"],
                         {"tap": {"action": "open_browser", "params": {}}})
        self.assertNotIn("bindings", cfg)
        self.assertIsNone(cfg["layer_key"])

    def test_profile_match_is_case_insensitive_list(self):
        p = {"match": "Firefox, kitty"}
        self.assertTrue(config.profile_matches(p, "firefox"))
        self.assertTrue(config.profile_matches(p, "kitty"))
        self.assertFalse(config.profile_matches(p, "obs"))
        self.assertFalse(config.profile_matches(p, ""))


if __name__ == "__main__":
    unittest.main()
