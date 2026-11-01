import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("the sandbox is Linux-only (Run Python is off on Windows)")

import unittest

from numpadctl import sandbox

ESCAPES = {
    "eval": "eval('1')",
    "exec": "exec('1')",
    "import os": "import os",
    "from os": "from os import system",
    "subprocess": "import subprocess",
    "importlib": "import importlib",
    "dunder": "().__class__.__base__.__subclasses__()",
    "gi_frame": "g = (x for x in [1])\ng.gi_frame.f_back",
    "format": "'{0.__class__}'.format(1)",
    "match": "match 1:\n    case int(__class__=c): pass",
    "class": "class A: pass",
    "open": "open('/etc/passwd')",
    "builtins": "__builtins__",
    "getattr": "getattr(1, 'real')",
    "relative import": "from . import x",
    "math dunder": "from math import __loader__",
}


class SandboxTest(unittest.TestCase):
    def test_escapes_are_rejected_statically(self):
        for name, code in ESCAPES.items():
            with self.subTest(name):
                self.assertTrue(sandbox.validate(code), f"{name} was allowed")

    def test_webbrowser_has_no_os(self):
        ok, out = sandbox.run("import webbrowser\nwebbrowser.os.system('id')")
        self.assertFalse(ok)
        self.assertIn("AttributeError", out)

    def test_allowed_snippet_and_url_filter(self):
        opened = []
        ok, out = sandbox.run(
            "import math\nprint(math.sqrt(16))\n"
            "open_url('https://example.com')\nopen_url('file:///etc/passwd')",
            on_open_url=opened.append, on_notify=lambda *a: None)
        self.assertTrue(ok, out)
        self.assertEqual(out, "4.0")
        self.assertEqual(opened, ["https://example.com"])

    def test_memory_bomb_is_stopped(self):
        ok, out = sandbox.run("x = 'a' * (10**10)")
        self.assertFalse(ok)
        self.assertIn("MemoryError", out)

    # Found by attacking the sandbox: a loop could print until the service ran out of
    # memory, or ask for a million URLs / notifications.
    def test_endless_output_is_stopped(self):
        ok, out = sandbox.run("while True:\n    print('x' * 100000)\n")
        self.assertFalse(ok)
        self.assertIn("printed more than", out)

    def test_a_loop_cannot_open_more_than_a_few_urls(self):
        opened = []
        ok, out = sandbox.run("while True:\n    open_url('https://example.com')\n",
                              on_open_url=opened.append, on_notify=lambda *a: None)
        self.assertFalse(ok)
        self.assertIn("more than", out)
        self.assertLessEqual(len(opened), sandbox.MAX_REQUESTS)

    def test_a_loop_cannot_flood_notifications(self):
        notes = []
        ok, _ = sandbox.run("while True:\n    notify('hi', 'there')\n",
                            on_open_url=lambda u: None, on_notify=lambda *a: notes.append(a))
        self.assertFalse(ok)
        self.assertLessEqual(len(notes), sandbox.MAX_REQUESTS)

    def test_an_oversized_request_is_stopped(self):
        notes = []
        ok, out = sandbox.run("notify('a' * 200000, 'b')", on_open_url=lambda u: None,
                              on_notify=lambda *a: notes.append(a))
        self.assertFalse(ok)
        self.assertEqual(notes, [])
        self.assertIn("too large", out)

    def test_normal_use_still_fits_in_the_limits(self):
        notes = []
        ok, out = sandbox.run("for i in range(5):\n    pass\nnotify('done', 'ok')\nprint('hello')",
                              on_open_url=lambda u: None, on_notify=lambda *a: notes.append(a))
        self.assertTrue(ok, out)
        self.assertEqual(out, "hello")
        self.assertEqual(notes, [("done", "ok")])

    def test_notification_text_is_never_an_option(self):
        from unittest import mock
        with mock.patch("subprocess.run") as run:
            sandbox._default_notify("--hint=string:x:y", "body")
        self.assertEqual(run.call_args.args[0], ["notify-send", "-a", "NumpadPilot", "--", "--hint=string:x:y", "body"])


if __name__ == "__main__":
    unittest.main()
