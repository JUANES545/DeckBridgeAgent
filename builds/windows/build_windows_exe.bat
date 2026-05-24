@echo off
REM Build a single-file Windows agent (requires Python 3.12+ on PATH as py -3.12).
REM Run this script from the repo root or double-click it from builds\windows\.

REM Resolve the repo root (two levels up from this script).
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Install Python 3.12 from https://www.python.org/ or: winget install Python.Python.3.12
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt pyinstaller

pyinstaller --onedir --windowed --name DeckBridge --clean ^
  --hidden-import=pairing_manager ^
  --hidden-import=agent_ux ^
  --hidden-import=session_file_log ^
  --hidden-import=pairing_console_qr ^
  --hidden-import=windows_tray ^
  --add-data "ui;ui" ^
  --add-data "CHANGELOG.md;." ^
  server.py

if errorlevel 1 exit /b 1
echo.
echo OK: dist\DeckBridge\DeckBridge.exe  (run this or place a shortcut on Desktop)
