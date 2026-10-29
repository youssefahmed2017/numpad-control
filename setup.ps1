# NumpadPilot setup for Windows (Windows PowerShell 5.1 or PowerShell 7): install, uninstall or
# reinstall/update, from a menu. (The installer .exe from the Releases page does the same without PowerShell.)
#
#   irm https://raw.githubusercontent.com/youssefahmed2017/numpad-pilot/main/setup.ps1 | iex
#
# or, from a copy of the project:  powershell -ExecutionPolicy Bypass -File setup.ps1 [options]
#
# It installs Python if needed (winget), gets the code (git, or a zip download),
# creates the Python environment, adds Start-menu entries and starts NumpadPilot
# at login. No driver and no administrator rights are needed. Running it again
# updates everything.
#
# Options: -Install | -Uninstall | -Update   skip the menu (-Update = reinstall, keeping your settings)
#          -Dir PATH     where to put it (default: your user folder\numpad-control)
#          -NoAutostart  don't start NumpadPilot at login
#          -DryRun       only show what it would do
#          -Uninstall    remove the shortcuts and autostart (keeps your settings)
#          -Interception also install the Interception driver and use it to read the numpad
#                        (the old way: one admin prompt and a restart; some games' anti-cheat blocks it)
# "irm | iex" can't pass options; set them first instead, e.g.
#   $env:NUMPAD_DRYRUN = "1"; irm ... | iex      (or $env:NUMPAD_ACTION = "install" | "uninstall" | "update")

