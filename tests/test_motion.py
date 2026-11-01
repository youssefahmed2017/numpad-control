"""numpadctl_ui/motion.py: Material 3's curves, durations and springs behave the way the spec's numbers say."""

import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QVariantAnimation

from numpadctl_ui import motion

APP = QCoreApplication.instance() or QCoreApplication([])


class EasingTest(unittest.TestCase):
    def test_every_curve_starts_at_0_ends_at_1_and_never_goes_backwards(self):
        for name in motion.EASINGS:
            curve = motion.ease(name)
            values = [curve(i / 100) for i in range(101)]
            self.assertAlmostEqual(values[0], 0.0, places=3, msg=name)
            self.assertAlmostEqual(values[-1], 1.0, places=3, msg=name)
            for a, b in zip(values, values[1:]):
                self.assertLessEqual(a, b + 1e-6, f"{name} went backwards")

    def test_decelerate_curves_arrive_early_and_accelerate_curves_leave_late(self):
        for name in ("standard", "standard_decelerate", "emphasized_decelerate", "emphasized"):
            self.assertGreater(motion.ease(name)(0.3), 0.5, name)
        for name in ("standard_accelerate", "emphasized_accelerate"):
            self.assertLess(motion.ease(name)(0.5), 0.5, name)

    def test_emphasized_is_the_two_part_path_from_the_spec(self):
        first, second = motion.bezier_points("emphasized")
        self.assertEqual(first[4:], (0.166666, 0.4))  # a quick start: 40 % done after a sixth of the time
        self.assertEqual(second[4:], (1.0, 1.0))
        self.assertGreater(motion.ease("emphasized")(0.2), 0.5)

    def test_the_standard_curve_matches_the_known_cubic(self):
        # cubic-bezier(0.2, 0, 0, 1) at t = 0.5: solving x(s) = 0.5 gives s = 0.782 and y = 0.878 (a strong ease-out)
        self.assertAlmostEqual(motion.ease("standard")(0.5), 0.878, delta=0.005)

    def test_duration_tokens_are_the_published_steps(self):
        self.assertEqual((motion.SHORT1, motion.SHORT4, motion.MEDIUM1, motion.MEDIUM4, motion.LONG1, motion.LONG4,
                          motion.EXTRA_LONG1, motion.EXTRA_LONG4), (50, 200, 250, 400, 450, 600, 700, 1000))


class SpringTest(unittest.TestCase):
    def test_a_spring_starts_at_rest_and_ends_at_its_target(self):
        for name, (damping, stiffness) in motion.SPRINGS.items():
            self.assertEqual(motion.spring_value(damping, stiffness, 0), 0.0)
            self.assertAlmostEqual(motion.spring_value(damping, stiffness, 10), 1.0, places=6, msg=name)

    def test_effects_springs_never_overshoot_and_spatial_ones_do_a_little(self):
        for name, (damping, stiffness) in motion.SPRINGS.items():
            peak = max(motion.spring_value(damping, stiffness, i / 1000) for i in range(0, 3000, 2))
            if name.endswith("effects"):
                self.assertLessEqual(peak, 1.0 + 1e-9, name)
            else:
                self.assertGreater(peak, 1.0, name)
                self.assertAlmostEqual(peak - 1.0, motion.overshoot(damping), delta=0.002, msg=name)

    def test_the_expressive_fast_spring_overshoots_by_the_textbook_amount(self):
        self.assertAlmostEqual(motion.overshoot(0.6), math.exp(-math.pi * 0.6 / 0.8), places=9)  # about 9.5 %
        self.assertAlmostEqual(motion.overshoot(0.8), 0.0152, delta=0.001)

    def test_stiffer_springs_settle_sooner(self):
        fast = motion.spring_duration(*motion.SPRINGS["fast_effects"])
        default = motion.spring_duration(*motion.SPRINGS["default_effects"])
        slow = motion.spring_duration(*motion.SPRINGS["slow_effects"])
        self.assertLess(fast, default)
        self.assertLess(default, slow)
        self.assertLess(slow, 700, "an effects spring is a quick fade, not a slow one")
        self.assertLess(motion.spring_duration(*motion.SPRINGS["fast_spatial"]),
                        motion.spring_duration(*motion.SPRINGS["slow_spatial"]))

    def test_over_damped_springs_work_too(self):
        self.assertAlmostEqual(motion.spring_value(1.5, 500, 10), 1.0, places=6)
        self.assertLess(max(motion.spring_value(1.5, 500, i / 100) for i in range(300)), 1.0 + 1e-9)

    def test_a_spring_moves_a_value_from_start_to_end_and_can_overshoot(self):
        seen = []
        spring = motion.Spring(None, "fast_spatial", seen.append)
        spring.go(0.0, 10.0)
        self.assertEqual(spring.duration, motion.spring_duration(*motion.SPRINGS["fast_spatial"]))
        for ms in range(0, spring.duration, 5):
            spring.set_time(ms)
        spring.set_time(spring.duration)
        self.assertAlmostEqual(seen[-1], 10.0, places=6)
        self.assertGreater(max(seen), 10.0, "a spatial spring springs past its target before it settles")
        self.assertAlmostEqual(max(seen) / 10 - 1, motion.overshoot(0.6), delta=0.01)

    def test_an_effects_spring_never_passes_its_target(self):
        seen = []
        spring = motion.Spring(None, "default_effects", seen.append)
        spring.go(1.0, 0.0)  # falling, like a hover fading out
        for ms in range(0, spring.duration + 1, 4):
            spring.set_time(ms)
        self.assertGreaterEqual(min(seen), -1e-9)
        self.assertAlmostEqual(seen[-1], 0.0, places=6)

    def test_retargeting_in_mid_flight_starts_from_where_it_is(self):
        seen = []
        spring = motion.Spring(None, "slow_effects", seen.append)
        spring.go(0.0, 1.0)
        spring.set_time(spring.duration // 3)
        midway = seen[-1]
        self.assertTrue(0.05 < midway < 0.95)
        spring.go(midway, 0.0)
        spring.set_time(spring.duration)
        self.assertAlmostEqual(seen[-1], 0.0, places=6)

    def test_the_spring_can_be_swapped_for_another_one(self):
        spring = motion.Spring(None, "fast_effects", lambda v: None)
        quick = spring.duration
        spring.set_spring("slow_spatial")
        self.assertGreater(spring.duration, quick)

    def test_a_tween_follows_its_curve_for_its_duration(self):
        seen = []
        tween = motion.Tween(None, motion.MEDIUM2, "emphasized_decelerate", seen.append)
        tween.go(10.0, 20.0)
        self.assertEqual(tween.duration, 300)
        tween.set_time(0)
        tween.set_time(90)
        self.assertAlmostEqual(seen[-1], 10 + 10 * motion.ease("emphasized_decelerate")(0.3), places=6)
        tween.set_time(300)
        self.assertAlmostEqual(seen[-1], 20.0, places=6)


if __name__ == "__main__":
    unittest.main()
