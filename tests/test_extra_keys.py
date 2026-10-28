"""Keys beyond the standard numpad: names, the "00" burst and the unknown flag (the window is in the app)."""

import asyncio
import unittest
from unittest import mock

from numpadctl import config, keys


class KeysTest(unittest.TestCase):
    def test_default_names(self):
        self.assertEqual(keys.label_for("KEY_TAB"), "Tab")
        self.assertEqual(keys.label_for("KEY_KPLEFTPAREN"), "(")
        self.assertEqual(keys.label_for("KEY_F13"), "F13")
        self.assertEqual(keys.label_for("KEY_PROG1"), "Prog1")
        self.assertEqual(keys.label_for("SC_0F"), "Tab")
        self.assertEqual(keys.label_for("SC_E0_1D"), "Key E0 1D")
        self.assertEqual(keys.label_for("5"), "5")

    def test_known_and_display(self):
        cfg = {"extra_keys": [{"id": "KEY_TAB", "label": "Switch"}]}
        self.assertTrue(keys.known("5", cfg) and keys.known("KEY_TAB", cfg))
        self.assertFalse(keys.known("KEY_F13", cfg))
        self.assertEqual(keys.display("KEY_TAB", cfg), "Switch")
        self.assertEqual(keys.display("KEY_F13", cfg), "F13")

    def test_default_config_has_no_extra_keys(self):
        self.assertEqual(config.DEFAULT_CONFIG["extra_keys"], [])


class DaemonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from numpadctl import daemon
        from tests.test_daemon import make_cfg
        patch = mock.patch.object(daemon.Daemon, "reload_if_changed", lambda self: None)
        patch.start()
        self.addCleanup(patch.stop)
        self.fired = []
        self.d = daemon.Daemon(run_action=lambda key, binding, slot: self.fired.append(key))
        self.d.cfg = make_cfg({})
        self.keys = []
        self.d.key_event = lambda key, down: self.keys.append((key, down))

    async def burst(self, count):
        for _ in range(count):
            self.d.on_key("0", True)
            self.d.on_key("0", False)
        await asyncio.sleep(0.15)

    async def test_two_zeros_stay_two_zeros_unless_a_00_key_was_added(self):
        await self.burst(2)
        self.assertEqual(self.keys, [("0", True), ("0", False)] * 2)

    async def test_two_zeros_are_the_00_key_once_added(self):
        self.d.cfg["extra_keys"] = [{"id": "00", "label": "00"}]
        await self.burst(2)
        self.assertEqual(self.keys, [("00", True), ("00", False)])

    async def test_two_zeros_are_00_while_learning_and_three_are_still_000(self):
        self.d.capturing.add(object())
        await self.burst(2)
        self.assertEqual(self.keys[0], ("00", True))
        self.keys.clear()
        await self.burst(3)
        self.assertEqual(self.keys, [("000", True), ("000", False)])

    async def test_five_zeros_are_000_and_00_when_wanted(self):
        self.d.cfg["extra_keys"] = [{"id": "00", "label": "00"}]
        await self.burst(5)
        self.assertEqual(self.keys, [("000", True), ("000", False), ("00", True), ("00", False)])

    async def test_key_event_says_when_a_key_is_unknown(self):
        from numpadctl import daemon
        d = daemon.Daemon(run_action=lambda *a: None)
        d.cfg["extra_keys"] = [{"id": "KEY_TAB", "label": "Tab"}]
        sent = []
        d.broadcast = sent.append
        for key in ("5", "KEY_TAB", "KEY_F13"):
            d.key_event(key, True)
        self.assertEqual([(m["key"], m["unknown"]) for m in sent], [("5", False), ("KEY_TAB", False), ("KEY_F13", True)])
        self.assertEqual(sent[2]["label"], "F13")


if __name__ == "__main__":
    unittest.main()
