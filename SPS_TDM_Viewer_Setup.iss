; ============================================================================
; SPS_TDM_Viewer_Setup.iss - Inno Setup installer script for
; SPS TDM Image Viewer.
;
; HOW TO BUILD THE INSTALLER:
;   1. Install Inno Setup (free): https://jrsoftware.org/isdl.php
;   2. First build the app .exe:  run build.bat  (creates dist\SPS_TDM_Image_Viewer.exe)
;   3. Open this file in Inno Setup and click "Compile"
;      (or run from command line: ISCC.exe SPS_TDM_Viewer_Setup.iss)
;   4. The installer is created at: Output\SPS_TDM_Image_Viewer_Setup.exe
;
; Works on any Windows version from Windows 7 through Windows 11
; (32-bit and 64-bit) - nothing needs to be pre-installed on the target
; machine, the app .exe it installs is already fully self-contained.
; ============================================================================

#define MyAppName "SPS TDM Image Viewer"
#define MyAppVersion "vBeta"
#define MyAppPublisher "Swift-ProSys"
#define MyAppExeName "SPS_TDM_Image_Viewer.exe"

[Setup]
AppId={{3A7E1D9C-2F4B-4A6E-8D1C-9B5E3F7A2C61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SPS_TDM_Image_Viewer_Setup
Compression=lzma2
SolidCompression=yes
MinVersion=6.1
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=Swift_Prosys.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "fileassoc"; Description: "Open .sps files with {#MyAppName} by double-clicking them"; GroupDescription: "Additional shortcuts:"

[Files]
; --onedir build: copy the whole output folder (exe + its dependency
; files/DLLs) that PyInstaller creates at dist\SPS_TDM_Image_Viewer\
Source: "dist\SPS_TDM_Image_Viewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.sps"; ValueType: string; ValueName: ""; ValueData: "SPSImageFile"; Tasks: fileassoc; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\SPSImageFile"; ValueType: string; ValueName: ""; ValueData: "SPS Encrypted Image"; Tasks: fileassoc; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SPSImageFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\SPSImageFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
