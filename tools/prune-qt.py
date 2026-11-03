"""Removes the parts of the PySide6 folder NumpadPilot never loads, so an install carries less.

    python prune-qt.py SITE_PACKAGES_FOLDER

Used by setup.ps1, setup.sh and packaging/windows/build-installer.ps1 right after pip. Works on both
layouts: Windows (DLLs next to the modules) and Linux (a Qt/ folder with lib/ and plugins/).

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
import struct
import sys
from pathlib import Path

KEEP_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork"}
# Windows: folder -> plugin names (without .dll) to keep; qoffscreen and qminimal are for the tests and the smoke test.
KEEP_PLUGINS = {
    "platforms": {"qwindows", "qoffscreen", "qminimal"},
    "styles": {"qmodernwindowsstyle"},
    "imageformats": {"qico", "qjpeg", "qgif"},
}
# Linux: which desktop is running decides the platform plugin (X11 or Wayland) and the Wayland client plugins,
# so those stay. Gone: kiosk and embedded platforms, the Wayland compositor side, input plugins for kiosks,
# and everything for QML, SQL, printing and SVG.
LINUX_KEEP_PLUGINS = {
    "platforms": {"qxcb", "qwayland", "qoffscreen", "qminimal"},
    "imageformats": {"qico", "qjpeg", "qgif"},
    "platforminputcontexts": {"composeplatforminputcontextplugin", "ibusplatforminputcontextplugin"},   # not the on-screen keyboard: it needs Quick
}
LINUX_DELETE_PLUGIN_DIRS = {"designer", "qmltooling", "sqldrivers", "printsupport", "vectorimageformats", "iconengines",
                            "networkinformation", "egldeviceintegrations", "generic", "wayland-graphics-integration-server"}
DELETE_DIRS = {"qml", "translations", "resources", "metatypes", "include", "typesystems", "glue", "scripts", "examples"}
KEEP_DIRS = {"plugins", "support", "__pycache__", "Qt"}


def size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def module_name(path):
    return path.name.split(".")[0]


def is_module(path):
    return path.name.endswith((".pyd", ".abi3.so"))


def plugin_name(path):
    """qwindows.dll -> qwindows, libqoffscreen.so -> qoffscreen"""
    name = path.name.lower()
    name = name[3:] if name.startswith("lib") else name
    return name.split(".")[0]


def libraries(package, qt, linux):
    """Every shared library of the package by lower-case file name (the names other files mention)."""
    found = {}
    folders = [package / "Qt" / "lib", package] if linux else [package]
    for folder in folders:
        if folder.is_dir():
            for path in folder.iterdir():
                name = path.name.lower()
                if path.is_file() and (name.endswith(".dll") or ".so" in name) and not is_module(path):
                    found[name] = path
    return found


def elf_needed(data):
    """The library names an ELF file (64-bit, little-endian) depends on, or None if it isn't one."""
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x02\x01":
        return None
    phoff, = struct.unpack_from("<Q", data, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)
    loads, dynamic = [], None
    for i in range(phnum):
        kind, _, offset, vaddr, _, filesz, *_ = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phentsize)
        if kind == 1:
            loads.append((vaddr, offset, filesz))
        elif kind == 2:
            dynamic = (offset, filesz)
    if dynamic is None:
        return set()

    def file_offset(vaddr):
        return next(off + vaddr - start for start, off, size in loads if start <= vaddr < start + size)

    needed, strtab, position = [], None, dynamic[0]
    while position < dynamic[0] + dynamic[1]:
        tag, value = struct.unpack_from("<qQ", data, position)
        if tag == 0:
            break
        if tag == 1:
            needed.append(value)
        elif tag == 5:
            strtab = file_offset(value)
        position += 16
    names = set()
    for value in needed:
        end = data.index(b"\0", strtab + value)
        names.add(data[strtab + value:end].decode().lower())
    return names


