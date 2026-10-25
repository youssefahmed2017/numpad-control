"""Starter presets are valid, only use real keys, and never overwrite."""

import unittest

from numpadctl import actions, presets, ui_common


def b(action, **params):
    return {"action": action, "params": params}


class PresetsTest(unittest.TestCase):
    def test_every_preset_is_valid(self):
        real_keys = {key for key, *_ in ui_common.LAYOUT}
        for preset in presets.PRESETS:
            keymap = {}
            presets.apply(preset, keymap)
            self.assertTrue(keymap, preset.name)
            for key, slots in keymap.items():
                self.assertIn(key, real_keys, f"{preset.name}: {key}")
                for slot, binding in slots.items():
                    self.assertEqual(actions.binding_problems(binding), [], f"{preset.name} {key} {slot}")

    def test_existing_keys_are_kept(self):
        keymap = {"5": {"tap": b("open_url", url="https://example.com")}, "4": {"tap": b("none")}}
        added, kept = presets.apply(presets.BY_NAME["Media and volume"], keymap)
        self.assertEqual(keymap["5"]["tap"]["action"], "open_url")
        self.assertEqual(keymap["4"]["tap"]["action"], "volume_down", "an empty (none) key is filled")
        self.assertEqual(kept, 1)
        self.assertGreater(added, 5)

    def test_second_apply_adds_nothing(self):
        keymap = {}
        presets.apply(presets.BY_NAME["Editing"], keymap)
        self.assertEqual(presets.apply(presets.BY_NAME["Editing"], keymap)[0], 0)

    def test_default_params_are_filled(self):
        self.assertEqual(presets.binding("press_keys", {})["params"], {"keys": "Enter"})
        self.assertEqual(presets.binding("press_keys", {"keys": "ctrl+c"})["params"], {"keys": "ctrl+c"})


if __name__ == "__main__":
    unittest.main()
