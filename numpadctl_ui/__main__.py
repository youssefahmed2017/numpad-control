"""python -m numpadctl_ui [--hidden]: open the settings window."""

import sys

from .app import run

sys.exit(run(sys.argv[1:]))
