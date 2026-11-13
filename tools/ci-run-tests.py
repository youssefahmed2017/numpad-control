"""Run the whole test suite for CI and leave with the right exit code.

`unittest discover` can crash while the process shuts down, after every test has passed: a segfault on Linux
while Qt is torn down, and an access violation on Windows while Windows unloads the keyboard hook DLL that
tests/test_windows_rawinput.py really loads (faulthandler showed it inside the exit call). The results are
what matters, so this prints them, flushes and ends the process without that teardown (on Windows with
TerminateProcess, which doesn't run the DLLs' detach code).
"""
import os
import sys
import unittest

suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.stdout.flush()
sys.stderr.flush()
code = 0 if result.wasSuccessful() else 1
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.TerminateProcess(ctypes.c_void_p(kernel32.GetCurrentProcess()), code)
os._exit(code)
