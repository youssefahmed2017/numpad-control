#!/usr/bin/env bash
# Moved: this is setup.sh now (it has an install / uninstall / update menu). This stub keeps old links working.
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -f "$here/setup.sh" ]; then exec bash "$here/setup.sh" "$@"; fi
exec bash <(curl -fsSL https://raw.githubusercontent.com/youssefahmed2017/numpad-pilot/main/setup.sh) "$@"
