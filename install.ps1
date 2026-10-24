# Numpad Control installer for Windows (Windows PowerShell 5.1 or PowerShell 7).
#
#   irm https://raw.githubusercontent.com/youssefahmed2017/numpad-control/main/install.ps1 | iex
#
# or, from a copy of the project:  powershell -ExecutionPolicy Bypass -File install.ps1 [options]
#
# It installs Python if needed (winget), gets the code (git, or a zip download),
# creates the Python environment, installs the Interception driver (one admin
# prompt; the numpad needs it), adds Start-menu entries and starts Numpad Control
# at login. Running it again updates everything.
#
# Options: -Dir PATH     where to put it (default: your user folder\numpad-control)
#          -NoAutostart  don't start Numpad Control at login
#          -DryRun       only show what it would do
#          -Uninstall    remove the shortcuts and autostart (keeps your settings)
# "irm | iex" can't pass options; set them first instead, e.g.
#   $env:NUMPAD_DRYRUN = "1"; irm ... | iex

$RepoUrl = "https://github.com/youssefahmed2017/numpad-control"
$InterceptionZip = "https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip"

function Step($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }
function Note($text) { Write-Host "  $text" }
function Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow }

function Assert-Ok($what) {
    # Programs (git, winget, python) report failure through their exit code only.
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE) - see the messages above." }
}

function Find-Python {
    # The real python.exe (not the Microsoft Store placeholder), version 3.10 or newer.
    foreach ($candidate in @("py", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd -or $cmd.Source -like "*WindowsApps*") { continue }
        $code = "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')"
        try {
            # Arguments written out, not splatted from an array: PowerShell would split "-c" into "-" "c".
            if ($candidate -eq "py") { $exe = & $cmd.Source -3 -c $code 2>$null }
            else { $exe = & $cmd.Source -c $code 2>$null }
        } catch { continue }
        if ($exe) { return "$exe".Trim() }
    }
    return $null
}

function Test-InterceptionDriver {
    # Interception installs two filter drivers: keyboard.sys and mouse.sys (services "keyboard", "mouse").
    $service = if (Get-Command Get-Service -ErrorAction SilentlyContinue) { Get-Service -Name keyboard -ErrorAction SilentlyContinue } else { $null }
    $file = if ($env:windir) { Join-Path $env:windir "System32\drivers\keyboard.sys" } else { $null }
    return [bool]$service -or ($file -and (Test-Path $file))
}

function Stop-NumpadControl($launcher) {
    # A running copy keeps the old code; stop it so the updated one can start.
    if (-not (Get-Command Get-CimInstance -ErrorAction SilentlyContinue)) { return }
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*numpad-control.pyw*" -or $_.CommandLine -like "*-m numpadctl run*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function New-Shortcut($path, $target, $arguments, $workdir, $icon) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $workdir
    if ($icon -and (Test-Path $icon)) { $link.IconLocation = $icon }
    $link.Save()
}

