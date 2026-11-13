"""Run the whole test suite (CI uses this instead of `unittest discover`, which exited 1 on Windows after a pass)."""
import sys, traceback, unittest

def hook(event, args):
    if event == "sys.exit" and args and args[0] not in (0, None):
        print(f"[diag] sys.exit({args[0]!r}) called from:", file=sys.stderr)
        traceback.print_stack(file=sys.stderr)

sys.addaudithook(hook)
suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(f"[diag] wasSuccessful={result.wasSuccessful()} errors={len(result.errors)} failures={len(result.failures)}", file=sys.stderr)
sys.exit(not result.wasSuccessful())
