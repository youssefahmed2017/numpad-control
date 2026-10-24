import unittest
from unittest import mock

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw  # noqa: E402

from numpadctl import gui  # noqa: E402


class CommitParamsTest(unittest.TestCase):
    def test_step_lists_survive_committing_the_visible_fields(self):
        """Regression: committing the Mode field used to wipe an if/else key's step lists."""
        Adw.init()
        binding = {"action": "if_mode", "params": {"mode": "Old", "then": [{"action": "a"}],
                                                   "otherwise": [{"action": "b"}]}}
        window = mock.Mock(selected="3", param_widgets={"tap": {"mode": Adw.EntryRow(text="Stream mode")}},
                           widget_value=gui.Window.widget_value)
        window.keymap.return_value = {"3": {"tap": binding}}
        gui.Window.commit_params(window)
        self.assertEqual(binding["params"], {"mode": "Stream mode", "then": [{"action": "a"}],
                                             "otherwise": [{"action": "b"}]})


if __name__ == "__main__":
    unittest.main()
