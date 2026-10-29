# Builds NumpadPilot-Setup-<version>.exe (what winget installs). Needs Windows, Python 3.12 and Inno Setup 6.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1
#
# The installer carries its own Python (the "embeddable" build from python.org) with the Python
# packages already in it, so nothing is downloaded when someone installs, and it needs no
# administrator rights. The result is in build\windows\.
param([string]$PythonVersion = "3.12.10")

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Build = Join-Path $Root "build\windows"
$App = Join-Path $Build "app"
$Version = (Select-String -Path (Join-Path $Root "numpadctl\__init__.py") -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value

function Step($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }
function Assert-Ok($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

if ((python -c "import sys; print('%d.%d' % sys.version_info[:2])") -ne ($PythonVersion -replace '\.\d+$', '')) {
    throw "Build with Python $($PythonVersion -replace '\.\d+$', '') (the packages must match the Python inside the installer)."
}

Step "Fresh build folder"
Remove-Item -Recurse -Force $Build -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $App | Out-Null

Step "Python $PythonVersion (embeddable)"
$zip = Join-Path $Build "python-embed.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip -UseBasicParsing
Expand-Archive $zip (Join-Path $App "python")
$short = "python" + ($PythonVersion -replace '^(\d+)\.(\d+).*', '$1$2')
# The embeddable Python ignores PYTHONPATH and the current folder; list where its packages and our code are.
Set-Content (Join-Path $App "python\$short._pth") @("$short.zip", ".", "..", "Lib\site-packages", "import site") -Encoding ascii

Step "Python packages"
python -m pip install --quiet --target (Join-Path $App "python\Lib\site-packages") --only-binary=:all: -r (Join-Path $Root "requirements.txt")
Assert-Ok "pip install"

Step "NumpadPilot's code"
foreach ($item in "numpadctl", "numpadctl_ui", "assets", "numpad-control.pyw", "LICENSE", "README.md") {
    Copy-Item -Recurse -Force (Join-Path $Root $item) $App
}
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
# Installed by an installer: updates come from winget or a newer installer, not from the app.
Set-Content (Join-Path $App ".packaged") "" -Encoding ascii

Step "Installer"
$iscc = @("$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { throw "Inno Setup 6 wasn't found (winget install JRSoftware.InnoSetup)." }
& $iscc "/DAppVersion=$Version" "/DBuildDir=$Build" (Join-Path $PSScriptRoot "numpad-pilot.iss")
Assert-Ok "Inno Setup"

$setup = Join-Path $Build "NumpadPilot-Setup-$Version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Built $setup"
Write-Host "SHA256 $hash"
