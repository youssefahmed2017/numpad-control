"""packaging/windows/prune-qt.py keeps what the window needs and deletes the rest (run on a made-up PySide6 folder)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prune_qt", Path(__file__).resolve().parent.parent / "tools" / "prune-qt.py")
prune_qt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prune_qt)


def make(root, files):
    for name, content in files.items():
        path = root / "PySide6" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


FILES = {
    "__init__.py": b"x", "QtCore.pyd": b"imports Qt6Core.dll and pyside6.abi3.dll", "QtGui.pyd": b"Qt6Gui.dll",
    "QtWidgets.pyd": b"Qt6Widgets.dll", "QtNetwork.pyd": b"Qt6Network.dll", "QtQml.pyd": b"Qt6Qml.dll",
    "QtOpenGL.pyd": b"Qt6OpenGL.dll", "pyside6qml.abi3.dll": b"Qt6Qml.dll", "QtCore.pyi": b"stub",
    "pyside6.abi3.dll": b"shiboken6.abi3.dll msvcp140.dll", "msvcp140.dll": b"runtime",
    "Qt6Core.dll": b"core", "Qt6Gui.dll": b"needs Qt6Core.dll", "Qt6Widgets.dll": b"needs Qt6Gui.dll",
    "Qt6Network.dll": b"needs Qt6Core.dll", "Qt6Qml.dll": b"qml needs Qt6Network.dll", "Qt6OpenGL.dll": b"gl",
    "Qt6Quick.dll": b"quick needs Qt6Qml.dll", "opengl32sw.dll": b"software gl", "assistant.exe": b"tool",
    "plugins/platforms/qwindows.dll": b"needs Qt6Gui.dll", "plugins/platforms/qdirect2d.dll": b"d2d",
    "plugins/styles/qmodernwindowsstyle.dll": b"s", "plugins/imageformats/qico.dll": b"i", "plugins/imageformats/qwebp.dll": b"w",
    "plugins/sqldrivers/qsqlite.dll": b"sql", "qml/QtQuick/x.qml": b"q", "translations/qt_de.qm": b"t",
    "support/signature.py": b"s", "mystery/file.bin": b"?",
}


class PruneQtTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make(self.root, FILES)
        self.before, self.after = prune_qt.prune(self.root)
        self.left = {str(p.relative_to(self.root / "PySide6")).replace("\\", "/") for p in (self.root / "PySide6").rglob("*") if p.is_file()}

    def test_what_the_window_needs_stays(self):
        for name in ("QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtNetwork.pyd", "__init__.py", "support/signature.py",
                     "plugins/platforms/qwindows.dll", "plugins/styles/qmodernwindowsstyle.dll", "plugins/imageformats/qico.dll"):
            self.assertIn(name, self.left)

    def test_libraries_follow_the_names_inside_the_modules(self):
        for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll", "pyside6.abi3.dll", "msvcp140.dll"):
            self.assertIn(name, self.left)

    def test_the_rest_goes(self):
        for name in ("QtQml.pyd", "QtOpenGL.pyd", "QtCore.pyi", "Qt6Qml.dll", "Qt6Quick.dll", "Qt6OpenGL.dll", "opengl32sw.dll",
                     "assistant.exe", "plugins/platforms/qdirect2d.dll", "plugins/imageformats/qwebp.dll",
                     "plugins/sqldrivers/qsqlite.dll", "qml/QtQuick/x.qml", "translations/qt_de.qm"):
            self.assertNotIn(name, self.left)
        self.assertFalse((self.root / "PySide6" / "plugins" / "sqldrivers").exists())

    def test_an_unknown_folder_is_left_alone(self):
        self.assertIn("mystery/file.bin", self.left)

    def test_it_gets_smaller(self):
        self.assertLess(self.after, self.before)

    def test_it_refuses_when_a_needed_module_is_missing(self):
        (self.root / "PySide6" / "QtWidgets.pyd").unlink()
        with self.assertRaises(SystemExit):
            prune_qt.prune(self.root)


LINUX_FILES = {
    "__init__.py": b"x", "QtCore.abi3.so": b"libQt6Core.so.6 libpyside6.abi3.so.6.12", "QtGui.abi3.so": b"libQt6Gui.so.6",
    "QtWidgets.abi3.so": b"libQt6Widgets.so.6", "QtNetwork.abi3.so": b"libQt6Network.so.6", "QtQml.abi3.so": b"libQt6Qml.so.6",
    "QtCore.pyi": b"stub", "assistant": b"tool", "libpyside6.abi3.so.6.12": b"libshiboken6.abi3.so.6.12",
    "libpyside6qml.abi3.so.6.12": b"libQt6Qml.so.6", "Qt/lib/libQt6Core.so.6": b"libicuuc.so.73", "Qt/lib/libicuuc.so.73": b"libicudata.so.73",
    "Qt/lib/libicudata.so.73": b"data", "Qt/lib/libQt6Gui.so.6": b"libQt6Core.so.6", "Qt/lib/libQt6Widgets.so.6": b"libQt6Gui.so.6",
    "Qt/lib/libQt6Network.so.6": b"libQt6Core.so.6", "Qt/lib/libQt6Qml.so.6": b"libQt6Network.so.6", "Qt/lib/libQt6Quick.so.6": b"libQt6Qml.so.6",
    "Qt/lib/libQt6WaylandClient.so.6": b"libQt6Gui.so.6", "Qt/lib/libQt6Designer.so.6": b"d",
    "Qt/plugins/platforms/libqxcb.so": b"libQt6Gui.so.6", "Qt/plugins/platforms/libqwayland.so": b"libQt6WaylandClient.so.6",
    "Qt/plugins/platformthemes/libqgtk3.so": b"t", "Qt/plugins/imageformats/libqico.so": b"i", "Qt/plugins/imageformats/libqsvg.so": b"svg",
    "Qt/plugins/sqldrivers/libqsqlite.so": b"sql", "Qt/qml/QtQuick/x.qml": b"q", "Qt/translations/qt_de.qm": b"t", "Qt/metatypes/a.json": b"m",
}


class PruneQtLinuxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make(self.root, LINUX_FILES)
        prune_qt.prune(self.root)
        self.left = {str(p.relative_to(self.root / "PySide6")) for p in (self.root / "PySide6").rglob("*") if p.is_file()}

    def test_the_window_and_both_desktops_stay(self):
        for name in ("QtWidgets.abi3.so", "libpyside6.abi3.so.6.12", "Qt/lib/libQt6Widgets.so.6", "Qt/lib/libQt6Core.so.6",
                     "Qt/lib/libicuuc.so.73", "Qt/lib/libicudata.so.73", "Qt/lib/libQt6WaylandClient.so.6",
                     "Qt/plugins/platforms/libqxcb.so", "Qt/plugins/platforms/libqwayland.so",
                     "Qt/plugins/platformthemes/libqgtk3.so", "Qt/plugins/imageformats/libqico.so"):
            self.assertIn(name, self.left)

    def test_qml_tools_and_unused_plugins_go(self):
        for name in ("QtQml.abi3.so", "QtCore.pyi", "assistant", "libpyside6qml.abi3.so.6.12", "Qt/lib/libQt6Qml.so.6",
                     "Qt/lib/libQt6Quick.so.6", "Qt/lib/libQt6Designer.so.6", "Qt/plugins/imageformats/libqsvg.so",
                     "Qt/plugins/sqldrivers/libqsqlite.so", "Qt/qml/QtQuick/x.qml", "Qt/translations/qt_de.qm", "Qt/metatypes/a.json"):
            self.assertNotIn(name, self.left)


if __name__ == "__main__":
    unittest.main()
