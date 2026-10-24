import unittest
from unittest import mock

from numpadctl import actions


class PowerConfirmTest(unittest.TestCase):
    def setUp(self):
        actions._armed.clear()
        self.clock = 1000.0
        self.patches = [
            mock.patch.object(actions.time, "monotonic", lambda: self.clock),
            mock.patch.object(actions.system, "power"),
            mock.patch.object(actions, "show_osd"),
        ]
        self.command = self.patches[1].start()
        self.osd = self.patches[2].start()
        self.patches[0].start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        actions._armed.clear()

    def press(self, action="shutdown", after=0.0, trigger="tap"):
        self.clock += after
        actions.run({"feedback": False}, {"action": action, "params": {}}, trigger=trigger)

    def test_single_press_only_asks(self):
        self.press()
        self.command.assert_not_called()
        self.assertEqual(self.osd.call_args.args[1], "Press again to shut down")
        self.assertTrue(self.osd.call_args.kwargs["force"], "prompt must show even with feedback off")

    def test_second_press_in_window_shuts_down(self):
        self.press()
        self.press(after=1.0)
        self.command.assert_called_once_with("poweroff")

    def test_reboot(self):
        self.press("reboot")
        self.press("reboot", after=2.0)
        self.command.assert_called_once_with("reboot")

    def test_too_late_rearms_instead(self):
        self.press()
        self.press(after=6.0)
        self.command.assert_not_called()
        self.press(after=1.0)
        self.command.assert_called_once()

    def test_bounce_does_not_confirm(self):
        self.press()
        self.press(after=0.1)
        self.command.assert_not_called()

    def test_shutdown_press_does_not_arm_reboot(self):
        self.press("shutdown")
        self.press("reboot", after=1.0)
        self.command.assert_not_called()

    def test_prompt_matches_how_the_key_is_used(self):
        for trigger, expected in (("hold", "Hold again to shut down"),
                                  ("double", "Double-tap again to shut down")):
            with self.subTest(trigger):
                actions._armed.clear()
                self.press(trigger=trigger)
                self.assertEqual(self.osd.call_args.args[1], expected)

    def test_hold_then_hold_again_shuts_down(self):
        self.press(trigger="hold")
        self.press(trigger="hold", after=1.5)
        self.command.assert_called_once_with("poweroff")

    def test_sleep_needs_confirming_too(self):
        self.press("suspend")
        self.command.assert_not_called()
        self.assertEqual(self.osd.call_args.args[1], "Press again to sleep")
        self.press("suspend", after=1.0)
        self.command.assert_called_once_with("suspend")

    def test_not_allowed_in_macros(self):
        self.assertNotIn("suspend", actions.STEP_IDS)
        self.assertNotIn("shutdown", actions.STEP_IDS)
        self.assertNotIn("reboot", actions.STEP_IDS)
        self.assertTrue(actions.macro_problems([{"action": "shutdown", "params": {}}]))


if __name__ == "__main__":
    unittest.main()
