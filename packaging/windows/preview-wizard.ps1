# Runs the installer's wizard on a CI machine and screenshots each page (CI only: it types into the desktop).
param([Parameter(Mandatory)][string]$Setup, [string]$Out = "wizard-shots")
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null
function Shot($name) {
    $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $bmp.Save((Join-Path $Out "$name.png"))
}
function Keys($keys, $name) { [System.Windows.Forms.SendKeys]::SendWait($keys); Start-Sleep -Seconds 3; Shot $name }

$dir = Join-Path $env:RUNNER_TEMP "NumpadPilot-preview"
Start-Process $Setup -ArgumentList "/DIR=`"$dir`""
Start-Sleep -Seconds 8; Shot "1-welcome"
Keys "%n" "2-license"
Keys "%a" "2b-license-accepted"
Keys "%n" "3-folder"
Keys "%n" "4-tasks"
Keys "%n" "5-ready"
Keys "%i" "6-installing"
Start-Sleep -Seconds 45; Shot "7-finish"

# The same wizard in Windows' dark mode (Setup follows the system theme).
Get-Process | Where-Object { $_.ProcessName -like "NumpadPilot-Setup*" -or $_.ProcessName -like "*.tmp" } | Stop-Process -Force -ErrorAction SilentlyContinue
$theme = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
Set-ItemProperty $theme -Name AppsUseLightTheme -Value 0
Set-ItemProperty $theme -Name SystemUsesLightTheme -Value 0
Start-Sleep -Seconds 3
Start-Process $Setup -ArgumentList "/DIR=`"$dir`""
Start-Sleep -Seconds 8; Shot "dark-1-welcome"
Keys "%n" "dark-2-license"
Keys "%a" "dark-2b-accepted"
Keys "%n" "dark-3-folder"
Keys "%n" "dark-4-tasks"
