"""A first clue for an error: what usually causes it, and the first thing to try.

Many of the actions' own messages already carry one ("ydotool failed - is its service running?", "OBS is not
running or its WebSocket server is disabled"). This is for the generic failures that don't: a program that
didn't answer, a permission error, a missing file, a refused connection. The service adds the clue to the
log line after the error (daemon.py), so the first thing a person reads in the log is where to start.
"""

import errno
import subprocess


def first_clue(error):
    """A short sentence for this error, or None when there is nothing useful to add. `error` is the exception;
    its text is also looked at, because actions wrap the original error in their own message."""
    text = str(error).lower()
    code = getattr(error, "errno", None)
    if isinstance(error, (subprocess.TimeoutExpired, TimeoutError)) or "timed out" in text:
        return "the program did not answer in time: is it hung or very slow? Try the same command by hand in a terminal."
    if isinstance(error, PermissionError) or code in (errno.EACCES, errno.EPERM) or "permission denied" in text:
        return ("permission denied: the service runs as your user, so check that this user may use that file or device "
                "(for the numpad itself, the udev rule: see docs/install.md).")
    if isinstance(error, FileNotFoundError) or "no such file or directory" in text:
        return "a file or program was not found: check the path or name in the action, and that the program is installed."
    if isinstance(error, ConnectionRefusedError) or code == errno.ECONNREFUSED or "connection refused" in text:
        return "nothing is listening there: is the program running, and are the host and the port right?"
    return None
