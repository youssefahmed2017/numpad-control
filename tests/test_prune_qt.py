"""packaging/windows/prune-qt.py keeps what the window needs and deletes the rest (run on a made-up PySide6 folder)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("prune_qt", Path(__file__).resolve().parent.parent / "packaging" / "windows" / "prune-qt.py")
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
    "QtOpenGL.pyd": b"Qt6OpenGL.dll", "QtCore.pyi": b"stub",
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


if __name__ == "__main__":
    unittest.main()
