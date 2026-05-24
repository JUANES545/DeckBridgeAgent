#!/usr/bin/env bash
# DeckBridge Mac Agent — Terminal launcher (fallback / developer mode)
# For the proper app experience, build with:  ./builds/mac/build_mac_app.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ ! -f ".venv/bin/python3" ]; then
  echo "First time? Run:  ./builds/mac/build_mac_app.sh"
  exit 1
fi
source .venv/bin/activate
exec python server.py "$@"
