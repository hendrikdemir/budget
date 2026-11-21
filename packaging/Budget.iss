; Inno Setup recipe for the Windows installer (dist\Budget-setup.exe). Built by build-windows.ps1,
; which passes the version: iscc /DVersion=0.9.0 packaging\Budget.iss
; Installs for the current user only (no administrator needed) in %LOCALAPPDATA%\Programs\Budget,
; with a Start menu entry and an uninstaller under Settings > Apps. The data in %APPDATA%\Budget is
; never touched, so updating or uninstalling keeps it, just like on the Mac.

#ifndef Version
  #error Pass the version: iscc /DVersion=x.y.z
#endif

[Setup]
; The AppId identifies Budget to Windows across versions; never change it.
AppId={{6E0B5C3A-2F4D-4C1B-9E8A-7D3F1B2A9C64}
AppName=Budget
AppVersion={#Version}
AppVerName=Budget {#Version}
AppPublisher=Hendrik Demir
AppPublisherURL=https://github.com/hendrikdemir/budget
AppSupportURL=https://github.com/hendrikdemir/budget/issues
AppUpdatesURL=https://github.com/hendrikdemir/budget/releases
VersionInfoVersion={#Version}
PrivilegesRequired=lowest
DefaultDirName={autopf}\Budget
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UninstallDisplayIcon={app}\Budget.exe
UninstallDisplayName=Budget
SetupIconFile=icon.ico
OutputDir=..\dist
OutputBaseFilename=Budget-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Updating: close a running Budget first, and start it again afterwards.
CloseApplications=yes
RestartApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
; The whole app folder from PyInstaller. Old files are removed first, so an update never mixes versions.
Source: "..\dist\Budget\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Budget"; Filename: "{app}\Budget.exe"
Name: "{autodesktop}\Budget"; Filename: "{app}\Budget.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Budget.exe"; Description: "Open Budget"; Flags: nowait postinstall skipifsilent
