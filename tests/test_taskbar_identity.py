"""The settings window gets its own taskbar identity on Windows (else it wears pythonw.exe's Python icon)."""

import unittest

from numpadctl import ui_common


class FakeShell32:
    def __init__(self, fail=False):
        self.ids, self.fail = [], fail

    def SetCurrentProcessExplicitAppUserModelID(self, app_id):
        if self.fail:
            raise OSError("no shell")
        self.ids.append(app_id)


class TaskbarIdentityTest(unittest.TestCase):
    def test_the_id_is_set_once_with_the_windows_name(self):
        shell = FakeShell32()
        ui_common.set_windows_app_id(shell)
        self.assertEqual(shell.ids, ["NumpadPilot.Settings"])

    def test_a_failing_call_is_ignored(self):
        ui_common.set_windows_app_id(FakeShell32(fail=True))

    def test_does_nothing_when_not_on_windows(self):
        if not ui_common.IS_WINDOWS:
            ui_common.set_windows_app_id()  # must not touch ctypes.windll (it doesn't exist here)


if __name__ == "__main__":
    unittest.main()
