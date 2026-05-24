#!/usr/bin/env bash
# DeckBridgeAgent — Fast dev run (NO build, NO install)
#
# Use this during active development to test changes instantly.
# Changes to Python files take effect on next restart (Ctrl+C + re-run).
#
# Usage:
#   ./builds/dev-run.sh              # headless, console menu active
#   ./builds/dev-run.sh --port 9000  # custom port
#
# For GUI testing (Mac menu bar + window):
#   ./builds/dev-run.sh --gui
#
# Full rebuild needed only before release or to test the .app bundle:
#   ./builds/mac/install.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f ".venv/bin/python" ]]; then
  echo "ERROR: .venv not found."
  echo "  Run once: pip install -r requirements.txt -r requirements-build.txt"
  exit 1
fi

# Default: headless (no rumps/pystray), console menu active
GUI=0
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--gui" ]]; then
    GUI=1
  else
    ARGS+=("$arg")
  fi
done

if [[ $GUI -eq 0 ]]; then
  export DECKBRIDGE_NO_GUI=1
  echo "🔧 Dev mode (headless) — menu bar/tray disabled. Use --gui to enable."
else
  echo "🔧 Dev mode (GUI) — menu bar / tray will appear."
fi

echo "   Agent: http://localhost:8765"
echo "   Press Ctrl+C to stop."
echo ""

exec .venv/bin/python server.py "${ARGS[@]:-}"
