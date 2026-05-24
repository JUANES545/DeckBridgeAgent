; DeckBridge Windows Agent — Inno Setup installer script
; Version and OutputBaseFilename are patched by GitHub Actions before build.
;
; Requirements:
;   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;   - Built dist\DeckBridge\ folder (PyInstaller --onedir)
;
; Usage (from Windows, manual):
;   iscc builds\windows\DeckBridgeAgent.iss
;
; Automated: .github/workflows/release.yml patches version and runs ISCC.

[Setup]
AppName=DeckBridge Agent
AppVersion=1.5.0
AppPublisher=JUANES545
AppPublisherURL=https://github.com/JUANES545/DeckBridgeAgent
AppSupportURL=https://github.com/JUANES545/DeckBridgeAgent/issues
DefaultDirName={autopf}\DeckBridge Agent
DefaultGroupName=DeckBridge Agent
OutputDir=..\..\
OutputBaseFilename=DeckBridgeAgent-v1.5.0-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "..\..\dist\DeckBridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DeckBridge Agent"; Filename: "{app}\DeckBridge.exe"
Name: "{commondesktop}\DeckBridge Agent"; Filename: "{app}\DeckBridge.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el &escritorio"; GroupDescription: "Iconos adicionales:"

[Run]
Filename: "{app}\DeckBridge.exe"; Description: "Iniciar DeckBridge Agent"; Flags: nowait postinstall skipifsilent
