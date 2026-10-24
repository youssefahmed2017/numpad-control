"""Windows: double-click to start Numpad Control in the system tray (no console window)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from numpadctl.platform.windows_tray import main  # noqa: E402

main()
