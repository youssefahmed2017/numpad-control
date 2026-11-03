"""Proves the (pruned) Qt in an installed NumpadControl still does what the settings window needs.

    python qt_check.py [offscreen|windows]

smoke-test.ps1 runs it with the installed copy's own Python. It opens the real settings window against a
throwaway config, paints it, loads a PNG and an .ico, and makes a local socket (QtNetwork), then prints OK.
"offscreen" needs no screen; "windows" uses the real Windows platform plugin (a runner with a desktop).
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

platform = sys.argv[1] if len(sys.argv) > 1 else "offscreen"
os.environ["QT_QPA_PLATFORM"] = platform

from PySide6.QtGui import QIcon, QPixmap  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from numpadctl import config, modes, ui_common  # noqa: E402
from numpadctl_ui import window as window_module  # noqa: E402

ASSETS = Path(window_module.__file__).resolve().parent.parent / "assets"


class QuietLink:
    connected = False

    def __init__(self, on_message, dispatch):
        pass

    def send(self, message):
        pass


def main():
    app = QApplication([])
    assert app.platformName() == platform, f"Qt started the {app.platformName()!r} platform, not {platform!r}"
    for name in ("icon-64.png", "numpad-control.ico"):
        assert not QPixmap(str(ASSETS / name)).isNull(), f"{name} didn't load (is an image plugin missing?)"
    assert not QIcon(str(ASSETS / "icon-32.png")).isNull()

    server, name = QLocalServer(), f"numpad-qt-check-{os.getpid()}"
    assert server.listen(name), "QtNetwork can't listen on a local socket"
    client = QLocalSocket()
    client.connectToServer(name)
    assert client.waitForConnected(2000), "QtNetwork can't connect to a local socket"
    client.disconnectFromServer()
    server.close()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config.json").write_text(json.dumps({"profiles": [{"name": "Default", "match": "", "bindings": {}}]}))
        patches = [mock.patch.object(config, "CONFIG_DIR", root), mock.patch.object(config, "CONFIG_PATH", root / "config.json"),
                   mock.patch.object(modes, "STATE_DIR", root), mock.patch.object(modes, "STATE_PATH", root / "modes.json"),
                   mock.patch.object(ui_common, "ServiceLink", QuietLink)]
        for patch in patches:
            patch.start()
        window = window_module.MainWindow()
        window.show()
        app.processEvents()
        picture = window.grab()
        assert not picture.isNull() and picture.width() > 100, "the settings window didn't paint"
        window.close()
        for patch in patches:
            patch.stop()
    print(f"Qt check OK ({platform}): window painted {picture.width()}x{picture.height()}")


if __name__ == "__main__":
    main()
