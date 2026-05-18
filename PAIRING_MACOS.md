# Vinculación recomendada: Android ↔ Mac (DeckBridgeMacAgent)

## Flujo principal (recomendado)

1. **En la Mac:** arranca el agente (`python3 server.py`, el `.command`, o el binario PyInstaller).
2. **En la Mac:** en la consola del agente, pulsa **`z`** (host QR invite).
3. Verás:
   - un **QR en ASCII** en la terminal (siempre que exista el paquete `qrcode`);
   - un **deeplink** `deckbridge://pair?...&os=mac` (incluye `os=mac` para que Android elija el **slot Mac** antes del bootstrap);
   - si Tk funciona: una **ventana** con el QR en alta resolución.
4. **En Android:** Conectar → escanear el QR (o el de la ventana).
5. Android hace **claim** de la sesión, muestra el código; en la Mac pulsa **`a`** para aprobar (o usa el `curl` que imprime el agente).
6. El **token** queda en el slot **Mac** (separado del slot Windows en la app).
7. **Discovery UDP** queda como **complemento** (misma LAN, sin QR) o si el QR no es práctico.

## Fallbacks

| Situación | Qué hacer |
|-----------|-----------|
| Sin ventana Tk (SSH, PyInstaller sin Tcl) | Usa el **QR ASCII** en terminal o copia el **deeplink** a un generador QR externo / “Compartir” desde notas. |
| Sin `qrcode` | `pip install -r requirements.txt` en el venv. |
| Sesión expirada / cancelada | Vuelve a pulsar **`z`** (nueva sesión). |
| Mismo QR escaneado dos veces | Tras `consumed` la sesión muere; genera otro con **`z`**. |
| Android ya vinculado a Windows | No importa: el deeplink **`os=mac`** fuerza el slot Mac antes de guardar host/token de esta Mac. |
| Trust inválido en Android | En Ajustes / flujo Conectar, “olvidar” enlace LAN o re-emparejar; el agente puede **`u`** (unpair). |

## Permisos macOS (importante)

- **Emparejamiento y `/health`:** solo red **local**; **no** requieren Accesibilidad.
- **Acciones del deck (pynput):** requieren **Privacidad y seguridad → Accesibilidad** (y a veces **Monitoreo de entrada**) para el proceso que ejecuta el agente: **Terminal**, **Cursor/IDE**, o el binario **`dist/DeckBridgeMacAgent/DeckBridgeMacAgent`** si usas PyInstaller.

Al arrancar, el agente escribe en log si **Accessibility** no está concedida (`deckbridge.macos`), para no confundir “pairing falla” con “faltan permisos de teclado”.

## Binario vs `python3`

El mismo flujo **`z`** aplica. Si el QR en ventana falla solo en el binario, recompila con `./build_mac_app.sh` (incluye `--collect-all tkinter`) o ejecuta desde **Homebrew Python** con `python-tk` instalado.

## Logs útiles (filtrado)

- Mac (stderr / sesión): `deckbridge.qr_popup`, `deckbridge.pairing_http`, `deckbridge.console_qr`, `deckbridge.macos`
- Android: `adb logcat -s DeckBridge | grep QR`
