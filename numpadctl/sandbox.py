"""Restricted runner for user-written "Run Python" snippets.

Defence in depth:
  1. Static AST check: rejects eval/exec/compile/open, any non-whitelisted
     import (os, sys, subprocess, ...), dunder / frame-introspection attribute
     access, class definitions, async code.
  2. Runtime: snippet runs with a minimal __builtins__ and only gets *proxies*
     of whitelisted modules exposing a fixed set of functions (so e.g.
     `webbrowser.os` does not exist).
  3. Process: runs in a separate, isolated interpreter (-I) with CPU, memory
     and wall-clock limits, no file writes and no process spawning.
  4. Side effects (opening a URL, notifications) are only *requested* by the
     snippet over a pipe; the trusted parent checks and performs them.

This file must stay stdlib-only: it is executed directly as a script.
"""

import ast
import json
import sys
from types import SimpleNamespace

TIMEOUT_SECONDS = 30

# module name -> attributes the snippet may use
ALLOWED_MODULES = {
    "webbrowser": {"open", "open_new", "open_new_tab"},
    "time": {"sleep", "time", "monotonic", "strftime", "localtime", "gmtime"},
    "datetime": {"datetime", "date", "time", "timedelta", "timezone"},
    "math": None,  # None = every public name
    "random": {"random", "randint", "randrange", "choice", "choices",
               "shuffle", "sample", "uniform"},
    "json": {"dumps", "loads"},
    "re": {"match", "fullmatch", "search", "sub", "split", "findall",
           "escape", "IGNORECASE", "MULTILINE"},
    "statistics": {"mean", "median", "mode", "stdev"},
}

# Names that are refused anywhere in the code, with a friendly reason.
BANNED_NAMES = {
    "eval": "eval() is banned",
    "exec": "exec() is banned",
    "compile": "compile() is banned",
    "open": "file access is banned",
    "__import__": "__import__ is banned",
    "getattr": "getattr() is banned", "setattr": "setattr() is banned",
    "delattr": "delattr() is banned", "globals": "globals() is banned",
    "locals": "locals() is banned", "vars": "vars() is banned",
    "dir": "dir() is banned", "breakpoint": "breakpoint() is banned",
    "input": "input() is banned", "help": "help() is banned",
    "type": "type() is banned", "object": "object is banned",
    "super": "super() is banned", "memoryview": "memoryview is banned",
}

# Attribute names that allow escaping a Python sandbox via introspection.
BANNED_ATTR_PREFIXES = ("_", "gi_", "cr_", "ag_", "f_", "tb_", "co_")
BANNED_ATTRS = {"mro", "format", "format_map"}

SAFE_BUILTINS = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
        "set", "frozenset", "tuple", "min", "max", "sum", "abs", "round",
        "sorted", "reversed", "enumerate", "zip", "map", "filter", "any",
        "all", "isinstance", "chr", "ord", "divmod", "pow", "hex", "bin",
        "repr", "True", "False", "None",
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "RuntimeError", "ZeroDivisionError",
    )
}


class SandboxError(Exception):
    pass


def _bad_attr(name):
    return name.startswith(BANNED_ATTR_PREFIXES) or name in BANNED_ATTRS


