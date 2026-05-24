# Start DeckBridgeAgent in development mode

Fast iteration — no build, no install. Changes to Python files take effect on restart.

## Usage

```bash
cd /Users/juamejia/Andes/DeckBridgeAgent
./builds/dev-run.sh          # headless (fastest, console menu)
./builds/dev-run.sh --gui    # with menu bar / tray icon
./builds/dev-run.sh 9000     # custom port
```

## When to use
- **dev-run**: during active development to test changes quickly (~1s restart)
- **install.sh**: before a release or to test the full .app experience (~2-3min build)

## Stopping
Press `Ctrl+C` in the terminal running dev-run.sh.
