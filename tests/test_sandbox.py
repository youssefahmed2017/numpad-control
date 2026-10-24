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


if __name__ == "__main__":
    unittest.main()
