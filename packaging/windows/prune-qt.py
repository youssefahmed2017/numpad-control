"""Removes the parts of the PySide6 folder NumpadPilot never loads, so the installer carries less.

    python prune-qt.py SITE_PACKAGES_FOLDER

The settings window uses only QtCore, QtGui, QtWidgets and QtNetwork. pip installs a lot more next to
them: QML and Quick, translations, developer tools, type stubs and plugins for things the app doesn't do.
This keeps an allowlist and deletes the rest of the PySide6 folder:

  * the four Python modules above, and the loose .py files of the package;
  * every DLL those modules (and the kept plugins) need, found by reading the DLL names inside them,
    so the Qt libraries and the Visual C++ runtime files stay and nothing else does;
  * the few plugins listed in KEEP_PLUGINS.

Folders this script doesn't know are left alone and printed, so a new PySide6 can't lose something
silently. packaging/windows/qt_check.py (run by smoke-test.ps1 on the installed copy) proves the window
still opens afterwards.
"""

import shutil
import sys
from pathlib import Path

KEEP_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork"}
# folder -> plugin names (without .dll). qoffscreen and qminimal are for the tests and the smoke test.
KEEP_PLUGINS = {
    "platforms": {"qwindows", "qoffscreen", "qminimal"},
    "styles": {"qmodernwindowsstyle"},
    "imageformats": {"qico", "qjpeg", "qgif"},
}
DELETE_DIRS = {"qml", "translations", "resources", "metatypes", "include", "typesystems", "glue", "scripts", "examples"}
KEEP_DIRS = {"plugins", "support", "__pycache__"}


def size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def module_name(path):
    return path.name.split(".")[0]


def wanted_dlls(package, seeds):
    """The DLLs in the package folder that the seed files (directly or through each other) mention by name."""
    dlls = {p.name.lower(): p for p in package.glob("*.dll")}
    keep, queue = set(), list(seeds)
    while queue:
        data = queue.pop().read_bytes().lower()
        for name, path in dlls.items():
            if path not in keep and name.encode() in data:
                keep.add(path)
                queue.append(path)
    return keep


def kept_plugins(package):
    keep = set()
    for folder, names in KEEP_PLUGINS.items():
        for plugin in (package / "plugins" / folder).glob("*.dll"):
            if plugin.stem.lower() in names:
                keep.add(plugin)
    return keep


def prune(site_packages):
    package = Path(site_packages) / "PySide6"
    if not package.is_dir():
        raise SystemExit(f"{package} isn't there: nothing to prune.")
    modules = {p for p in package.iterdir() if p.suffix == ".pyd" and module_name(p) in KEEP_MODULES}
    missing = KEEP_MODULES - {module_name(p) for p in modules}
    if missing:
        raise SystemExit(f"PySide6 has no {', '.join(sorted(missing))} here: refusing to prune.")
    plugins = kept_plugins(package)
    dlls = wanted_dlls(package, modules | plugins | {p for p in package.glob("pyside6*.dll")})
    keep_files = modules | plugins | dlls | {p for p in package.iterdir() if p.suffix == ".py"}

    before, removed, unknown = size(package), [], []
    for item in sorted(package.iterdir()):
        if item.is_dir():
            if item.name in DELETE_DIRS:
                removed.append((size(item), item))
            elif item.name not in KEEP_DIRS:
                unknown.append(item.name)
        elif item not in keep_files:
            removed.append((size(item), item))
    for folder in sorted((package / "plugins").iterdir()) if (package / "plugins").is_dir() else []:
        if not folder.is_dir():
            continue
        for plugin in folder.iterdir():
            if plugin not in plugins:
                removed.append((size(plugin), plugin))
    for _, item in removed:
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    for folder in (package / "plugins").iterdir() if (package / "plugins").is_dir() else []:
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    after = size(package)

    print(f"PySide6 pruned: {before / 1e6:.0f} MB -> {after / 1e6:.0f} MB (removed {len(removed)} items)")
    print("  largest removed:", ", ".join(f"{p.name} {s / 1e6:.1f} MB" for s, p in sorted(removed, key=lambda x: -x[0])[:8]))
    print("  kept DLLs:", ", ".join(sorted(p.name for p in dlls)))
    print("  kept plugins:", ", ".join(sorted(f"{p.parent.name}/{p.name}" for p in plugins)))
    if unknown:
        print("  folders left alone (not on the allowlist or the delete list):", ", ".join(unknown))
    return before, after


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    prune(sys.argv[1])
