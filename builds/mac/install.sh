#!/usr/bin/env bash
# DeckBridge Mac Agent — Build, Install & (optionally) create DMG
#
# Uso:
#   ./builds/mac/install.sh            # build + install en /Applications
#   ./builds/mac/install.sh --release  # build + install + crear DMG para distribución
set -euo pipefail

RELEASE_MODE=false
[[ "${1:-}" == "--release" ]] && RELEASE_MODE=true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     DeckBridge Mac Agent — Installer     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Pull latest code ──────────────────────────────────────────────────────
echo "==> Actualizando código …"
if /usr/bin/git -C "$ROOT" diff --quiet HEAD 2>/dev/null; then
  /usr/bin/git -C "$ROOT" pull --ff-only origin master 2>&1 | grep -E "Already|Fast-forward|->|error" || true
else
  echo "    WARN: cambios locales sin commit — omitiendo pull"
fi

# ── 2. Build .app ────────────────────────────────────────────────────────────
echo ""
echo "==> Construyendo DeckBridge.app …"
chmod +x "${SCRIPT_DIR}/build_mac_app.sh"
"${SCRIPT_DIR}/build_mac_app.sh"

# ── 3. Stop running instance ─────────────────────────────────────────────────
echo ""
echo "==> Deteniendo instancia anterior …"
pkill -f "DeckBridge" 2>/dev/null && sleep 1 || true

# ── 4. Install in /Applications using ditto ──────────────────────────────────
echo "==> Instalando en /Applications …"
rm -rf /Applications/DeckBridge.app 2>/dev/null || true
ditto "${ROOT}/dist/DeckBridge.app" /Applications/DeckBridge.app
echo "    Instalado OK"

# ── 5. Clean dist ────────────────────────────────────────────────────────────
rm -rf "${ROOT}/dist/DeckBridge.app" "${ROOT}/dist/DeckBridge"

# ── 6. Remove quarantine flag (avoids Gatekeeper block on first launch) ──────
echo "==> Removiendo cuarentena de Gatekeeper …"
xattr -dr com.apple.quarantine /Applications/DeckBridge.app 2>/dev/null || true

# ── 7. Launch ────────────────────────────────────────────────────────────────
echo "==> Abriendo DeckBridge …"
open /Applications/DeckBridge.app
sleep 2

echo ""
echo "✓  DeckBridge está corriendo."
echo "   Busca el ícono  🎛  en la barra de menús (arriba a la derecha)."
echo ""
echo "   Primera vez: activa Accesibilidad para que los atajos funcionen:"
echo "   Sistema → Privacidad y Seguridad → Accesibilidad → activa DeckBridge"
echo ""

# ── 8. Build DMG (solo en modo --release) ────────────────────────────────────
if [[ "$RELEASE_MODE" == "true" ]]; then
  echo "==> Construyendo DMG para distribución …"

  # Re-build the .app if it was cleaned (install cleaned dist/)
  if [[ ! -d "${ROOT}/dist/DeckBridge.app" ]]; then
    chmod +x "${SCRIPT_DIR}/build_mac_app.sh"
    "${SCRIPT_DIR}/build_mac_app.sh"
  fi

  chmod +x "${SCRIPT_DIR}/build_dmg.sh"
  "${SCRIPT_DIR}/build_dmg.sh"
fi
