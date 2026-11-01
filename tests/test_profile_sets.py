import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from numpadctl import actions, config, profile_sets


def binding(action):
    return {"tap": {"action": action, "params": {}}}


class SetsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.config_path = tmp / "config.json"
        patches = [mock.patch.object(config, "CONFIG_PATH", self.config_path),
                   mock.patch.object(config, "CONFIG_DIR", tmp),
                   mock.patch.object(profile_sets, "STATE_DIR", tmp),
                   mock.patch.object(profile_sets, "STATE_PATH", tmp / "profile_set.json")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def write(self, data):
        self.config_path.write_text(json.dumps(data))

    def two_sets(self):
        return {"sets": [
            {"name": "Coding", "profiles": [{"name": "Default", "match": "",
                                              "bindings": {"1": binding("open_browser")}, "layer_bindings": {}}]},
            {"name": "Streaming", "profiles": [{"name": "Default", "match": "",
                                                 "bindings": {"1": binding("mic_mute")}, "layer_bindings": {}}]}]}


class ProfileSetsTest(SetsCase):
    def test_profiles_before_sets_become_one_set_called_default(self):
        profiles = [{"name": "Default", "match": "", "bindings": {"1": binding("open_browser")}, "layer_bindings": {}},
                    {"name": "Kitty", "match": "kitty", "bindings": {}, "layer_bindings": {}}]
        self.write({"profiles": profiles})
        cfg = config.load()
        self.assertEqual([s["name"] for s in cfg["sets"]], ["Default"])
        self.assertEqual(cfg["profiles"], profiles)
        self.assertEqual(cfg["active_set"], "Default")

    def test_migration_survives_a_save_and_a_second_load(self):
        self.write({"profiles": [{"name": "Default", "match": "", "bindings": {"2": binding("mic_mute")}, "layer_bindings": {}}]})
        config.save(config.load())
        on_disk = json.loads(self.config_path.read_text())
        self.assertNotIn("profiles", on_disk)
        self.assertEqual(on_disk["sets"][0]["profiles"][0]["bindings"]["2"], binding("mic_mute"))
        self.assertEqual(config.load()["profiles"][0]["bindings"]["2"], binding("mic_mute"))

    def test_oldest_format_still_migrates_through_sets(self):
        self.write({"bindings": {"1": {"action": "open_browser", "params": {}}}})
        cfg = config.load()
        self.assertEqual(cfg["profiles"][0]["bindings"]["1"], binding("open_browser"))
        self.assertEqual(len(cfg["sets"]), 1)

    def test_fresh_install_has_one_default_set(self):
        cfg = config.load()  # no file
        self.assertEqual([s["name"] for s in cfg["sets"]], ["Default"])
        self.assertIs(cfg["profiles"], cfg["sets"][0]["profiles"])

    def test_the_active_set_decides_which_profiles_apply(self):
        self.write(self.two_sets())
        self.assertEqual(config.load()["active_set"], "Coding")  # the first, until you switch
        profile_sets.set_active("Streaming")
        cfg = config.load()
        self.assertEqual(config.resolve(cfg, "1", False, "")["tap"]["action"], "mic_mute")

    def test_sets_do_not_share_keys(self):
        data = self.two_sets()
        del data["sets"][1]["profiles"][0]["bindings"]["1"]
        self.write(data)
        profile_sets.set_active("Streaming")
        self.assertEqual(config.resolve(config.load(), "1", False, ""), {})

    def test_saving_writes_edits_into_the_active_set_only(self):
        self.write(self.two_sets())
        profile_sets.set_active("Streaming")
        cfg = config.load()
        cfg["profiles"][0]["bindings"]["3"] = binding("lock_screen")
        config.save(cfg)
        sets = {s["name"]: s for s in json.loads(self.config_path.read_text())["sets"]}
        self.assertIn("3", sets["Streaming"]["profiles"][0]["bindings"])
        self.assertNotIn("3", sets["Coding"]["profiles"][0]["bindings"])

    def test_save_after_the_service_switched_still_lands_in_the_set_it_was_loaded_from(self):
        self.write(self.two_sets())
        cfg = config.load()  # the window opened on Coding
        profile_sets.set_active("Streaming")  # a key switched meanwhile
        cfg["profiles"][0]["bindings"]["4"] = binding("lock_screen")
        config.save(cfg)
        sets = {s["name"]: s for s in json.loads(self.config_path.read_text())["sets"]}
        self.assertIn("4", sets["Coding"]["profiles"][0]["bindings"])
        self.assertNotIn("4", sets["Streaming"]["profiles"][0]["bindings"])

    def test_an_unknown_saved_set_falls_back_to_the_first(self):
        self.write(self.two_sets())
        profile_sets.set_active("Deleted set")
        self.assertEqual(config.load()["active_set"], "Coding")

    def test_hand_edited_sets_are_repaired(self):
        self.write({"sets": [{"name": "A"}, {"name": "a", "profiles": []}, "junk", {"profiles": []}]})
        cfg = config.load()
        self.assertEqual([s["name"] for s in cfg["sets"]], ["A"])
        self.assertEqual(cfg["profiles"][0]["name"], "Default")

    def test_switching_changes_the_config_mtime(self):
        self.write(self.two_sets())
        before = config.mtime()
        profile_sets.set_active("Streaming")
        self.assertNotEqual(before, config.mtime())


class SwitchActionTest(SetsCase):
    def cfg(self):
        data = self.two_sets()
        data["sets"].append({"name": "Gaming", "profiles": [{"name": "Default", "match": "",
                                                             "bindings": {}, "layer_bindings": {}}]})
        self.write(data)
        return config.load()

    def test_switch_by_name_ignoring_case(self):
        cfg = self.cfg()
        self.assertEqual(actions.perform(cfg, {"action": "set_switch", "params": {"name": "streaming"}}), "Set: Streaming")
        self.assertEqual(profile_sets.active_name(), "Streaming")

    def test_unknown_set_is_an_error(self):
        with self.assertRaises(actions.ActionError):
            actions.perform(self.cfg(), {"action": "set_switch", "params": {"name": "Nope"}})

    def test_next_and_previous_wrap_around(self):
        cfg = self.cfg()
        seen = [actions.perform(cfg, {"action": "set_next", "params": {}}) for _ in range(4)]
        self.assertEqual(seen, ["Set: Streaming", "Set: Gaming", "Set: Coding", "Set: Streaming"])
        self.assertEqual(actions.perform(cfg, {"action": "set_previous", "params": {}}), "Set: Coding")
        self.assertEqual(actions.perform(cfg, {"action": "set_previous", "params": {}}), "Set: Gaming")

    def test_next_with_one_set_explains(self):
        self.write({"profiles": [{"name": "Default", "match": "", "bindings": {}, "layer_bindings": {}}]})
        with self.assertRaises(actions.ActionError):
            actions.perform(config.load(), {"action": "set_next", "params": {}})

    def test_a_binding_naming_a_missing_set_is_flagged_before_it_runs(self):
        cfg = self.cfg()
        self.assertEqual(actions.binding_problems({"action": "set_switch", "params": {"name": "Gaming"}}, cfg), [])
        self.assertTrue(actions.binding_problems({"action": "set_switch", "params": {"name": "Nope"}}, cfg))


if __name__ == "__main__":
    unittest.main()