def mentioned(path, candidates):
    """The candidate libraries this file needs: from its dependency list (ELF), else by finding their names in it."""
    data = path.read_bytes()
    needed = elf_needed(data)
    if needed is not None:
        return {candidates[name] for name in needed if name in candidates}
    data = data.lower()
    return {other for name, other in candidates.items() if name.encode() in data}


def wanted_libraries(candidates, seeds):
    """The libraries the seed files (directly or through each other) need."""
    keep, queue = set(), list(seeds)
    while queue:
        for path in mentioned(queue.pop(), candidates):
            if path not in keep:
                keep.add(path)
                queue.append(path)
    return keep


def plugin_choices(plugins, linux):
    """(kept plugin files, plugin files and folders to delete)"""
    keep, remove = set(), []
    if not plugins.is_dir():
        return keep, remove
    for folder in sorted(p for p in plugins.iterdir() if p.is_dir()):
        if linux and folder.name in LINUX_DELETE_PLUGIN_DIRS:
            remove.append(folder)
            continue
        names = (LINUX_KEEP_PLUGINS if linux else KEEP_PLUGINS).get(folder.name)
        for plugin in sorted(p for p in folder.rglob("*") if p.is_file()):
            if names is None and linux or names is not None and plugin_name(plugin) in names:
                keep.add(plugin)
            else:
                remove.append(plugin)
    return keep, remove


def prune(site_packages):
    package = Path(site_packages) / "PySide6"
    if not package.is_dir():
        raise SystemExit(f"{package} isn't there: nothing to prune.")
    linux = (package / "Qt").is_dir()
    qt = package / "Qt" if linux else package
    modules = {p for p in package.iterdir() if is_module(p) and module_name(p) in KEEP_MODULES}
    missing = KEEP_MODULES - {module_name(p) for p in modules}
    if missing:
        raise SystemExit(f"PySide6 has no {', '.join(sorted(missing))} here: refusing to prune.")
    plugins_keep, plugins_remove = plugin_choices(qt / "plugins", linux)
    candidates = libraries(package, qt, linux)
    # Only the main PySide6 library: the QML one (pyside6qml) would drag Qt6Qml and Quick in.
    main = {path for name, path in candidates.items() if "pyside6." in name and "pyside6qml" not in name}
    libs = wanted_libraries(candidates, modules | plugins_keep | main)

    before, removed, unknown = size(package), list(map(lambda p: (size(p), p), plugins_remove)), []
    for item in sorted(package.iterdir()):
        if item.is_dir():
            if item.name in DELETE_DIRS:
                removed.append((size(item), item))
            elif item.name not in KEEP_DIRS:
                unknown.append(f"{item.name} ({size(item) / 1e6:.1f} MB)")
        elif item.suffix != ".py" and item not in modules and item not in libs:
            removed.append((size(item), item))
    if linux:
        for item in sorted(qt.iterdir()):
            if item.is_dir() and item.name in DELETE_DIRS:
                removed.append((size(item), item))
        removed += [(size(p), p) for p in candidates.values() if p.parent == qt / "lib" and p not in libs]
    for _, item in removed:
        if item.is_dir():
            shutil.rmtree(item)
        elif item.exists():
            item.unlink()
    for folder in (qt / "plugins").iterdir() if (qt / "plugins").is_dir() else []:
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    after = size(package)

    print(f"PySide6 pruned: {before / 1e6:.0f} MB -> {after / 1e6:.0f} MB (removed {len(removed)} items, {'Linux' if linux else 'Windows'} layout)")
    print("  largest removed:", ", ".join(f"{p.name} {s / 1e6:.1f} MB" for s, p in sorted(removed, key=lambda x: -x[0])[:8]))
    print("  kept libraries:", ", ".join(sorted(p.name for p in libs)))
    print("  kept plugins:", ", ".join(sorted(f"{p.parent.name}/{p.name}" for p in plugins_keep)))
    if unknown:
        print("  folders left alone (not on the allowlist or the delete list):", ", ".join(unknown))
    return before, after


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    prune(sys.argv[1])
