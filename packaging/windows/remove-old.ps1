# Run by the installer before it copies anything: finds a NumpadPilot / "Numpad Control" that the old
# PowerShell installer (setup.ps1) put on this PC, stops it and removes it.
# Settings (%APPDATA%\numpad-control) and the Interception driver are never touched.
param([Parameter(Mandatory)][string]$NewDir)
$ErrorActionPreference = "Continue"
$log = Join-Path $env:TEMP "numpadpilot-cleanup.log"
function Log($text) { Add-Content -Path $log -Value "$(Get-Date -Format s) $text" }
Log "looking for an old copy (new one goes to $NewDir)"

function Is-OurFolder($path) {
    # Only a folder that really is NumpadPilot's code, and not the one being installed now.
    if (-not $path -or -not (Test-Path $path)) { return $false }
    $full = (Resolve-Path $path).Path.TrimEnd('\')
    if ($full -eq $NewDir.TrimEnd('\')) { return $false }
    return (Test-Path (Join-Path $full "numpad-control.pyw")) -and (Test-Path (Join-Path $full "numpadctl"))
}

# 1. Where the old copy lives: the default folder, and wherever its start-at-login entry points.
$folders = @(Join-Path $env:USERPROFILE "numpad-control")
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
foreach ($name in "NumpadPilot", "Numpad Control") {
    $command = (Get-ItemProperty -Path $runKey -Name $name -ErrorAction SilentlyContinue).$name
    if (-not $command) { continue }
    if ($command -match '"([^"]*numpad-control\.pyw)"') { $folders += Split-Path $matches[1] }
    if ($name -eq "Numpad Control" -or $command -notlike "*$($NewDir.TrimEnd('\'))*") {
        Remove-ItemProperty -Path $runKey -Name $name -ErrorAction SilentlyContinue
        Log "removed the start-at-login entry '$name'"
    }
}
$folders = $folders | Where-Object { Is-OurFolder $_ } | Select-Object -Unique

# 2. Stop it (the tray app and the settings window).
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { ($_.CommandLine -like "*numpad-control.pyw*" -or $_.CommandLine -like "*-m numpadctl*") -and
                   $_.ExecutablePath -notlike "$($NewDir.TrimEnd('\'))\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Log "stopped process $($_.ProcessId)" }
Start-Sleep -Milliseconds 800

# 3. The old Start-menu entries (a folder named NumpadPilot or Numpad Control).
$programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
foreach ($name in "NumpadPilot", "Numpad Control") {
    $folder = Join-Path $programs $name
    if (Test-Path -PathType Container $folder) { Remove-Item -Recurse -Force $folder -ErrorAction SilentlyContinue; Log "removed Start-menu folder $folder" }
}

# 4. The old program folder.
foreach ($folder in $folders) {
    Remove-Item -Recurse -Force $folder -ErrorAction SilentlyContinue
    Log "removed the old copy in $folder"
}
Log "done"
