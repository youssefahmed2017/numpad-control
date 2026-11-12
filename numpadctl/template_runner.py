"""Runs one Python template in its own short-lived process (started by templates.run, never imported).

    python -I template_runner.py <template.py>     (what to fill in: a JSON object on stdin)

The template's build(pad) is called with a Pad that only *records* what the template asks for; the result is
printed as one JSON object and the service-free parent (templates.py) checks every action and setting the
same way an imported profile is checked before anything reaches your config. On Linux the process can't write
files or start programs and has a CPU and memory limit (sandbox.py's limits); everywhere it has a time limit.

This file must stay stdlib-only and must not import numpadctl: it is executed directly as a script.
"""

import json
import runpy
import sys
import traceback

MAX_CALLS = 2000   # recorded actions: a runaway loop stops here instead of filling memory


class TemplateError(Exception):
    pass


def step(action, **params):
    """One step of a macro or of an if/otherwise branch: step("press_keys", keys="ctrl+c")."""
    if not isinstance(action, str):
        raise TemplateError("step(): the action is its id, e.g. step(\"volume_up\")")
    return {"action": action, "params": params}


class _Layer:
    """Records actions for one layer: the normal keys (pad) or the keys while the layer key is held (pad.layer)."""

    def __init__(self, recorder, name):
        self._recorder, self._name = recorder, name

    def set(self, key, slot, action, rapid=None, turbo=None, **params):
        """Put `action` on `key` for `slot` ("tap", "hold" or "double"), with its settings as keywords."""
        if not isinstance(key, str) or not key:
            raise TemplateError(f"a key is its name as text, like \"7\" or \"Enter\" (got {key!r})")
        if slot not in ("tap", "hold", "double"):
            raise TemplateError(f"slot must be \"tap\", \"hold\" or \"double\" (got {slot!r})")
        if not isinstance(action, str):
            raise TemplateError(f"the action is its id as text, like \"volume_up\" (got {action!r})")
        binding = {"action": action, "params": params}
        if rapid is not None:
            binding["rapid"] = bool(rapid)
        if turbo is not None:
            binding["turbo"] = turbo
        self._recorder.record(self._name, key, slot, binding)
        return self

    def tap(self, key, action, **params):
        return self.set(key, "tap", action, **params)

    def hold(self, key, action, **params):
        return self.set(key, "hold", action, **params)

    def double(self, key, action, **params):
        return self.set(key, "double", action, **params)

    def macro(self, key, steps, slot="tap"):
        """Several steps on one key: pad.macro("5", [step("press_keys", keys="ctrl+c"), step("wait", seconds=0.2)])."""
        return self.set(key, slot, "macro", steps=list(steps))

    def if_mode(self, key, mode, then=(), otherwise=(), slot="tap"):
        """Steps that depend on a mode (Settings → Modes): pad.if_mode("8", "Stream mode", [step(...)], [step(...)])."""
        return self.set(key, slot, "if_mode", mode=mode, then=list(then), otherwise=list(otherwise))


class Pad(_Layer):
    """What a template's build(pad) gets. pad.tap / hold / double / set / macro / if_mode fill the normal keys,
    pad.layer.<same> the keys while the layer key is held. pad.note("...") adds a line to the message shown
    afterwards. Read-only facts: pad.keys (the numpad's key names), pad.platform ("linux" / "windows"),
    pad.desktop, pad.profile (the profile's name), pad.layer_key, pad.modes, pad.actions ({id: [setting names]}),
    pad.bound ({key: [slots that already do something]} in the normal layer; pad.layer_bound for the layer)."""

    def __init__(self, info):
        self._calls = {"bindings": {}, "layer_bindings": {}}
        self._count = 0
        self.notes = []
        super().__init__(self, "bindings")
        self.layer = _Layer(self, "layer_bindings")
        self.info = dict(info)
        self.keys = list(info.get("keys", []))
        self.platform = info.get("platform", "")
        self.desktop = info.get("desktop", "")
        self.profile = info.get("profile", "")
        self.layer_key = info.get("layer_key")
        self.modes = list(info.get("modes", []))
        self.actions = dict(info.get("actions", {}))
        self.bound = dict(info.get("bound", {}))
        self.layer_bound = dict(info.get("layer_bound", {}))

    def record(self, layer, key, slot, binding):
        self._count += 1
        if self._count > MAX_CALLS:
            raise TemplateError(f"more than {MAX_CALLS} actions: is a loop running away?")
        self._calls[layer].setdefault(key, {})[slot] = binding

    def note(self, text):
        self.notes.append(str(text)[:300])


def _limit_resources():
    try:
        import resource
    except ImportError:   # Windows: only the parent's time limit
        return
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    mem = 512 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))   # can't write files
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))   # can't start programs


def main(path):
    info = json.loads(sys.stdin.read() or "{}")
    _limit_resources()
    pad = Pad(info)
    try:
        module = runpy.run_path(path, init_globals={"step": step, "TemplateError": TemplateError},
                                run_name="numpadcontrol_template")
        build = module.get("build")
        if not callable(build):
            raise TemplateError("it has no build(pad) function")
        build(pad)
    except TemplateError as e:
        print(json.dumps({"error": str(e)}))
        return
    except Exception as e:   # the template's own bug: say where, briefly
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == path]
        where = f" (line {frames[-1].lineno})" if frames else ""
        print(json.dumps({"error": f"{type(e).__name__}: {e}{where}"}))
        return
    try:
        print(json.dumps({"bindings": pad._calls["bindings"], "layer_bindings": pad._calls["layer_bindings"],
                          "notes": pad.notes[:20]}))
    except (TypeError, ValueError) as e:
        print(json.dumps({"error": f"a setting isn't plain data (text, numbers, lists): {e}"}))


if __name__ == "__main__":
    main(sys.argv[1])
