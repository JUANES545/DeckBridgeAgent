# DeckBridgeMacAgent

Python LAN agent for **macOS**, protocol-compatible with the Windows agent under `DeckBridge/pc-lan-server` and the DeckBridge Android app.

## Run (desarrollo)

```bash
cd ~/Andes/DeckBridgeMacAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 server.py          # HTTP 8765, UDP discovery 8766
python3 server.py 9000     # custom HTTP port (discovery replies use this port)
```

## Ejecutable (doble clic, como el `.exe` en Windows)

1. Una vez en **Terminal** (desde esta carpeta):

   ```bash
   chmod +x build_mac_app.sh "DeckBridge Mac Agent.command"
   ./build_mac_app.sh
   ```

   Si pip sigue sin ver paquetes (`No matching distribution` / `versions: none`), suele ser un **`.venv` viejo** o **Python del sistema raro**. Prueba:

   ```bash
   ./build_mac_app.sh --recreate-venv
   ```

   O instala un Python estable (p. ej. `brew install python@3.12`) y vuelve a ejecutar el script (elige solo `python3.12` si está en el `PATH`).

2. En **Finder**: doble clic en **`DeckBridge Mac Agent.command`** — se abre Terminal y arranca el agente compilado con PyInstaller (`dist/DeckBridgeMacAgent/DeckBridgeMacAgent`).

En macOS no existe un `.exe` único idéntico a Windows; lo equivalente es un **binario firmable** más un **`.command`** para que el doble clic abra consola y veas logs (el `.app` sin consola suele ocultar la salida estándar).

**Gatekeeper**: si aparece “no se puede abrir porque proviene de un desarrollador no identificado”, clic derecho en el binario o en el `.command` → **Abrir** → confirmar. Para distribución seria haría falta firma con **Developer ID** y notarización.

**Permisos de accesibilidad**: tras el build, macOS puede pedir permisos para el **ejecutable dentro de `dist/…`** (no solo Terminal). Añade ese binario en **Privacidad y seguridad → Accesibilidad** (e **Input Monitoring** si aplica) si los atajos no llegan al sistema.

## macOS permissions

Input simulation uses **pynput**. Grant **Accessibility** and **Input Monitoring** for Terminal (or your IDE) in **System Settings → Privacy & Security**, or keystrokes will fail silently or with errors in logs.

## State & logs

- Pairing data: `~/.deckbridge/` (override with `DECKBRIDGE_STATE_DIR`)
- Session file logs: `~/.deckbridge/logs/deckbridge_mac_session_*.log`

## Protocol notes

- UDP `8766`, magic `DECKBRIDGE_DISCOVER_v1` → JSON `{ "ok", "ip", "port", "agent_os": "darwin" }`
- `GET /health` includes `agent_os` for the phone to correlate discovery vs host OS
- Pairing and `POST /action` match the Windows agent (`pc-lan-server`)

## Android

Deeplinks generados en esta Mac incluyen **`os=mac`**: la app puede poner el chip **macOS** sola antes del bootstrap LAN, y guardar host/puerto/token en el **slot Mac** (separado de Windows). Sigue pudiendo elegir el chip a mano si omites `os=` en un enlace antiguo.

Guía detallada: **[PAIRING_MACOS.md](./PAIRING_MACOS.md)** (QR primero, discovery como respaldo, permisos, casos borde).
