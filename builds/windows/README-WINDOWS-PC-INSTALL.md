# DeckBridge PC — agente LAN (Windows)

Este paquete vive en tu PC (por ejemplo `C:\Users\PC\Documents\Andes\DeckBridgePc`). **No es la app Android**: es el servidor HTTP que escucha en el puerto **8765** y simula teclas (Copiar/Pegar, etc.).

## Ejecutar

1. Doble clic en **`DeckBridgePcAgent.exe`** (o en el acceso directo del escritorio **DeckBridge PC Agent**).
2. Deja la ventana de consola abierta; verás el mensaje de que el servidor está en marcha.
3. Si Windows Firewall pregunta, permite conexiones **privadas** en la red local.

## Conectar el móvil (DeckBridge Android)

1. El teléfono y el PC deben estar en la **misma Wi‑Fi**.
2. En el PC, averigua tu IPv4 (PowerShell: `ipconfig` → adaptador Wi‑Fi, algo como `192.168.1.x`).
3. En el móvil: **Ajustes → PC over LAN (prototype)** → canal **LAN / Wi‑Fi** → escribe esa **IPv4**, puerto **8765** → **Guardar dirección** → **Probar conexión (GET /health)**.
4. En la pantalla principal, plataforma **Windows**; pulsa **Copiar** / **Pegar** en el deck.

## Seguridad

Sin autenticación: cualquiera en tu LAN que conozca la IP y el puerto puede enviar acciones. Usa solo redes de confianza.

## Reconstruir el `.exe`

Con Python 3.12 instalado:

```bat
build_windows_exe.bat
```

O manualmente: `pip install -r requirements.txt pyinstaller` y `pyinstaller --onefile --console --name DeckBridgePcAgent server.py`, luego copia `dist\DeckBridgePcAgent.exe` a esta carpeta.

## API HTTP

- `GET http://<IP>:8765/health` → `{"ok": true}`
- `POST http://<IP>:8765/action` con cuerpo JSON `{"type":"combo","keys":["ctrl","c"]}`
