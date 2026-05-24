#!/usr/bin/env bash
# DeckBridge Mac Agent — Build & Install
#
# Pulls latest code, builds DeckBridge.app and installs it in /Applications.
# Run once from Terminal:
#   chmod +x builds/mac/install.sh
#   ./builds/mac/install.sh
#
# Or double-click builds/mac/Install DeckBridge.command (if it exists)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     DeckBridge Mac Agent — Installer     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Pull latest code ──────────────────────────────────────────────────────
echo "==> Actualizando desde git …"
GIT_BIN="/usr/bin/git"
if ! "$GIT_BIN" -C "$ROOT" diff --quiet HEAD 2>/dev/null; then
  echo "    WARN: hay cambios locales sin commit — se omite el pull"
else
  "$GIT_BIN" -C "$ROOT" pull --ff-only origin master 2>&1 \
    && echo "    Pull OK" \
    || echo "    WARN: pull falló (continuando con versión local)"
fi

# ── 2. Build .app ────────────────────────────────────────────────────────────
echo ""
echo "==> Construyendo DeckBridge.app …"
chmod +x "${SCRIPT_DIR}/build_mac_app.sh"
"${SCRIPT_DIR}/build_mac_app.sh"

# ── 3. Stop running instance ─────────────────────────────────────────────────
echo ""
echo "==> Deteniendo instancia anterior …"
pkill -f "DeckBridge" 2>/dev/null && sleep 1 && echo "    Detenido" || echo "    No había instancia corriendo"

# ── 4. Install in /Applications ──────────────────────────────────────────────
echo ""
echo "==> Instalando en /Applications …"
rm -rf /Applications/DeckBridge.app 2>/dev/null || true
ditto "${ROOT}/dist/DeckBridge.app" /Applications/DeckBridge.app
echo "    Instalado OK"

# ── 5. Clean dist ────────────────────────────────────────────────────────────
rm -rf "${ROOT}/dist/DeckBridge.app"
echo "    dist/ limpiado"

# ── 6. Launch ────────────────────────────────────────────────────────────────
echo ""
echo "==> Abriendo DeckBridge …"
open /Applications/DeckBridge.app
sleep 2
echo ""
echo "✓  DeckBridge está corriendo. Busca el ícono en la barra de menús ↗"
echo ""
echo "   Primera vez: si macOS bloquea la app → clic derecho → Abrir → confirmar"
echo "   Accesibilidad: Sistema → Privacidad → Accesibilidad → activa DeckBridge"
echo ""
