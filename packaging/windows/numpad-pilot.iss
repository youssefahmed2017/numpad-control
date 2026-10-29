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
WizardStyle=modern dynamic
DisableWelcomePage=no
WizardSizePercent=115
WizardImageFile=wizard\side-164.bmp,wizard\side-246.bmp,wizard\side-328.bmp
WizardSmallImageFile=wizard\small-55.bmp,wizard\small-83.bmp,wizard\small-110.bmp
WizardImageFileDynamicDark=wizard\side-dark-164.bmp,wizard\side-dark-246.bmp,wizard\side-dark-328.bmp
WizardSmallImageFileDynamicDark=wizard\small-dark-55.bmp,wizard\small-dark-83.bmp,wizard\small-dark-110.bmp

[Messages]
WelcomeLabel1=Welcome to NumpadPilot
WelcomeLabel2=This sets up NumpadPilot, which turns a cheap USB numpad into a control deck for OBS, apps, media and macros.%n%nIt needs no administrator rights, and your settings stay when you update or remove it.
FinishedHeadingLabel=You're all set
FinishedLabel=NumpadPilot is installed. Plug in your numpad, open the settings and choose what each key does.
FinishedLabelNoIcons=NumpadPilot is installed. Plug in your numpad, open the settings and choose what each key does.

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
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\numpad-control.pyw"""; WorkingDir: "{app}"; Flags: nowait skipifsilent
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\numpad-control.pyw"" gui"; WorkingDir: "{app}"; Description: "Open the NumpadPilot settings"; Flags: nowait postinstall skipifsilent

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

function OldCopyFound(): Boolean;
begin
  Result := FileExists(ExpandConstant('{%USERPROFILE}\numpad-control\numpad-control.pyw'));
end;

// The wizard in the app's colours, light or dark like Windows (Inno's colours are blue-green-red:
// $FAF7FF is #fff7fa, $1F1F1F is #1f1f1f).
procedure InitializeWizard();
var
  Surface, Title: Integer;
begin
  if IsDarkInstallMode() then
  begin
    Surface := $1F1F1F;
    Title := $FFBEEC;
  end
  else
  begin
    Surface := $FAF7FF;
    Title := $7F4E7C;
  end;
  WizardForm.Color := Surface;
  WizardForm.InnerPage.Color := Surface;
  WizardForm.MainPanel.Color := Surface;
  WizardForm.WelcomePage.Color := Surface;
  WizardForm.FinishedPage.Color := Surface;
  WizardForm.Bevel.Visible := False;
  WizardForm.Bevel1.Visible := False;
  WizardForm.PageNameLabel.Font.Color := Title;
  WizardForm.WelcomeLabel1.Font.Color := Title;
  WizardForm.FinishedHeadingLabel.Font.Color := Title;
  if OldCopyFound() then
    WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 +
      'An older copy from the PowerShell installer was found. It will be stopped and removed; your settings stay.';
end;
