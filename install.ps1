# Moved: this is setup.ps1 now (it has an install / uninstall / update menu). This stub keeps old links working.
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "setup.ps1"))) { & (Join-Path $PSScriptRoot "setup.ps1") @args }
else { irm https://raw.githubusercontent.com/youssefahmed2017/numpad-pilot/main/setup.ps1 | iex }
