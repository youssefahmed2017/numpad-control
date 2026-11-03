"""Exporting a profile to a file and importing one: careful with what comes from outside."""

import copy
import json
import unittest

from numpadctl import config, profile_io


def b(action, **params):
    return {"action": action, "params": params}


PROFILE = {"name": "Streaming", "match": "obs",
           "bindings": {"1": {"tap": b("open_browser", url="https://example.org"), "hold": b("media_next")},
                        "8": {"tap": {"action": "volume_up", "params": {}, "turbo": 20}},
                        "KEY_TAB": {"double": b("mic_mute")}},
           "layer_bindings": {"2": {"tap": b("lock_screen")}}}


def file_for(profile=None, **changes):
    data = profile_io.export_profile(profile or PROFILE, "0.3.0")
    data.update(changes)
    return json.dumps(data)


class ExportTest(unittest.TestCase):
    def test_a_profile_survives_the_round_trip(self):
        profile, dropped = profile_io.parse(profile_io.dumps(profile_io.export_profile(PROFILE, "0.3.0")))
        self.assertEqual(profile, PROFILE)
        self.assertEqual(dropped, [])

    def test_export_is_a_copy_and_has_only_the_profile(self):
        original = copy.deepcopy(PROFILE)
        data = profile_io.export_profile(PROFILE, "0.3.0")
        data["profile"]["bindings"]["1"]["tap"]["params"]["url"] = "changed"
        self.assertEqual(PROFILE, original)
        self.assertEqual(sorted(data), ["app_version", "format", "profile", "version"])
        self.assertEqual(sorted(data["profile"]), ["bindings", "layer_bindings", "match", "name"])

    def test_the_file_is_readable_text(self):
        text = profile_io.dumps(profile_io.export_profile(PROFILE, "0.3.0"))
        self.assertIn('"format": "numpadcontrol-profile"', text)
        self.assertTrue(text.endswith("\n"))


class ImportRefusesTest(unittest.TestCase):
    def refused(self, text, words):
        with self.assertRaisesRegex(profile_io.ProfileFileError, words):
            profile_io.parse(text)

    def test_not_json_or_not_ours(self):
        self.refused("hello", "isn't valid JSON")
        self.refused("[1, 2]", "isn't a NumpadControl profile")
        self.refused(json.dumps({"format": "something-else", "version": 1}), "isn't a NumpadControl profile")

    def test_a_file_from_a_newer_version(self):
        self.refused(file_for(version=2), "newer NumpadControl")

    def test_bad_version_numbers(self):
        for version in (0, -1, "1", None, True):
            self.refused(file_for(version=version), "version")

    def test_too_big(self):
        self.refused(" " * (profile_io.MAX_BYTES + 1), "too big")

    def test_no_profile_or_no_name(self):
        self.refused(json.dumps({"format": profile_io.FORMAT, "version": 1}), "no profile")
        self.refused(file_for(profile={**PROFILE, "name": "  "}), "no name")
        self.refused(file_for(profile={**PROFILE, "name": 5}), "name")

    def test_keys_that_are_not_a_dict(self):
        self.refused(file_for(profile={**PROFILE, "bindings": ["1"]}), "isn't a list of keys")

    def test_far_too_many_keys(self):
        many = {str(i): {"tap": b("mic_mute")} for i in range(profile_io.MAX_KEYS + 1)}
        self.refused(file_for(profile={**PROFILE, "bindings": many}), "more than a numpad has")

    def test_deeply_nested_json_does_not_crash(self):
        self.refused("[" * 100000, "isn't valid JSON")


