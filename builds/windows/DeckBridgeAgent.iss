; DeckBridge Windows Agent — Inno Setup installer script
; Version and OutputBaseFilename are patched by GitHub Actions before build.
;
; Requirements:
;   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;   - Built dist\DeckBridge\ folder (PyInstaller --onedir --windowed)
;
; Usage (from Windows, manual):
;   iscc builds\windows\DeckBridgeAgent.iss
;
; Automated: .github/workflows/release.yml patches version and runs ISCC.

#define AppName    "DeckBridge"
#define AppVersion "1.7.0"
#define AppExe     "DeckBridge.exe"
#define Publisher  "JUANES545"
#define AppURL     "https://github.com/JUANES545/DeckBridgeAgent"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
; Installs per-user (no UAC prompt needed)
DefaultDirName={userappdata}\DeckBridge
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\
OutputBaseFilename=DeckBridgeAgent-v{#AppVersion}-Setup
SetupIconFile=..\..\builds\windows\DeckBridge.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
; No UAC — installs in %APPDATA%\DeckBridge
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
; Prevent running two instances
AppMutex=DeckBridgeAgentMutex

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; App bundle (PyInstaller onedir)
Source: "..\..\dist\DeckBridge\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; Icon for shortcuts
Source: "..\..\builds\windows\DeckBridge.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\DeckBridge.ico"; Comment: "DeckBridge macro deck agent"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional)
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\DeckBridge.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon";    Description: "Crear acceso directo en el &escritorio"; \
  GroupDescription: "Opciones adicionales:"; Flags: unchecked
Name: "autostart";      Description: "Iniciar {#AppName} al arrancar Windows"; \
  GroupDescription: "Opciones adicionales:"

[Registry]
; Auto-start at login (HKCU — no admin needed)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExe}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Launch after install
Filename: "{app}\{#AppExe}"; \
  Description: "Iniciar {#AppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the agent before uninstalling
Filename: "taskkill"; Parameters: "/f /im {#AppExe}"; \
  Flags: runhidden; RunOnceId: "StopAgent"

; Note: running instance is stopped by [UninstallRun] on upgrade/uninstall.