function Install-NumpadControl {
    param(
        [string]$Dir = $(if ($env:NUMPAD_DIR) { $env:NUMPAD_DIR } else { Join-Path $HOME "numpad-control" }),
        [switch]$NoAutostart = [bool]$env:NUMPAD_NOAUTOSTART,
        [switch]$DryRun = [bool]$env:NUMPAD_DRYRUN,
        [switch]$Uninstall = [bool]$env:NUMPAD_UNINSTALL,
        [string]$ScriptRoot = ""
    )
    $ErrorActionPreference = "Stop"

    # Every change goes through Run, so -DryRun can show it instead.
    function Run([string]$what, [scriptblock]$action) {
        if ($DryRun) { Write-Host "  [dry-run] $what" -ForegroundColor DarkGray }
        else { Note $what; & $action }
    }

    $programs = [Environment]::GetFolderPath("Programs")
    if (-not $programs) { $programs = Join-Path $HOME "Start Menu" }  # (only when testing outside Windows)
    $StartMenu = Join-Path $programs "Numpad Control"

    # A copy of the project next to this script is used as it is.
    if ($ScriptRoot -and (Test-Path (Join-Path $ScriptRoot "numpadctl"))) { $Dir = $ScriptRoot; $here = $true } else { $here = $false }
    $VenvPython = Join-Path $Dir ".venv\Scripts\python.exe"
    $VenvPythonw = Join-Path $Dir ".venv\Scripts\pythonw.exe"
    $Launcher = Join-Path $Dir "numpad-control.pyw"
    $InDir = "import sys; sys.path.insert(0, r'$Dir'); "

    # ---------------------------------------------------------------- uninstall
    if ($Uninstall) {
        Step "Removing Numpad Control's shortcuts and autostart"
        Run "stop Numpad Control" { Stop-NumpadControl $Launcher }
        if (Test-Path $VenvPython) {
            Run "turn off start at login" { & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import set_autostart; set_autostart(False)") }
        }
        if (Test-Path $StartMenu) { Run "remove the Start-menu entries" { Remove-Item -Recurse -Force $StartMenu } }
        Note "Your settings stay in $env:APPDATA\numpad-control, the program in $Dir."
        Note "To remove the Interception driver too: run its 'install-interception.exe /uninstall' as administrator, then restart."
        return
    }

    # ---------------------------------------------------------------- 1. Python
    Step "1/6  Python"
    $Python = Find-Python
    if ($Python) {
        Note "found $Python"
    } else {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "Python 3.10+ isn't installed and winget isn't available. Install Python from python.org (tick 'Add python.exe to PATH') and run this again."
        }
        Run "install Python 3.12 with winget" {
            winget install --id Python.Python.3.12 --exactly --silent --accept-package-agreements --accept-source-agreements
            Assert-Ok "Installing Python"
        }
        # winget doesn't update this window's PATH; read it again.
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        $Python = Find-Python
        if (-not $Python -and -not $DryRun) { throw "Python was installed but can't be found yet - open a new PowerShell window and run this again." }
    }

    # ---------------------------------------------------------------- 2. code
    Step "2/6  Code"
    if ($here) {
        Note "using $Dir"
    } elseif (Test-Path (Join-Path $Dir ".git")) {
        if (Get-Command git -ErrorAction SilentlyContinue) {
            Run "update $Dir (git pull)" { git -C $Dir pull --ff-only; Assert-Ok "git pull" }
        } else { Warn "$Dir is a git copy but git isn't installed; not updating it" }
    } elseif (Get-Command git -ErrorAction SilentlyContinue) {
        Run "download into $Dir (git clone)" { git clone "$RepoUrl.git" $Dir; Assert-Ok "git clone" }
    } else {
        Run "download into $Dir (zip)" {
            $zip = Join-Path $env:TEMP "numpad-control.zip"
            Invoke-WebRequest "$RepoUrl/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
            $unpacked = Join-Path $env:TEMP "numpad-control-zip"
            if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
            Expand-Archive $zip $unpacked
            New-Item -ItemType Directory -Force $Dir | Out-Null
            Copy-Item -Recurse -Force (Join-Path $unpacked "numpad-control-main\*") $Dir
        }
    }

    # ---------------------------------------------------------------- 3. Python environment
    Step "3/6  Python environment (downloads Qt for the settings window, about 250 MB)"
    Run "stop a running Numpad Control (it restarts at the end)" { Stop-NumpadControl $Launcher }
    if (-not (Test-Path $VenvPython)) {
        Run "create the environment in $Dir\.venv" { & $Python -m venv (Join-Path $Dir ".venv"); Assert-Ok "Creating the Python environment" }
    }
    Run "install the Python packages" {
        & $VenvPython -m pip install --quiet --upgrade pip
        & $VenvPython -m pip install --quiet --upgrade -r (Join-Path $Dir "requirements.txt")
        Assert-Ok "Installing the Python packages"
    }

    # ---------------------------------------------------------------- 4. Interception
    Step "4/6  Interception driver (lets Numpad Control tell your numpad apart from the keyboard)"
    $Dll = Join-Path $Dir "numpadctl\platform\interception.dll"
    $NeedsRestart = $false
    if ((Test-Path $Dll) -and (Test-InterceptionDriver)) {
        Note "already installed"
    } else {
        $unpacked = Join-Path $env:TEMP "interception"
        Run "download Interception from its official release" {
            $zip = Join-Path $env:TEMP "interception.zip"
            Invoke-WebRequest $InterceptionZip -OutFile $zip -UseBasicParsing
            if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
            Expand-Archive $zip $unpacked
        }
        Run "copy interception.dll next to the code" {
            $source = Get-ChildItem -Recurse -Path $unpacked -Filter interception.dll | Where-Object { $_.FullName -like "*x64*" } | Select-Object -First 1
            if (-not $source) { throw "interception.dll (x64) wasn't in the download." }
            Copy-Item $source.FullName $Dll -Force
        }
        if (-not (Test-InterceptionDriver)) {
            Run "install the driver (Windows will ask for administrator permission)" {
                $installer = Get-ChildItem -Recurse -Path $unpacked -Filter install-interception.exe | Select-Object -First 1
                try {
                    $process = Start-Process $installer.FullName -ArgumentList "/install" -Verb RunAs -Wait -PassThru
                } catch {
                    throw "The driver wasn't installed (administrator permission was declined). Run this again and click Yes."
                }
                if ($process.ExitCode -ne 0) { throw "The Interception installer didn't finish (exit code $($process.ExitCode))." }
            }
            $NeedsRestart = $true
        }
    }

    # ---------------------------------------------------------------- 5. shortcuts
    Step "5/6  Start menu"
    $Icon = Join-Path $Dir "numpad-control.ico"
    Run "draw the icon" {
        & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import draw_icon; draw_icon(256).save(r'$Icon', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])")
        Assert-Ok "Drawing the icon"
    }
    Run "add 'Numpad Control' and 'Numpad Control Settings' to the Start menu" {
        New-Item -ItemType Directory -Force $StartMenu | Out-Null
        New-Shortcut (Join-Path $StartMenu "Numpad Control.lnk") $VenvPythonw "`"$Launcher`"" $Dir $Icon
        New-Shortcut (Join-Path $StartMenu "Numpad Control Settings.lnk") $VenvPythonw "`"$Launcher`" gui" $Dir $Icon
    }

    # ---------------------------------------------------------------- 6. start
    Step "6/6  Starting"
    if (-not $NoAutostart) {
        Run "start Numpad Control at login" {
            & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import set_autostart; set_autostart(True)")
            Assert-Ok "Turning on start at login"
        }
    }
    if ($NeedsRestart) {
        Write-Host ""
        Warn "Restart the PC to finish installing the Interception driver."
        Note "After the restart Numpad Control starts by itself (tray icon, bottom right)."
    } else {
        Run "start Numpad Control now (look for its icon in the tray)" {
            Start-Process $VenvPythonw -ArgumentList "`"$Launcher`"" -WorkingDirectory $Dir
        }
        Write-Host ""
        Note "Done. Right-click the tray icon, or open 'Numpad Control Settings' from the Start menu."
    }
}

Install-NumpadControl @args -ScriptRoot $PSScriptRoot
