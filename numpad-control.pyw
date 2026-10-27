"""Windows: double-click to start NumpadPilot in the system tray (no console window).

With "gui" as argument it opens the settings instead (the tray menu does that): the
NumpadPilot app if it's installed, otherwise the settings file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if "gui" in sys.argv[1:]:
    from numpadctl.gui import run  # noqa: E402
    sys.exit(run(sys.argv[2:]))
else:
    from numpadctl.platform.windows_tray import main  # noqa: E402
    main()
