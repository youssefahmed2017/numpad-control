"""Crash reports: when Numpad Control crashes, ask the user whether to report it, every time.

This is not telemetry. Nothing is ever sent by itself, and nothing is collected while
things work. Only when a part of Numpad Control crashes:

  1. the crash (what failed and where in the code, the version, the OS) is saved to
     <state folder>/crashes/, with your user name and home folder taken out;
  2. a plain system dialog, not Qt (which may be what broke), asks
     "Numpad Control crashed. Do you want to report it?  [Yes] [No]";
  3. Yes opens a pre-filled GitHub issue in the browser, so you read every word before
     choosing to send it; No sends nothing (the file stays, for you to look at).

Each step falls back to the next, so even a crash handler in trouble can't hide a crash:
the dialog runs in its own process (python -m numpadctl.crash FILE); if that can't
start, the crashing process shows it itself; if no dialog can be shown at all (no
desktop, say), the report waits and is asked about when Numpad Control next starts.
The same crash repeating (a service restarted again and again) is asked about once.

Only the standard library is used here, so this still loads when the rest doesn't.
"""

import getpass
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from pathlib import Path

from .platform import IS_WINDOWS, paths

ROOT = Path(__file__).resolve().parent.parent
ISSUE_URL = "https://github.com/youssefahmed2017/numpad-pilot/issues/new"
KEEP_REPORTS = 20          # older crash files are deleted
REPEAT_WINDOW = 3600       # the same crash again within an hour isn't asked about again
ASKING_TIMEOUT = 3600      # a dialog that never answered (its process died) is asked again after this
MAX_ATTEMPTS = 3           # ...but not forever
MAX_TRACEBACK = 5000       # characters of traceback in the issue (browsers cap URL length)
TITLE = "Numpad Control crashed"

_installed = set()


def crashes_dir():
    return paths.state_dir() / "crashes"


def _sanitize(text):
    """Take the home folder and user name out of a report."""
    home = str(Path.home())
    if len(home) > 1:
        text = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if len(user) >= 3:
        text = re.sub(rf"\b{re.escape(user)}\b", "<user>", text)
    return text


def _version():
    """The git commit, read from .git directly (no programs started while crashing)."""
    try:
        head = (ROOT / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            head = (ROOT / ".git" / head[5:]).read_text().strip()
        return head[:7]
    except OSError:
        return "unknown"


def _signature(exc_type, tb_text):
    """Same exception type and same last lines of the traceback = the same crash."""
    tail = "\n".join(line for line in tb_text.splitlines() if line.startswith("  File"))[-600:]
    return hashlib.sha1(f"{exc_type}\n{tail}".encode()).hexdigest()[:12]


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _store(path, report):
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _reports():
    """[(path, report)] of the saved crashes, oldest first."""
    found = []
    for path in crashes_dir().glob("crash-*.json"):
        try:
            found.append((path, _load(path)))
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda item: (item[1].get("time", 0), item[0].name))


def save(component, exc_type, exc, tb):
    """Write the crash to a file; returns (path, should we ask about it)."""
    folder = crashes_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tb_text = _sanitize("".join(traceback.format_exception(exc_type, exc, tb)))
    now = time.time()
    signature = _signature(exc_type.__name__, tb_text)
    repeat = any(r.get("signature") == signature and now - r.get("time", 0) < REPEAT_WINDOW
                 for _, r in _reports())
    report = {
        "component": component, "time": now, "version": _version(),
        "system": platform.platform(), "python": sys.version.split()[0],
        "error": _sanitize(f"{exc_type.__name__}: {exc}")[:300], "traceback": tb_text,
        "signature": signature, "state": "repeat" if repeat else "pending", "attempts": 0,
    }
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    n = 1
    while (path := folder / f"crash-{stamp}-{n}-{component}.json").exists():
        n += 1
    _store(path, report)
    for old, _ in _reports()[:-KEEP_REPORTS]:
        old.unlink(missing_ok=True)
    return path, not repeat


def report(component, exc_info=None):
    """Save the crash being handled (or exc_info) and ask about it. Never raises."""
    try:
        exc_type, exc, tb = exc_info or sys.exc_info()
        if exc_type is None or issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            return
        path, ask_now = save(component, exc_type, exc, tb)
        if not ask_now:
            return
        try:
            _spawn_dialog(path)
        except Exception:  # can't start a process: ask from here
            ask(path)
    except BaseException:
        try:  # the last resort: at least the log / terminal gets it
            sys.__stderr__.write("numpad-control: the crash handler failed too:\n" + traceback.format_exc())
        except Exception:
            pass


