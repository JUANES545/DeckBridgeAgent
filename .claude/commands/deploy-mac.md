# Deploy DeckBridgeAgent to Mac

Build and install the latest DeckBridgeAgent on this Mac.

## Steps

1. Run `./builds/mac/install.sh` from the project root `/Users/juamejia/Andes/DeckBridgeAgent`
   - This pulls latest code, builds the .app with PyInstaller, installs in /Applications, opens the app
2. Wait for the agent to start (up to 10s)
3. Verify with `curl -s http://localhost:8765/api/status`
4. Report: version installed, state, any errors

## On success
Tell the user:
- Version running
- That the icon should appear in the menu bar
- Remind to re-grant Accessibility in System Settings if it was rebuilt