class ImportCleansTest(unittest.TestCase):
    def parse_bindings(self, bindings):
        return profile_io.parse(file_for(profile={**PROFILE, "bindings": bindings, "layer_bindings": {}}))

    def test_unknown_actions_slots_and_junk_are_dropped_and_reported(self):
        profile, dropped = self.parse_bindings({
            "1": {"tap": b("mic_mute"), "triple": b("mic_mute")},
            "2": {"tap": {"action": "launch_missiles", "params": {}}},
            "3": "not a dict", "4": {"tap": "not a dict"}, "": {"tap": b("mic_mute")}})
        self.assertEqual(profile["bindings"], {"1": {"tap": b("mic_mute")}})
        self.assertEqual(len(dropped), 5)
        self.assertTrue(any("unknown action" in d for d in dropped))
        self.assertTrue(any("unknown slot" in d for d in dropped))

    def test_only_known_fields_are_kept_and_checked(self):
        profile, _ = self.parse_bindings({"1": {"tap": {"action": "volume_up", "params": {}, "rapid": True, "turbo": 20,
                                                          "evil": "x", "__class__": 1}},
                                          "2": {"tap": {"action": "volume_up", "params": {}, "turbo": 9999, "rapid": "yes"}}})
        self.assertEqual(profile["bindings"]["1"]["tap"], {"action": "volume_up", "params": {}, "rapid": True, "turbo": 20})
        self.assertEqual(profile["bindings"]["2"]["tap"], {"action": "volume_up", "params": {}})

    def test_settings_that_are_not_plain_json_values_are_dropped(self):
        profile, dropped = self.parse_bindings({"1": {"tap": {"action": "open_url", "params": ["x"]}},
                                                "2": {"tap": {"action": "type_text", "params": {"text": "x" * (profile_io.MAX_STRING + 1)}}}})
        self.assertEqual(profile["bindings"], {})
        self.assertEqual(len(dropped), 2)

    def test_an_action_with_bad_settings_is_dropped(self):
        profile, dropped = self.parse_bindings({"1": {"tap": b("go_to_workspace", workspace="banana")},
                                                "2": {"tap": b("mic_mute")}})
        self.assertEqual(sorted(profile["bindings"]), ["2"])
        self.assertEqual(len(dropped), 1)

    def test_a_macro_is_checked_inside_too(self):
        good = b("macro", steps=[b("wait", seconds="1"), b("mic_mute")])
        bad = b("macro", steps=[b("wait", seconds="1"), b("launch_missiles")])
        profile, dropped = self.parse_bindings({"1": {"tap": good}, "2": {"tap": bad}})
        self.assertEqual(sorted(profile["bindings"]), ["1"])
        self.assertEqual(len(dropped), 1)

    def test_names_are_trimmed_and_control_characters_removed(self):
        profile, _ = profile_io.parse(file_for(profile={**PROFILE, "name": "  A\x00B\nC  " + "z" * 100, "match": "o\x07bs"}))
        self.assertEqual(len(profile["name"]), profile_io.MAX_NAME)
        self.assertTrue(profile["name"].startswith("A B C"))
        self.assertEqual(profile["match"], "o bs")

    def test_a_missing_layer_section_is_fine(self):
        data = profile_io.export_profile(PROFILE, "0.3.0")
        del data["profile"]["layer_bindings"]
        profile, _ = profile_io.parse(json.dumps(data))
        self.assertEqual(profile["layer_bindings"], {})


class HelpersTest(unittest.TestCase):
    def test_unique_name(self):
        self.assertEqual(profile_io.unique_name("Games", ["Default"]), "Games")
        self.assertEqual(profile_io.unique_name("Games", ["Default", "games"]), "Games (2)")
        self.assertEqual(profile_io.unique_name("Games", ["Games", "Games (2)"]), "Games (3)")

    def test_summary_counts_actions_and_puts_the_risky_ones_first(self):
        macro = b("macro", steps=[b("press_keys", keys="ctrl+c"), b("mic_mute")])
        profile = {"bindings": {"1": {"tap": macro, "hold": b("mic_mute")}, "2": {"tap": b("shutdown")}},
                   "layer_bindings": {"3": {"tap": b("mic_mute")}}}
        rows = {label: (n, risky) for label, n, risky in profile_io.summary(profile)}
        self.assertEqual(rows["Mute / unmute microphone"], (3, False))
        self.assertTrue(rows["Shut down (press twice)"][1])
        self.assertTrue(rows["Macro"][1])
        self.assertTrue(rows["Press keys"][1])
        self.assertTrue(profile_io.summary(profile)[0][2])   # a risky one comes first
        self.assertEqual(profile_io.key_count(profile), 3)

    def test_default_config_profile_exports_and_imports(self):
        profile, dropped = profile_io.parse(profile_io.dumps(profile_io.export_profile(config.DEFAULT_CONFIG["profiles"][0])))
        self.assertEqual((profile["name"], dropped), ("Default", []))


if __name__ == "__main__":
    unittest.main()