$RepoUrl = "https://github.com/youssefahmed2017/numpad-pilot"
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
        [switch]$Interception = [bool]$env:NUMPAD_INTERCEPTION,
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
    $StartMenu = Join-Path $programs "NumpadPilot"
    $OldStartMenu = Join-Path $programs "Numpad Control"  # before the rename to NumpadPilot

    # A copy of the project next to this script is used as it is.
    if ($ScriptRoot -and (Test-Path (Join-Path $ScriptRoot "numpadctl"))) { $Dir = $ScriptRoot; $here = $true } else { $here = $false }
    $VenvPython = Join-Path $Dir ".venv\Scripts\python.exe"
    $VenvPythonw = Join-Path $Dir ".venv\Scripts\pythonw.exe"
    $Launcher = Join-Path $Dir "numpad-control.pyw"
    $InDir = "import sys; sys.path.insert(0, r'$Dir'); "

    # ---------------------------------------------------------------- uninstall
    if ($Uninstall) {
        Step "Removing NumpadPilot's shortcuts and autostart"
        Run "stop NumpadPilot" { Stop-NumpadControl $Launcher }
        if (Test-Path $VenvPython) {
            Run "turn off start at login" { & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import set_autostart; set_autostart(False)") }
        }
        if (Test-Path $StartMenu) { Run "remove the Start-menu entries" { Remove-Item -Recurse -Force $StartMenu } }
        if (Test-Path $OldStartMenu) { Run "remove the old 'Numpad Control' Start-menu entries" { Remove-Item -Recurse -Force $OldStartMenu } }
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
    Run "stop a running NumpadPilot (it restarts at the end)" { Stop-NumpadControl $Launcher }
    if (-not (Test-Path $VenvPython)) {
        Run "create the environment in $Dir\.venv" { & $Python -m venv (Join-Path $Dir ".venv"); Assert-Ok "Creating the Python environment" }
    }
    Run "install the Python packages" {
        & $VenvPython -m pip install --quiet --upgrade pip
        & $VenvPython -m pip install --quiet --upgrade -r (Join-Path $Dir "requirements.txt")
        Assert-Ok "Installing the Python packages"
    }

    # ---------------------------------------------------------------- 4. reading the numpad
    Step "4/6  Reading the numpad"
    $Dll = Join-Path $Dir "numpadctl\platform\interception.dll"
    $NeedsRestart = $false
    if (-not $Interception) {
        Note "no driver needed (Raw Input and a keyboard hook, like Discord's or OBS's hotkeys)"
        Run "use the built-in way to read the numpad" {
            [Environment]::SetEnvironmentVariable("NUMPADCTL_WINDOWS_BACKEND", $null, "User")
            Remove-Item Env:NUMPADCTL_WINDOWS_BACKEND -ErrorAction SilentlyContinue  # for the copy started below
        }
        if (Test-InterceptionDriver) {
            Note "The Interception driver from an earlier install isn't used any more. To remove it:"
            Note "run its 'install-interception.exe /uninstall' as administrator, then restart."
        }
    } elseif ((Test-Path $Dll) -and (Test-InterceptionDriver)) {
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
            Note "Windows will now ask for administrator permission and show 'Publisher: Unknown':"
            Note "that's Interception's installer (install-interception.exe) from its official GitHub"
            Note "release, which isn't signed (its drivers are). Click Yes to install it."
            Run "install the driver" {
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
    if ($Interception) {
        Run "read the numpad through Interception" {
            [Environment]::SetEnvironmentVariable("NUMPADCTL_WINDOWS_BACKEND", "interception", "User")
            $env:NUMPADCTL_WINDOWS_BACKEND = "interception"  # for the copy started below
        }
    }

    # ---------------------------------------------------------------- 5. shortcuts
    Step "5/6  Start menu"
    $Icon = Join-Path $Dir "numpad-control.ico"
    Run "draw the icon" {
        & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import draw_icon; draw_icon(256).save(r'$Icon', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])")
        Assert-Ok "Drawing the icon"
    }
    if (Test-Path $OldStartMenu) {
        Run "remove the old 'Numpad Control' Start-menu entries" { Remove-Item -Recurse -Force $OldStartMenu }
    }
    Run "add 'NumpadPilot' and 'NumpadPilot Settings' to the Start menu" {
        New-Item -ItemType Directory -Force $StartMenu | Out-Null
        New-Shortcut (Join-Path $StartMenu "NumpadPilot.lnk") $VenvPythonw "`"$Launcher`"" $Dir $Icon
        New-Shortcut (Join-Path $StartMenu "NumpadPilot Settings.lnk") $VenvPythonw "`"$Launcher`" gui" $Dir $Icon
    }

    # ---------------------------------------------------------------- 6. start
    Step "6/6  Starting"
    if (-not $NoAutostart) {
        Run "start NumpadPilot at login" {
            & $VenvPython -c ($InDir + "from numpadctl.platform.windows_tray import set_autostart; set_autostart(True)")
            Assert-Ok "Turning on start at login"
        }
    }
    if ($NeedsRestart) {
        Write-Host ""
        Warn "Restart the PC to finish installing the Interception driver."
        Note "After the restart NumpadPilot starts by itself (tray icon, bottom right)."
    } else {
        Run "start NumpadPilot now (look for its icon in the tray)" {
            Start-Process $VenvPythonw -ArgumentList "`"$Launcher`"" -WorkingDirectory $Dir
        }
        Write-Host ""
        Note "Done. Right-click the tray icon, or open 'NumpadPilot Settings' from the Start menu."
    }
}

# ---------------------------------------------------------------- the look and the menu
$Esc = [char]27

function Enable-Colors {
    # Windows PowerShell 5.1's console needs ANSI turned on; Windows Terminal and PowerShell 7 already have it.
    if ($env:NO_COLOR -or [Console]::IsOutputRedirected) { return $false }
    try {
        Add-Type -Namespace NumpadPilot -Name Console -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out int mode);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, int mode);
"@ -ErrorAction Stop
        $handle = [NumpadPilot.Console]::GetStdHandle(-11)
        $mode = 0
        if ([NumpadPilot.Console]::GetConsoleMode($handle, [ref]$mode)) { [void][NumpadPilot.Console]::SetConsoleMode($handle, $mode -bor 4) }
        try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
        return $true
    } catch { return $false }
}

function Show-Banner {
    $color = Enable-Colors
    $tile = if ($color) { "$Esc[48;2;124;78;127m" } else { "" }
    $key = if ($color) { "$Esc[48;2;255;255;255m" } else { "" }
    $ink = if ($color) { "$Esc[38;2;236;190;255m" } else { "" }
    $accent = if ($color) { "$Esc[1;38;2;236;190;255m" } else { "" }
    $dim = if ($color) { "$Esc[2m" } else { "" }
    $rst = if ($color) { "$Esc[0m" } else { "" }
    # The logo: a rounded tile with the numpad's keys (# = key), two characters wide per cell.
    $logo = @(".............", ".###.###.###.", ".###.###.###.", ".............", ".###.###.###.",
              ".###.###.###.", ".........###.", ".#######.###.", ".#######.###.", ".............")
    $font = @{
        S = @(" ####", "#    ", " ### ", "    #", "#### ")
        E = @("#####", "#    ", "#### ", "#    ", "#####")
        T = @("#####", "  #  ", "  #  ", "  #  ", "  #  ")
        U = @("#   #", "#   #", "#   #", "#   #", " ### ")
        P = @("#### ", "#   #", "#### ", "#    ", "#    ")
    }
    Write-Host ""
    for ($r = 0; $r -lt 10; $r++) {
        $line = "  "
        for ($c = 0; $c -lt 13; $c++) {
            $cell = $logo[$r][$c]
            if ($cell -eq "#") { $line += if ($color) { "$key  $rst" } else { [string][char]0x2588 * 2 } }
            elseif (($r -eq 0 -or $r -eq 9) -and ($c -eq 0 -or $c -eq 12)) { $line += "  " }   # the tile's rounded corners
            else { $line += if ($color) { "$tile  $rst" } else { [string][char]0x2591 * 2 } }
        }
        if ($r -ge 2 -and $r -le 6) {
            $text = ""
            foreach ($letter in "S", "E", "T", "U", "P") { $text += $font[$letter][$r - 2] + " " }
            $line += "    $ink" + $text.Replace("#", [string][char]0x2588) + $rst
        } elseif ($r -eq 8) {
            $line += "    ${accent}NumpadPilot${rst}${dim}  your `$10 numpad, now a control deck${rst}"
        }
        Write-Host $line
    }
    Write-Host ""
    return @{ Accent = $accent; Rst = $rst; Dim = $dim }
}

function Read-Action($look) {
    while ($true) {
        Write-Host "  $($look.Accent)Options:$($look.Rst)"
        foreach ($item in @(@("1", "Install"), @("2", "Uninstall"), @("3", "Reinstall / Update"), @("0", "Quit"))) {
            Write-Host "    $($look.Accent)[$($item[0])]$($look.Rst) $($item[1])"
        }
        Write-Host ""
        $choice = Read-Host "  Choose [0-3]"
        switch ($choice.Trim()) {
            "1" { return "install" }
            "2" { return "uninstall" }
            "3" { return "update" }
            { $_ -in "0", "q", "Q", "" } { return "quit" }
            default { Write-Host "`n  $($look.Dim)Please type 1, 2, 3 or 0.$($look.Rst)`n" }
        }
    }
}

# What to do: an option, or NUMPAD_ACTION / NUMPAD_UNINSTALL, or ask in the menu.
$action = $null
if ($args -contains "-Install") { $action = "install" }
elseif ($args -contains "-Uninstall" -or $env:NUMPAD_UNINSTALL) { $action = "uninstall" }
elseif ($args -contains "-Update") { $action = "update" }
elseif ($env:NUMPAD_ACTION) { $action = $env:NUMPAD_ACTION.ToLower() }
if (-not $action) {
    $look = Show-Banner
    $action = if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) { Read-Action $look } else { "install" }
}

$passed = @($args | Where-Object { $_ -notin "-Install", "-Uninstall", "-Update" })
switch ($action) {
    "install"   { Install-NumpadControl @passed -ScriptRoot $PSScriptRoot }
    "uninstall" { Install-NumpadControl @passed -Uninstall -ScriptRoot $PSScriptRoot }
    "update"    {
        Install-NumpadControl @passed -Uninstall -ScriptRoot $PSScriptRoot   # shortcuts and autostart; settings stay
        Install-NumpadControl @passed -ScriptRoot $PSScriptRoot
    }
    default     { Write-Host "  Nothing changed." }
}
