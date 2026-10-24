"""Windows: double-click to start Numpad Control in the system tray (no console window).

With "gui" as argument it opens the settings window instead (the tray menu does that).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if "gui" in sys.argv[1:]:
    from numpadctl.qt.app import run  # noqa: E402
    sys.exit(run(sys.argv[2:]))
else:
    from numpadctl.platform.windows_tray import main  # noqa: E402
    main()
