; Inno Setup script for NumpadPilot (built by build-installer.ps1, which passes AppVersion and BuildDir).
; A per-user install: no administrator prompt, uninstall from Settings -> Apps.

#define AppName "NumpadPilot"

[Setup]
AppId={{276E655D-0D17-4786-99FA-B4F2C232FEFB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Youssef Ahmed
AppPublisherURL=https://github.com/youssefahmed2017/numpad-pilot
AppSupportURL=https://github.com/youssefahmed2017/numpad-pilot/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
LicenseFile={#BuildDir}\app\LICENSE
SetupIconFile={#BuildDir}\app\assets\numpad-pilot.ico
UninstallDisplayIcon={app}\assets\numpad-pilot.ico
OutputDir={#BuildDir}
OutputBaseFilename=NumpadPilot-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "remove-old.ps1"; Flags: dontcopy
Source: "{#BuildDir}\app\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
Name: "autostart"; Description: "Start NumpadPilot when I sign in"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\numpad-control.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\numpad-pilot.ico"
Name: "{autoprograms}\{#AppName} Settings"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\numpad-control.pyw"" gui"; WorkingDir: "{app}"; IconFilename: "{app}\assets\numpad-pilot.ico"

[Run]
Filename: "{app}\python\python.exe"; Parameters: "-c ""from numpadctl.platform.windows_tray import set_autostart; set_autostart(True)"""; WorkingDir: "{app}"; Flags: runhidden; Tasks: autostart
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\numpad-control.pyw"""; WorkingDir: "{app}"; Description: "Start NumpadPilot now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\python\python.exe"; Parameters: "-c ""from numpadctl.platform.windows_tray import set_autostart; set_autostart(False)"""; WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "NoAutostart"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// A copy put here by the old PowerShell installer (setup.ps1) would run next to this one, so find it,
// stop it and remove it first. Settings stay (they live in %APPDATA%\numpad-control).
procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssInstall then
  begin
    ExtractTemporaryFile('remove-old.ps1');
    Exec('powershell.exe',
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        ExpandConstant('{tmp}\remove-old.ps1') + '" -NewDir "' + ExpandConstant('{app}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;