def _spawn_dialog(path):
    """Ask in a separate process, which keeps running if this one goes away."""
    python = Path(sys.executable)
    if IS_WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")  # no console window
    argv = [str(python), "-m", "numpadctl.crash", str(path)]
    if IS_WINDOWS:
        subprocess.Popen(argv, cwd=ROOT, creationflags=0x00000008 | 0x00000200,  # detached, own group
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return
    import shutil
    if os.environ.get("INVOCATION_ID") and shutil.which("systemd-run"):
        # Under systemd: its own scope, so restarting the crashed service doesn't close the dialog.
        argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--", *argv]
    subprocess.Popen(argv, cwd=ROOT, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _message(report):
    return (f"Numpad Control's {report.get('component', 'program')} crashed:\n\n"
            f"{report.get('error', '')}\n\n"
            "Do you want to report it?\n\n"
            "Yes opens a GitHub issue in your browser with the details, for you to read "
            "before sending. Nothing is sent unless you choose to.")


def issue_url(report):
    tb_text = report.get("traceback", "")
    if len(tb_text) > MAX_TRACEBACK:
        tb_text = "…\n" + tb_text[-MAX_TRACEBACK:]
    body = (f"**What I was doing when it crashed:**\n\n\n\n"
            f"---\n"
            f"Crash report (sent by me, from the crash dialog)\n\n"
            f"- Part: {report.get('component')}\n- Version: {report.get('version')}\n"
            f"- System: {report.get('system')}, Python {report.get('python')}\n\n"
            f"```\n{tb_text}```\n")
    title = f"Crash: {report.get('error', '')}"[:120]
    return f"{ISSUE_URL}?{urllib.parse.urlencode({'title': title, 'body': body, 'labels': 'crash'})}"


def _dialog(text):
    """Yes -> True, No -> False, couldn't show a dialog -> None. Plain system dialogs only."""
    if IS_WINDOWS:
        import ctypes
        MB_YESNO, MB_ICONERROR, MB_SETFOREGROUND, MB_TOPMOST, IDYES = 0x4, 0x10, 0x10000, 0x40000, 6
        answer = ctypes.windll.user32.MessageBoxW(None, text, TITLE,
                                                  MB_YESNO | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST)
        return None if answer == 0 else answer == IDYES
    _find_display()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    import shutil
    choices = [["zenity", "--question", "--title", TITLE, "--text", text, "--ok-label", "Yes",
                "--cancel-label", "No", "--width", "420"],
               ["kdialog", "--title", TITLE, "--yesno", text],
               ["xmessage", "-center", "-buttons", "Yes:0,No:1", "-default", "Yes", _wrap(text)]]
    for argv in choices:
        if shutil.which(argv[0]):
            try:
                code = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
            except OSError:
                continue
            return code == 0
    return None


def _wrap(text, width=64):
    """xmessage doesn't wrap lines itself."""
    import textwrap
    return "\n".join(textwrap.fill(line, width) if line else "" for line in text.split("\n"))


def _find_display():
    """A service started before the desktop doesn't know the display yet: ask systemd."""
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return
    try:
        out = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True,
                             text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return
    for line in out.splitlines():
        name, _, value = line.partition("=")
        if name in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS") \
                and value:
            os.environ.setdefault(name, value)


def ask(path):
    """Show the dialog for one saved crash and remember the answer."""
    report = _load(path)
    if report.get("state") not in ("pending", "asking"):
        return
    report["attempts"] = report.get("attempts", 0) + 1
    if report["attempts"] > MAX_ATTEMPTS:
        report["state"] = "gave up"
        _store(path, report)
        return
    report.update(state="asking", asking_since=time.time())
    _store(path, report)
    answer = _dialog(_message(report))
    if answer is None:
        report["state"] = "pending"  # no desktop to ask on: ask at the next start
    elif answer:
        webbrowser.open(issue_url(report))
        report["state"] = "reported"
    else:
        report["state"] = "declined"
    _store(path, report)


def ask_pending():
    """At start: ask about the latest crash nobody could be asked about yet (in the background)."""
    now = time.time()
    waiting = [path for path, r in _reports()
               if r.get("state") == "pending"
               or (r.get("state") == "asking" and now - r.get("asking_since", 0) > ASKING_TIMEOUT)]
    if not waiting:
        return
    for older in waiting[:-1]:  # one question is enough: older ones are only kept as files
        older_report = _load(older)
        older_report["state"] = "skipped"
        _store(older, older_report)
    try:
        _spawn_dialog(waiting[-1])
    except Exception:
        threading.Thread(target=ask, args=(waiting[-1],), daemon=True).start()


def install(component):
    """Report uncaught exceptions of this process (any thread) as crashes of `component`."""
    if component in _installed:
        return
    _installed.add(component)
    previous_hook, previous_thread_hook = sys.excepthook, threading.excepthook

    def hook(exc_type, exc, tb):
        report(component, (exc_type, exc, tb))
        previous_hook(exc_type, exc, tb)

    def thread_hook(args):
        report(component, (args.exc_type, args.exc_value, args.exc_traceback))
        previous_thread_hook(args)

    sys.excepthook, threading.excepthook = hook, thread_hook
    try:
        ask_pending()
    except Exception:
        pass


def main(argv):
    """python -m numpadctl.crash FILE: the dialog process."""
    if len(argv) != 1:
        sys.exit("usage: python -m numpadctl.crash CRASH_FILE")
    try:
        ask(argv[0])
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
