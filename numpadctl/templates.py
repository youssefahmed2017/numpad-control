"""Your own templates: Python files that fill in a profile's keys, next to the built-in starter presets.

A template is a .py file in the templates folder (~/.config/numpad-control/templates on Linux) with a
build(pad) function, and optionally NAME and DESCRIPTION:

    NAME = "My streaming pad"
    DESCRIPTION = "Scenes on 1-3, mute on 0."

    def build(pad):
        for number in range(1, 4):
            pad.tap(str(number), "obs_set_scene", scene=f"Scene {number}")
        pad.tap("0", "mic_mute")
        pad.layer.tap("0", "obs_toggle_streaming")
        pad.macro("5", [step("press_keys", keys="ctrl+c"), step("wait", seconds=0.2), step("press_keys", keys="ctrl+v")])

Profile ⋯ → Add a starter preset… lists them; like a preset, a template only fills keys that have nothing yet.
The whole API is in template_runner.py (Pad), and `python -m numpadctl actions` lists every action id and its
settings.

How it is kept safe and solid: the list is made by reading NAME / DESCRIPTION without running anything. A
template runs only when you pick it, in its own process with a time limit (on Linux also unable to write files
or start programs), and what it asks for goes through the same checks as an imported profile, so a template
can't put anything in your config that a profile file couldn't. It is still a program you put there: it can
read files, so only keep templates you trust in that folder.
"""

import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import actions, config, profile_io, ui_common
from .platform import paths

TIMEOUT = 10          # seconds a template may take
MAX_OUTPUT = 2_000_000
RUNNER = Path(__file__).resolve().with_name("template_runner.py")


class TemplateError(Exception):
    """A template couldn't be listed or run; the message is shown as it is."""


@dataclass
class Template:
    name: str
    description: str
    path: Path
    problem: str = ""        # set when the file can't even be read (shown in the list, can't be picked)


@dataclass
class Result:
    bindings: dict = field(default_factory=dict)
    layer_bindings: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    dropped: list = field(default_factory=list)   # what the checks took out, and why


def folder():
    return config.CONFIG_DIR / "templates"


def _literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            return value if isinstance(value, str) else None
    return None


def _pretty(path):
    return path.stem.replace("_", " ").replace("-", " ").capitalize()


def describe(path):
    """A template's NAME and DESCRIPTION (or its file name and docstring), read without running it."""
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError) as e:
        return Template(_pretty(path), "", path, f"can't be read ({e})")
    except SyntaxError as e:
        return Template(_pretty(path), "", path, f"has a mistake on line {e.lineno}: {e.msg}")
    name = _literal(tree, "NAME") or _pretty(path)
    description = _literal(tree, "DESCRIPTION") or (ast.get_docstring(tree) or "").strip().split("\n\n")[0]
    has_build = any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body)
    return Template(name[:80], description[:500], path, "" if has_build else "has no build(pad) function")


def list_templates(where=None):
    where = Path(where) if where else folder()
    if not where.is_dir():
        return []
    return [describe(p) for p in sorted(where.glob("*.py")) if not p.name.startswith(("_", "."))]


def info_for(cfg, profile):
    """What a template may read (pad.keys, pad.platform...): plain data, nothing secret (no OBS password)."""
    return {
        "keys": [k for k, *_ in ui_common.LAYOUT],
        "platform": "windows" if sys.platform == "win32" else "linux" if sys.platform.startswith("linux") else sys.platform,
        "desktop": _desktop(),
        "profile": profile.get("name", ""),
        "layer_key": cfg.get("layer_key"),
        "modes": list(cfg.get("modes", [])),
        "actions": {a.id: [p.name for p in a.params] for a in actions.ACTIONS},
        "bound": {k: [s for s, b in slots.items() if actions.is_set(b)] for k, slots in profile.get("bindings", {}).items()},
        "layer_bound": {k: [s for s, b in slots.items() if actions.is_set(b)]
                        for k, slots in profile.get("layer_bindings", {}).items()},
    }


def _desktop():
    try:
        from . import desktop
        return desktop.current()
    except Exception:   # noqa: BLE001 - a template only gets a hint; never fail over it
        return ""


def _with_defaults(binding):
    """Fill in the settings the template left out with the action's defaults (as the editor would)."""
    action = actions.BY_ID.get(binding.get("action")) if isinstance(binding, dict) else None
    if action is None or not isinstance(binding.get("params"), dict):
        return binding
    params = {p.name: p.default for p in action.params}
    params.update(binding["params"])
    return {**binding, "params": params}


