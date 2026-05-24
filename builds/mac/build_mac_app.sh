#!/usr/bin/env bash
# Build a proper macOS .app bundle (PyInstaller windowed), same idea as Windows DeckBridgePcAgent.exe.
#
# Usage (from Terminal once):
#   chmod +x build_mac_app.sh
#   ./build_mac_app.sh
#
# Then in Finder: double-click DeckBridge.app (or: open dist/DeckBridge.app)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "--recreate-venv" ]]; then
  echo "==> Eliminando .venv (pedido por --recreate-venv) …"
  rm -rf .venv
  shift || true
fi

# PyPI explícito (evita índices vacíos si hay pip.conf corporativo o roto).
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_EXTRA=(--index-url "$PIP_INDEX_URL" --trusted-host pypi.org --trusted-host files.pythonhosted.org)

pick_python() {
  # PyInstaller suele ir bien con 3.10–3.13; evita depender de un solo `python3` del sistema.
  for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
      if "$cmd" -c 'import sys; assert sys.version_info[:2] >= (3, 10), "need 3.10+"' 2>/dev/null; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  echo ""
  return 1
}

PY="$(pick_python)" || {
  echo "ERROR: No encontré Python >= 3.10 (prueba: brew install python@3.12)." >&2
  exit 1
}

echo "==> Usando: $($PY --version) ($PY)"

VENV_PY="${ROOT}/.venv/bin/python3"
recreate_venv() {
  echo "==> Creando/actualizando .venv con pip reciente (--upgrade-deps) …"
  rm -rf .venv
  "$PY" -m venv .venv --upgrade-deps
  VENV_PY="${ROOT}/.venv/bin/python3"
}

if [[ ! -x "$VENV_PY" ]]; then
  recreate_venv
elif ! "$VENV_PY" -m pip --version &>/dev/null; then
  echo "==> pip roto dentro de .venv; recreando …"
  recreate_venv
else
  echo "==> venv existente: $VENV_PY"
fi

echo "==> Comprobando acceso a PyPI …"
if ! curl -sfI --connect-timeout 8 --max-time 15 "$PIP_INDEX_URL/pyinstaller/" | head -n1 | grep -qE 'HTTP/[0-9.]+ [23]'; then
  echo "WARN: No pude validar HTTPS contra $PIP_INDEX_URL (¿proxy/VPN/firewall?). Sigo con pip…"
fi

echo "==> Actualizando pip / setuptools / wheel …"
"$VENV_PY" -m pip install "${PIP_EXTRA[@]}" -q --upgrade "pip>=24.2" "setuptools>=69" "wheel>=0.44"

echo "==> Instalando dependencias del agente …"
if ! "$VENV_PY" -m pip install "${PIP_EXTRA[@]}" -q -r requirements.txt; then
  echo "ERROR: Falló pip install -r requirements.txt. Diagnóstico:" >&2
  "$VENV_PY" -m pip install "${PIP_EXTRA[@]}" -v -r requirements.txt || true
  exit 1
fi

echo "==> Instalando PyInstaller (build) …"
if ! "$VENV_PY" -m pip install "${PIP_EXTRA[@]}" -q -r requirements-build.txt; then
  echo "ERROR: Falló la instalación de PyInstaller." >&2
  echo "     Si usas Python muy nuevo (p. ej. 3.14), prueba con 3.12: brew install python@3.12" >&2
  echo "     Reintento en modo verbose:" >&2
  "$VENV_PY" -m pip install "${PIP_EXTRA[@]}" -v -r requirements-build.txt || true
  exit 1
fi

echo "==> PyInstaller — windowed .app bundle …"
"$VENV_PY" -m PyInstaller --noconfirm --clean \
  --windowed \
  --name DeckBridge \
  --icon "${ROOT}/DeckBridgeMacAgent.icns" \
  --osx-bundle-identifier com.juanes545.deckbridge \
  --hidden-import=pairing_manager \
  --hidden-import=agent_ux \
  --hidden-import=pairing_qr_popup \
  --hidden-import=session_file_log \
  --hidden-import=pairing_console_qr \
  --hidden-import=macos_accessibility \
  --hidden-import=macos_menubar \
  --hidden-import=macos_window \
  --hidden-import=macos_audio \
  --hidden-import=mac_bridge_client \
  --hidden-import=rumps \
  --hidden-import=webview \
  --add-data "${ROOT}/ui:ui" \
  --add-data "${ROOT}/builds/mac/menubar_template.png:builds/mac" \
  --collect-all tkinter \
  --collect-all rumps \
  server.py

PLIST="${ROOT}/dist/DeckBridge.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
  echo "==> Patching Info.plist — LSUIElement (no Dock icon) …"
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST"
  echo "    LSUIElement = true (app runs as menu-bar-only, no Dock)"
fi

echo ""
echo "OK — app bundle built:"
echo "  • App:      ${ROOT}/dist/DeckBridge.app"
echo "  • Launch:   open ${ROOT}/dist/DeckBridge.app"
echo ""
echo "First run: if macOS blocks it, right-click → Open, then confirm."
echo "Grant Accessibility in System Settings → Privacy & Security → Accessibility."
