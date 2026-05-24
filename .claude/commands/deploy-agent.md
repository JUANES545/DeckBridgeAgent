# Deploy DeckBridgeAgent to all platforms

Build and deploy the latest agent code to Mac and Windows. Includes pre-deploy review.

## Pre-deploy check (ALWAYS do this first)

1. Run `git status` — if there are uncommitted changes, ask the user if they want to commit first
2. Run `git log <last-tag>..HEAD --oneline` — show what will be deployed
3. Run `./builds/test-agent.sh` to verify current agents are healthy before replacing them
4. If tests fail, warn the user and ask for confirmation before proceeding

## Deploy (parallel)

### Mac
```bash
cd /Users/juamejia/Andes/DeckBridgeAgent
./builds/mac/install.sh
```

### Windows
```bash
ssh windows-pc '"C:\Program Files\Git\cmd\git.exe" -C Documents\Andes\DeckBridgeAgent pull'
ssh windows-pc "taskkill /f /im python.exe /im pythonw.exe 2>nul"
# Start headless for SSH verification
ssh windows-pc "set DECKBRIDGE_NO_GUI=1 && Documents\Andes\DeckBridgeAgent\.venv\Scripts\python.exe Documents\Andes\DeckBridgeAgent\server.py" &
```

## Post-deploy verification

Run `./builds/test-agent.sh` again and show results as table:

| Platform | Version | State | Tests |
|---|---|---|---|
| macOS | ... | ... | ✅/❌ |
| Windows | ... | ... | ✅/❌ |

## On issues
- If Windows SSH is down: `ssh windows-pc "Start-Service sshd"` first
- Remind user to double-click desktop shortcut for full tray experience on Windows
- Remind to re-grant Accessibility on Mac if rebuilt