def run(template, cfg, profile, python=None):
    """Run a template and check what it made. Returns a Result; raises TemplateError with a sentence."""
    path = Path(template.path if isinstance(template, Template) else template)
    if not path.is_file():
        raise TemplateError(f"{path.name} isn't there any more")
    try:
        done = subprocess.run([python or sys.executable, "-I", str(RUNNER), str(path)],
                              input=json.dumps(info_for(cfg, profile)), capture_output=True, text=True,
                              timeout=TIMEOUT, cwd=str(paths.state_dir() if paths.state_dir().is_dir() else Path.home()))
    except subprocess.TimeoutExpired:
        raise TemplateError(f"{path.name} took longer than {TIMEOUT} seconds and was stopped") from None
    except OSError as e:
        raise TemplateError(f"couldn't start {path.name}: {e}") from None
    output = done.stdout[-MAX_OUTPUT:].strip().splitlines()
    try:
        data = json.loads(output[-1]) if output else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        detail = (done.stderr.strip().splitlines() or ["it stopped without an answer"])[-1]
        raise TemplateError(f"{path.name} failed: {detail[:300]}")
    if data.get("error"):
        raise TemplateError(f"{path.name}: {str(data['error'])[:300]}")
    result = Result(notes=[str(n)[:300] for n in data.get("notes", [])][:20])
    for layer in ("bindings", "layer_bindings"):
        raw = data.get(layer, {})
        if isinstance(raw, dict):
            raw = {k: {s: _with_defaults(b) for s, b in v.items()} if isinstance(v, dict) else v for k, v in raw.items()}
        label = "the normal keys" if layer == "bindings" else "the layer keys"
        try:
            setattr(result, layer, profile_io._clean_layer(raw, label, result.dropped))
        except profile_io.ProfileFileError as e:
            raise TemplateError(f"{path.name}: {e}") from None
    for layer in (result.bindings, result.layer_bindings):   # macros: check modes etc. against this config
        for key, slots in layer.items():
            for slot, binding in list(slots.items()):
                problems = actions.binding_problems(binding, cfg)
                if problems:
                    result.dropped.append(f"key {key} ({slot}): {problems[0]}")
                    del slots[slot]
        for key in [k for k, slots in layer.items() if not slots]:
            del layer[key]
    return result


def apply(result, profile):
    """Fill the profile's empty slots from a Result (like a starter preset). Returns (added, kept)."""
    added = kept = 0
    for layer in ("bindings", "layer_bindings"):
        target = profile.setdefault(layer, {})
        for key, slots in getattr(result, layer).items():
            mine = target.setdefault(key, {})
            for slot, binding in slots.items():
                if actions.is_set(mine.get(slot, {"action": "none"})):
                    kept += 1
                else:
                    mine[slot] = binding
                    added += 1
            if not mine:
                del target[key]
    return added, kept


EXAMPLE = '''"""My first NumpadControl template.

build(pad) fills keys: pad.tap / pad.hold / pad.double(key, action_id, setting=value...), the same on
pad.layer for the layer keys, pad.macro(key, [step(...), ...]) and pad.if_mode(key, mode, then, otherwise).
Every action is in the list on the right: double-click one to insert its line. "Try it" shows what this would
add; Save, then pick it in Profile ⋯ → Add a starter preset…. It only fills keys that have nothing yet.
"""

NAME = "{name}"
DESCRIPTION = "Media keys on 7-9, volume on 4-6, and copy-paste on the layer."


def build(pad):
    pad.tap("7", "media_previous")
    pad.tap("8", "media_play_pause")
    pad.tap("9", "media_next")
    for key, action in (("4", "volume_down"), ("5", "volume_mute"), ("6", "volume_up")):
        pad.tap(key, action)
    pad.hold("5", "mic_mute")                      # hold 5: mute the microphone

    pad.layer.tap("1", "press_keys", keys="ctrl+c")
    pad.layer.tap("2", "press_keys", keys="ctrl+v")
    pad.layer.macro("3", [step("press_keys", keys="ctrl+a"), step("press_keys", keys="ctrl+c")])

    if pad.platform == "linux":
        pad.note("Tip: Settings → Appearance can follow your wallpaper too.")
'''


def free_path(name):
    """A file name in the templates folder made from a template's name that isn't taken yet."""
    where = folder()
    where.mkdir(parents=True, exist_ok=True)
    base = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_") or "template"
    path, n = where / f"{base}.py", 2
    while path.exists():
        path, n = where / f"{base}_{n}.py", n + 1
    return path


def describe_text(code):
    """The NAME in a template's code (read, not run), or "My template"."""
    try:
        return _literal(ast.parse(code), "NAME") or "My template"
    except SyntaxError:
        return "My template"


def new_template(name="My template"):
    """Write a commented example template into the folder; returns its path (a free file name)."""
    path = free_path(name)
    path.write_text(EXAMPLE.replace("{name}", name.replace('"', "'")), encoding="utf-8")
    return path


def import_template(source):
    """Copy a template file (from anywhere: a download, a friend) into the folder; returns the new path.
    It is only read here, never run: it runs when you pick it, like every template."""
    source = Path(source)
    if source.suffix != ".py":
        raise TemplateError(f"{source.name} isn't a Python file (.py)")
    try:
        code = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise TemplateError(f"couldn't read {source.name}: {e}") from None
    if len(code) > MAX_OUTPUT:
        raise TemplateError(f"{source.name} is too big to be a template")
    path = free_path(describe_text(code) if describe_text(code) != "My template" else source.stem)
    path.write_text(code, encoding="utf-8")
    return path


def delete_template(path):
    """Remove a template from the folder (only files that are in it)."""
    path = Path(path)
    if path.parent.resolve() != folder().resolve():
        raise TemplateError("only templates in the templates folder can be deleted here")
    path.unlink(missing_ok=True)


def describe_actions():
    """Every action id with its settings, for template writers (python -m numpadctl actions)."""
    lines = []
    for action in actions.ACTIONS:
        if action.id == "none":
            continue
        settings = ", ".join(f"{p.name}={p.default!r}" for p in action.params)
        lines.append(f"{action.id:28} {action.label}" + (f"\n{'':28} settings: {settings}" if settings else ""))
    return "\n".join(lines)
