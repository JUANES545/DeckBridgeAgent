#!/usr/bin/env bash
# DeckBridge Mac Agent — Build DMG installer for distribution
#
# Usage:
#   ./builds/mac/build_dmg.sh <version>        # e.g. 1.5.0
#   ./builds/mac/build_dmg.sh                  # reads version from CHANGELOG.md
#
# Output: DeckBridge-v<version>.dmg  (in project root)
# Requires: create-dmg (brew install create-dmg) + a built dist/DeckBridge.app

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$ROOT"

# ── Version ──────────────────────────────────────────────────────────────────
if [[ "${1:-}" != "" ]]; then
  VERSION="$1"
else
  VERSION=$(grep -m1 '## \[' CHANGELOG.md | sed 's/.*\[\(.*\)\].*/\1/')
fi
[[ -z "$VERSION" ]] && { echo "ERROR: could not determine version"; exit 1; }
echo "Version: $VERSION"

APP="dist/DeckBridge.app"
DMG_OUT="DeckBridge-v${VERSION}.dmg"
BACKGROUND="packaging/dmg_background.png"
STAGING="dmg_staging_$$"

# ── Checks ────────────────────────────────────────────────────────────────────
[[ -d "$APP" ]] || { echo "ERROR: $APP not found — run build_mac_app.sh first"; exit 1; }
[[ -f "$BACKGROUND" ]] || { echo "ERROR: $BACKGROUND not found"; exit 1; }

if ! command -v create-dmg &>/dev/null; then
  echo "==> Installing create-dmg via Homebrew …"
  brew install create-dmg
fi

# ── Staging ───────────────────────────────────────────────────────────────────
echo "==> Preparing staging …"
rm -rf "$STAGING"
mkdir "$STAGING"
ditto "$APP" "$STAGING/DeckBridge.app"
xattr -cr "$STAGING/DeckBridge.app" 2>/dev/null || true   # strip quarantine

# ── Build DMG ────────────────────────────────────────────────────────────────
echo "==> Building DMG …"
[[ -f "$DMG_OUT" ]] && rm "$DMG_OUT"

create-dmg \
  --volname "DeckBridge ${VERSION}" \
  --volicon "${SCRIPT_DIR}/DeckBridgeMacAgent.icns" \
  --background "$BACKGROUND" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --icon "DeckBridge.app" 200 185 \
  --hide-extension "DeckBridge.app" \
  --app-drop-link 600 185 \
  --skip-jenkins \
  "$DMG_OUT" \
  "$STAGING/"

# ── Cleanup ───────────────────────────────────────────────────────────────────
rm -rf "$STAGING"

echo ""
echo "✓  DMG creado: ${ROOT}/${DMG_OUT}"
echo "   Sube al GitHub Release:"
echo "   gh release upload v${VERSION} ${DMG_OUT} --repo JUANES545/DeckBridgeAgent"
echo ""
