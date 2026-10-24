import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import actions, modes


def step(action, **params):
    return {"action": action, "params": params}


class ModesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state_dir = Path(self.tmp.name)
        self.patches = [mock.patch.object(modes, "STATE_DIR", state_dir),
                        mock.patch.object(modes, "STATE_PATH", state_dir / "modes.json")]
        self.ran = []
        fake = lambda name: actions.Action(name, name, lambda cfg: self.ran.append(name))
        boom = actions.Action("boom", "Boom", lambda cfg: (_ for _ in ()).throw(RuntimeError("nope")))
        extra = {"a": fake("a"), "b": fake("b"), "boom": boom}
        self.patches += [mock.patch.dict(actions.BY_ID, extra),
                         mock.patch.object(actions, "STEP_IDS", actions.STEP_IDS | set(extra))]
        for p in self.patches:
            p.start()
        self.cfg = {"modes": ["Stream mode", "Gaming"], "feedback": False}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_action(self, action, **params):
        return actions.run(self.cfg, step(action, **params))

    def test_toggle_on_off_and_persist(self):
        self.assertEqual(self.run_action("mode_toggle", mode="stream MODE"), "Stream mode on")
        self.assertTrue(modes.is_on("Stream mode"))
        self.assertEqual(self.run_action("mode_toggle", mode="Stream mode"), "Stream mode off")
        self.run_action("mode_on", mode="Gaming")
        self.assertEqual(modes.states(), {"Stream mode": False, "Gaming": True})  # read back from the file
        self.run_action("mode_off", mode="Gaming")
        self.assertFalse(modes.is_on("Gaming"))

    def test_unknown_mode(self):
        with self.assertRaisesRegex(actions.ActionError, "no mode called 'Chill'"):
            self.run_action("mode_toggle", mode="Chill")

    def test_if_runs_the_matching_branch(self):
        binding = step("if_mode", mode="Stream mode", then=[step("a")], otherwise=[step("b")])
        actions.run(self.cfg, binding)
        modes.set_mode("Stream mode", True)
        actions.run(self.cfg, binding)
        self.assertEqual(self.ran, ["b", "a"])

    def test_empty_branch_does_nothing(self):
        modes.set_mode("Gaming", True)
        actions.run(self.cfg, step("if_mode", mode="Gaming", then=[], otherwise=[step("a")]))
        self.assertEqual(self.ran, [])

    def test_branch_failure_names_the_step(self):
        modes.set_mode("Gaming", True)
        with self.assertRaisesRegex(actions.ActionError, r"step 2 \(Boom\) failed: nope"):
            actions.run(self.cfg, step("if_mode", mode="Gaming",
                                       then=[step("a"), step("boom"), step("b")], otherwise=[]))
        self.assertEqual(self.ran, ["a"])

    def test_bad_settings_stop_it_before_anything_runs(self):
        modes.set_mode("Gaming", True)
        with self.assertRaisesRegex(actions.ActionError, "if on, step 2: wait must be between"):
            actions.run(self.cfg, step("if_mode", mode="Gaming",
                                       then=[step("a"), step("wait", seconds="-1")], otherwise=[]))
        self.assertEqual(self.ran, [])

    def test_problems_found_on_save(self):
        problems = lambda b: actions.binding_problems(b, self.cfg)
        self.assertEqual(problems(step("if_mode", mode="Gaming", then=[step("a")], otherwise=[])), [])
        self.assertIn("both branches are empty",
                      problems(step("if_mode", mode="Gaming", then=[], otherwise=[])))
        self.assertTrue(problems(step("mode_toggle", mode="Removed mode")))
        self.assertIn("otherwise, step 1: unknown key 'Dwn' (examples: ctrl+c, Down, Enter, F5)",
                      problems(step("if_mode", mode="Gaming", then=[step("a")],
                                    otherwise=[step("press_keys", keys="Dwn")])))
        # a mode used inside a macro step is checked too
        self.assertTrue(problems(step("macro", steps=[step("mode_on", mode="Nope")])))

    def test_mode_steps_allowed_in_macros_but_not_if(self):
        self.assertIn("mode_toggle", actions.STEP_IDS)
        self.assertNotIn("if_mode", actions.STEP_IDS)

    def test_branches_do_not_share_defaults(self):
        params = actions.BY_ID["if_mode"].params
        self.assertEqual([p.default for p in params if p.kind == "macro"], [[], []])


if __name__ == "__main__":
    unittest.main()
