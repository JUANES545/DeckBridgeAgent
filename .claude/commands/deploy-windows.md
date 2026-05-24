# Deploy DeckBridgeAgent to Windows PC

Deploy the latest code to the Windows PC via SSH and restart the agent.

## Steps

1. SSH pull: `ssh windows-pc '"C:\Program Files\Git\cmd\git.exe" -C Documents\Andes\DeckBridgeAgent pull'`
2. Kill running agent: `ssh windows-pc "taskkill /f /im python.exe /im pythonw.exe 2>nul"`
3. Start agent (headless for SSH testing):
   `ssh windows-pc "set DECKBRIDGE_NO_GUI=1 && Documents\Andes\DeckBridgeAgent\.venv\Scripts\python.exe Documents\Andes\DeckBridgeAgent\server.py" &`
4. Wait 5s then verify: `curl -s http://192.168.1.29:8765/api/status`
5. Report: version, state, last actions

## Notes
- pystray tray icon only works from desktop session (not SSH) — tell user to double-click desktop shortcut for full experience
- If SSH is down: tell user to run `Start-Service sshd` in PowerShell admin
- Windows PC LAN: 192.168.1.29 | Tailscale: 100.65.234.99
