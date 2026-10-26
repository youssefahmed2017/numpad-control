"""The guided numpad test (numpad-control check): how it judges what a numpad sends."""

import asyncio
import unittest
from unittest import mock

from numpadctl import check


class JudgeTest(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(check.judge_key("5", [("5", True, 0), ("5", False, 0.1)]), "ok")
        self.assertEqual(check.judge_key("5", []), "missing")
        self.assertEqual(check.judge_key("/", [("*", True, 0)]), "sent *")

    def test_hold(self):
        self.assertEqual(check.judge_hold([("5", True, 0), ("5", False, 2)]), "ok")
        self.assertEqual(check.judge_hold([("5", True, 0)] * 3 + [("5", False, 2)]), "3 presses for one hold")

    def test_000(self):
        burst = [("0", True, 0.0), ("0", True, 0.01), ("0", True, 0.02)]
        self.assertEqual(check.judge_000(burst), "ok")
        self.assertIn("too slow", check.judge_000([("0", True, 0.0), ("0", True, 0.2), ("0", True, 0.4)]))
        self.assertIn("no 000 key", check.judge_000([("0", True, 0.0)]))
        self.assertEqual(check.judge_000([]), "missing")

    def test_summary_row(self):
        results = {k: "ok" for k in check.KEYS}
        results.update({"Backspace": "missing", "hold": "ok", "000": "missing"})
        good, row, wrong = check.summary({"vendor": "c0f4", "product": "05f5"}, results, "Acme Pad")
        self.assertTrue(good)
        self.assertEqual(wrong, [])
        self.assertTrue(row.startswith("| Acme Pad | c0f4:05f5 |"))
        self.assertIn(f"| {len(check.KEYS) - 1}/{len(check.KEYS)} | Backspace |", row)

    def test_a_key_sending_another_is_a_problem(self):
        results = {k: "ok" for k in check.KEYS}
        results.update({"/": "sent *", "hold": "ok", "000": "ok"})
        good, row, wrong = check.summary({"vendor": "1", "product": "2"}, results, "X")
        self.assertFalse(good)
        self.assertEqual(wrong, ["/ (sent *)"])


class ScriptedNumpad:
    """Presses each key when asked (except Backspace, which this model lacks)."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def events(self):
        while True:
            yield await self.queue.get()


class RunChecksTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_whole_run(self):
        numpad = ScriptedNumpad()
        lines = []

        def say(*parts, **_):
            text = " ".join(str(p) for p in parts)
            lines.append(text)
            if "Press  000" in text:
                for _ in range(3):
                    numpad.queue.put_nowait(("0", True))
            elif "Hold 5" in text:
                numpad.queue.put_nowait(("5", True))
                numpad.queue.put_nowait(("5", False))
            elif text.startswith("  Press") and "Backspace" not in text:
                key = text.split()[1]
                numpad.queue.put_nowait((key, True))
                numpad.queue.put_nowait((key, False))

        with mock.patch.object(check, "KEY_WAIT", 0.2), mock.patch.object(check, "SETTLE", 0.03), \
                mock.patch.object(check, "HOLD_SECONDS", 0):
            results = await check.run_checks(numpad, say=say)
        self.assertEqual(results["Backspace"], "missing")
        self.assertEqual(results["5"], "ok")
        self.assertEqual(results["hold"], "ok")
        self.assertEqual(results["000"], "ok")
        self.assertEqual({k: v for k, v in results.items() if v != "ok"}, {"Backspace": "missing"})


class MainTest(unittest.TestCase):
    def test_refuses_while_the_service_holds_the_numpad(self):
        said = []
        with mock.patch.object(check, "service_running", lambda: True):
            self.assertEqual(check.main(ask=lambda q: "", say=said.append), 1)
        self.assertIn("Stop it first", said[0])


if __name__ == "__main__":
    unittest.main()
