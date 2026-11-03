"""Where the numpad's keys are drawn: the layouts agree on the keys, don't overlap, and the setting picks one."""

import unittest

from numpadctl import config, ui_common


def cells(layout):
    taken = []
    for key, row, column, span in layout:
        taken += [(row + r, column) for r in range(span)]
    return taken


class NumpadLayoutsTest(unittest.TestCase):
    def test_every_layout_has_the_same_nineteen_keys(self):
        standard = sorted(key for key, *_ in ui_common.LAYOUT)
        self.assertEqual(len(standard), 19)
        for name, (_, layout) in ui_common.LAYOUTS.items():
            self.assertEqual(sorted(key for key, *_ in layout), standard, name)

    def test_no_two_keys_share_a_cell_and_the_grid_is_five_by_four(self):
        for name, (_, layout) in ui_common.LAYOUTS.items():
            taken = cells(layout)
            self.assertEqual(len(taken), len(set(taken)), name)
            self.assertEqual((max(r for r, _ in taken), max(c for _, c in taken)), (4, 3), name)

    def test_the_standard_layout_is_the_default(self):
        self.assertEqual(config.DEFAULT_CONFIG["numpad_layout"], "standard")
        self.assertIs(ui_common.layout_for({}), ui_common.LAYOUT)

    def test_an_unknown_layout_falls_back_to_the_standard_one(self):
        self.assertIs(ui_common.layout_for({"numpad_layout": "nonsense"}), ui_common.LAYOUT)

    def test_backspace_below_puts_minus_plus_backspace_down_the_right_hand_column(self):
        placed = {key: (row, column) for key, row, column, _ in ui_common.layout_for({"numpad_layout": "backspace_below"})}
        self.assertEqual([placed[k] for k in ("-", "+", "Backspace")], [(0, 3), (1, 3), (2, 3)])
        standard = {key: (row, column) for key, row, column, _ in ui_common.LAYOUT}
        self.assertEqual([standard[k] for k in ("Backspace", "-", "+")], [(0, 3), (1, 3), (2, 3)])


if __name__ == "__main__":
    unittest.main()
