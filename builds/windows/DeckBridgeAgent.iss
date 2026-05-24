; DeckBridge Windows Agent — Inno Setup installer script
; TODO: implement when Windows installer is needed
;
; Requirements:
;   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;   - Built dist\DeckBridge\ folder from build_windows_exe.bat
;
; Usage (from Windows):
;   iscc builds\windows\DeckBridgeAgent.iss
;
; Output: DeckBridgeAgent-vX.Y.Z-Setup.exe

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
SetupIconFile=..\..\builds\mac\DeckBridgeMacAgent.icns
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
