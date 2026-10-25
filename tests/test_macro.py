import time
import unittest
from unittest import mock

from numpadctl import actions


def step(action, **params):
    return {"action": action, "params": params}


class MacroTest(unittest.TestCase):
    def setUp(self):
        self.ran = []
        fake = lambda name: actions.Action(name, name, lambda cfg: self.ran.append(name))
        failing = actions.Action("boom", "Boom", lambda cfg: (_ for _ in ()).throw(RuntimeError("nope")))
        extra = {"a": fake("a"), "b": fake("b"), "boom": failing}
        self.patches = [mock.patch.dict(actions.BY_ID, extra),
                        mock.patch.object(actions, "STEP_IDS", actions.STEP_IDS | set(extra))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_macro(self, *steps):
        return actions.run({}, {"action": "macro", "params": {"steps": list(steps)}})

    def test_steps_run_in_order_with_wait(self):
        start = time.monotonic()
        self.run_macro(step("a"), step("wait", seconds="0.2"), step("b"))
        self.assertEqual(self.ran, ["a", "b"])
        self.assertGreaterEqual(time.monotonic() - start, 0.15)  # Windows timers are coarse

    def test_stops_at_failing_step(self):
        with self.assertRaisesRegex(actions.ActionError, r"step 2 \(Boom\) failed: nope"):
            self.run_macro(step("a"), step("boom"), step("b"))
        self.assertEqual(self.ran, ["a"])

    def test_rejected_macros(self):
        cases = {
            "empty": [],
            "nested macro": [step("macro", steps=[])],
            "python": [step("run_python", code="print(1)")],
            "wait too long": [step("wait", seconds="600")],
            "wait not a number": [step("wait", seconds="soon")],
        }
        for name, steps in cases.items():
            with self.subTest(name):
                self.assertTrue(actions.macro_problems(steps))
                with self.assertRaises(actions.ActionError):
                    self.run_macro(*steps)
        self.assertEqual(self.ran, [])

    def test_new_bindings_do_not_share_the_default_list(self):
        p = actions.BY_ID["macro"].params[0]
        self.assertEqual(p.default, [])
        actions.perform({}, {"action": "macro", "params": {"steps": [step("a")]}})
        self.assertEqual(p.default, [])


if __name__ == "__main__":
    unittest.main()
