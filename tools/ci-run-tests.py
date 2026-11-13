"""Run the whole test suite for CI and leave with the right exit code.

`unittest discover` can crash (exit 1 on Windows, a segfault on Linux) while Python tears Qt down
after every test has passed. The results are what matters, so this prints them, flushes and exits
without the teardown.
"""
import os
import sys
import unittest

suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.stdout.flush()
sys.stderr.flush()
os._exit(0 if result.wasSuccessful() else 1)
