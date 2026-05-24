# Deploy DeckBridgeAgent to all platforms

Deploy the latest agent code to both Mac and Windows simultaneously.

## Steps (run in parallel)

### Mac
1. Run `./builds/mac/install.sh` from `/Users/juamejia/Andes/DeckBridgeAgent`
2. Verify with `curl -s http://localhost:8765/api/status`

### Windows
1. `ssh windows-pc '"C:\Program Files\Git\cmd\git.exe" -C Documents\Andes\DeckBridgeAgent pull'`
2. Restart agent (kill + start with DECKBRIDGE_NO_GUI=1)
3. Verify with `curl -s http://192.168.1.29:8765/api/status`

## Report
Show a summary table:
| Platform | Version | State | Status |
|---|---|---|---|
| macOS | ... | ... | ✅/❌ |
| Windows | ... | ... | ✅/❌ |
