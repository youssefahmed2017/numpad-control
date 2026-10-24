"""Everything that differs between operating systems lives in this package.

The rest of numpadctl (key timing, macros, modes, OBS, config) is shared and
talks to the system only through these modules, so a Windows version can add
its own implementations next to the Linux ones.
"""

import sys

IS_WINDOWS = sys.platform == "win32"
