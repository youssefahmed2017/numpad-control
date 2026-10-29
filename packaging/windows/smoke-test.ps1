# Installs the built installer silently, checks the installed copy starts, then uninstalls it.
param([Parameter(Mandatory)][string]$Setup)
$ErrorActionPreference = "Stop"
$dir = Join-Path $env:RUNNER_TEMP "NumpadPilot-smoke"
if (-not $env:RUNNER_TEMP) { $dir = Join-Path $env:TEMP "NumpadPilot-smoke" }

Start-Process $Setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=", "/DIR=`"$dir`"" -Wait
$python = Join-Path $dir "python\python.exe"
foreach ($path in $python, (Join-Path $dir "numpad-control.pyw"), (Join-Path $dir ".packaged"), (Join-Path $dir "numpadctl\platform\numpadhook.dll")) {
    if (-not (Test-Path $path)) { throw "The installer didn't put $path in place." }
}

$env:QT_QPA_PLATFORM = "offscreen"
& $python -c "import numpadctl, numpadctl_ui.window, numpadctl.platform.windows_tray as t, PySide6.QtWidgets, pystray; from numpadctl import updater; assert updater.packaged(); print('installed copy imports fine, version', numpadctl.__version__)"
if ($LASTEXITCODE -ne 0) { throw "The installed copy didn't start." }

$uninstaller = Get-ChildItem $dir -Filter "unins*.exe" | Select-Object -First 1
Start-Process $uninstaller.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
Start-Sleep -Seconds 3
if (Test-Path (Join-Path $dir "python\python.exe")) { throw "Uninstalling left the program behind." }
Write-Host "Install, start and uninstall all worked."