def validate(code):
    """Return a list of human-readable problems; empty list means OK."""
    try:
        tree = ast.parse(code, "<snippet>")
    except SyntaxError as e:
        return [f"line {e.lineno}: syntax error: {e.msg}"]

    problems = []

    def bad(node, msg):
        problems.append(f"line {getattr(node, 'lineno', '?')}: {msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if alias.name not in ALLOWED_MODULES:
                    bad(node, f"import of '{root}' is not allowed "
                              f"(allowed: {', '.join(sorted(ALLOWED_MODULES))})")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad(node, "relative imports are not allowed")
                continue
            if node.module not in ALLOWED_MODULES:
                bad(node, f"import from '{node.module}' is not allowed")
                continue
            allowed = ALLOWED_MODULES[node.module]
            for alias in node.names:
                if alias.name == "*" or _bad_attr(alias.name) or (
                        allowed is not None and alias.name not in allowed):
                    bad(node, f"'{alias.name}' from {node.module} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES:
                bad(node, BANNED_NAMES[node.id])
            elif node.id.startswith("_"):
                bad(node, f"names starting with '_' are not allowed ({node.id})")
        elif isinstance(node, ast.Attribute):
            if _bad_attr(node.attr):
                bad(node, f"attribute '.{node.attr}' is not allowed")
        elif isinstance(node, ast.MatchClass):
            for attr in node.kwd_attrs:
                if _bad_attr(attr):
                    bad(node, f"pattern attribute '{attr}' is not allowed")
        elif isinstance(node, ast.ClassDef):
            bad(node, "class definitions are not allowed")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor,
                               ast.AsyncWith)):
            bad(node, "async code is not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bad(node, "global/nonlocal are not allowed")
    return problems


def _module_proxy(name, request):
    if name == "webbrowser":
        # Opening is done by the trusted parent, not inside the sandbox.
        return SimpleNamespace(open=lambda url, *a, **k: request("open_url", url),
                               open_new=lambda url: request("open_url", url),
                               open_new_tab=lambda url: request("open_url", url))
    import importlib
    real = importlib.import_module(name)
    allowed = ALLOWED_MODULES[name]
    if allowed is None:
        allowed = {n for n in dir(real) if not n.startswith("_")}
    return SimpleNamespace(**{n: getattr(real, n) for n in allowed})


def _execute(code, request_fd):
    problems = validate(code)
    if problems:
        raise SandboxError("\n".join(problems))

    channel = open(request_fd, "w", buffering=1)

    def request(kind, *args):
        channel.write(json.dumps({"kind": kind, "args": [str(a) for a in args]}) + "\n")
        return True

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in ALLOWED_MODULES:
            raise ImportError(f"import of '{name}' is not allowed")
        return _module_proxy(name, request)

    builtins = dict(SAFE_BUILTINS, __import__=safe_import)
    env = {"__builtins__": builtins, "__name__": "snippet",
           "notify": lambda title, body="": request("notify", title, body),
           "open_url": lambda url: request("open_url", url)}
    exec(compile(code, "<snippet>", "exec"), env)  # noqa: S102 - validated above


def _limit_resources():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SECONDS, TIMEOUT_SECONDS))
    mem = 512 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # can't write files
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))  # can't spawn processes


def _handle_request(line, on_open_url, on_notify):
    """Perform a side effect the snippet asked for, after checking it."""
    try:
        req = json.loads(line)
        kind, args = req["kind"], req["args"]
    except (ValueError, KeyError, TypeError):
        return
    if kind == "open_url" and len(args) == 1:
        from urllib.parse import urlparse
        if urlparse(args[0]).scheme in ("http", "https"):
            on_open_url(args[0])
    elif kind == "notify" and len(args) == 2:
        on_notify(args[0][:200], args[1][:1000])


def _default_open_url(url):
    import webbrowser
    webbrowser.open(url)


def _default_notify(title, body):
    import subprocess
    subprocess.run(["notify-send", "-a", "NumpadPilot", title, body],
                   check=False, timeout=5)


def run(code, on_open_url=_default_open_url, on_notify=_default_notify):
    """Run a snippet in an isolated child interpreter. Returns (ok, output)."""
    import os
    import subprocess
    import threading

    problems = validate(code)
    if problems:
        return False, "\n".join(problems)

    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        [sys.executable, "-I", __file__, str(write_fd)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, pass_fds=(write_fd,), preexec_fn=_limit_resources,
    )
    os.close(write_fd)

    def pump():
        with open(read_fd) as requests:
            for line in requests:
                _handle_request(line, on_open_url, on_notify)

    pumper = threading.Thread(target=pump, daemon=True)
    pumper.start()
    try:
        output, _ = proc.communicate(json.dumps({"code": code}),
                                     timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return False, f"snippet killed after {TIMEOUT_SECONDS}s"
    finally:
        pumper.join(timeout=2)
    return proc.returncode == 0, output.strip()


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    try:
        _execute(payload["code"], int(sys.argv[1]))
    except SandboxError as e:
        print(f"rejected:\n{e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"{e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)
