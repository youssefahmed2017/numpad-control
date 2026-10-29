"""Fills in the manifest templates for a release: python render.py 0.2.1 <sha256 of the installer> [out dir].

The output folder (default: manifests/<version>) is what goes into microsoft/winget-pkgs under
manifests/y/YoussefAhmed/NumpadPilot/<version>/ (validate first on Windows: winget validate <folder>).
"""

import sys
from pathlib import Path

version, sha256 = sys.argv[1], sys.argv[2].upper()
out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent / "manifests" / version
out.mkdir(parents=True, exist_ok=True)
for template in Path(__file__).parent.glob("YoussefAhmed.NumpadPilot*.yaml"):
    text = template.read_text().replace("@VERSION@", version).replace("@SHA256@", sha256)
    (out / template.name).write_text(text)
print(f"wrote {out}")
