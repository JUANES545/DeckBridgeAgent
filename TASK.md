# TASK — DeckBridge Mac Agent: Native macOS App Experience

**Estado:** 🟡 En refinamiento — NO implementar hasta que el estado sea ✅ Aprobado
**Última actualización:** 2026-05-23
**Referencia visual:** Elgato Stream Deck, Logitech Options+, Tailscale macOS app

> **Hallazgos clave de investigación (Stream Deck + patrones macOS nativos):**
> - Stream Deck es 100% menu bar app — **sin ícono en el Dock** (`LSUIElement = true` en Info.plist)
> - El ícono de la barra de menús es una **template image** monocromática — macOS lo invierte automáticamente en modo claro/oscuro
> - El menú desplegable de Stream Deck es **minimalista**: Open, Profiles submenu, Quit — el estado va en la ventana, no en el menú
> - La ventana de configuración sigue el patrón: **barra superior** (device selector, profile selector, gear) + **grid central** + **panel lateral** de acciones
> - Preferencias en tabs: General | Perfiles | Dispositivos | Avanzado
> - **Empty state**: si el dispositivo está desconectado, la ventana muestra el último layout en gris con banner "Dispositivo no encontrado" — no borra nada
> - Login item: via `LaunchAgent` plist, no toggle en la app

---

## Objetivo final

Transformar el agente Mac de una app de terminal (`.command` + ventana de consola)
a una **aplicación nativa de macOS** con:

1. **Ícono en la barra de menús** (top right) — el agente corre en segundo plano sin ventanas visibles
2. **Menú desplegable nativo** al hacer clic en el ícono — acciones rápidas y estado
3. **Ventana principal "DeckBridge"** — abierta desde el menú, muestra estado, configuración y diagnósticos con UI nativa
4. **Bundle `.app` real** — no más `.command`, instalable como cualquier app macOS

---

## Experiencia de usuario (flujo objetivo)

### Primera vez
```
1. Usuario descarga DeckBridge.app desde GitHub Releases
2. Doble-clic → app se inicia, NO abre Terminal
3. Ícono 🎛️ aparece en la barra de menús (top-right)
4. macOS puede pedir permisos de Accesibilidad → diálogo nativo (ya existe)
5. Usuario hace clic en el ícono → ve menú con "Sin dispositivo pareado"
6. Clic en "Parear con Android..." → ventana con código QR
7. Usuario escanea desde la app Android → conexión establecida
8. Ícono cambia a verde 🟢, menú muestra el nombre del dispositivo
```

### Uso diario
```
1. DeckBridge.app arranca automáticamente con el Mac (login item, opcional)
2. Ícono en barra de menús — un vistazo confirma que está conectado
3. Clic → menú con estado + acceso rápido a la ventana principal
4. La ventana principal se puede abrir/cerrar libremente sin parar el agente
5. Cerrar la ventana = minimizar a barra de menús (no quita el agente)
6. Salir = opción explícita en el menú
```

---

## Menú desplegable (especificación)

Patrón Stream Deck: **minimalista** — el estado detallado vive en la ventana, el menú es solo acceso rápido.

```
┌────────────────────────────────┐
│ DeckBridge                     │  ← header no-interactivo (app name)
│ 🟢 iPhone de Juan              │  ← estado dinámico (1 línea, no-interactivo)
│   192.168.1.29                 │  ← LAN IP del Mac (no-interactivo)
├────────────────────────────────┤
│ Abrir DeckBridge...            │  ← abre/trae la ventana principal
├────────────────────────────────┤
│ Parear con Android...          │  ← abre ventana QR (deshabilitado si ya pareado)
│ Olvidar dispositivo            │  ← unpair (deshabilitado si no hay)
├────────────────────────────────┤
│ Salir de DeckBridge            │
└────────────────────────────────┘
```

**Estados del ícono (template image — monocromático):**
- Template normal = sin parear / idle / desconectado
- Template con badge verde = dispositivo conectado y activo
- Template con badge amarillo = pareado pero sin actividad reciente
- Template con badge rojo = error de accesibilidad o fallo de arranque

> **Nota de implementación:** `NSStatusItem` con `isTemplate = true` en la imagen.
> El badge de color se dibuja programáticamente sobre la template image.

---

## Ventana principal — secciones

Referencia visual: Tailscale + Elgato Stream Deck (sidebar izquierda + panel derecho)

```
┌──────────────────────────────────────────────────────────┐
│  [ícono]  DeckBridge                          [·][□][×]  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ESTADO DE CONEXIÓN                                      │
│  ┌──────────────────────────────────────────────────┐   │
│  │  🟢  Conectado          iPhone de Juan           │   │
│  │      LAN 192.168.1.29 · puerto 8765              │   │
│  │      Última acción: hace 12 s                    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ACCIONES RÁPIDAS                                        │
│  ┌────────────────┐  ┌────────────────┐                 │
│  │  📱 Parear     │  │  🔗 QR deeplink│                 │
│  └────────────────┘  └────────────────┘                 │
│                                                          │
│  SALIDAS DE AUDIO  (macOS)                               │
│  ○ MacBook Pro Speakers          [activo]                │
│  ○ AirPods Pro                                           │
│  ○ LG OLED (HDMI)                                        │
│                                                          │
│  DIAGNÓSTICOS                                            │
│  Últimas acciones recibidas:                             │
│  ✓  14:32:11  combo [ctrl+c]                             │
│  ✓  14:31:58  media vol_up                               │
│  ✓  14:31:45  key enter                                   │
│                                                          │
│  ─────────────────────────────────────────────────────  │
│  v1.2.0 · Accesibilidad ✓ · UDP 8766 ✓                  │
└──────────────────────────────────────────────────────────┘
```

### Secciones detalladas

| Sección | Contenido | Interactivo |
|---|---|---|
| **Estado de conexión** | Dispositivo pareado, IP, puerto, tiempo desde última acción | No (solo lectura) |
| **Acciones rápidas** | Botón "Parear con Android" (abre QR), "Copiar QR deeplink", "Olvidar dispositivo" | Sí |
| **Salidas de audio** | Lista de dispositivos CoreAudio con radio buttons — clic cambia la salida activa | Sí (v2) |
| **Diagnósticos** | Últimas 10 acciones recibidas con timestamp y resultado | No (solo lectura) |
| **Footer** | Versión, estado Accesibilidad, estado UDP discovery | No (solo lectura) |

---

## Especificación técnica

### Librería de menú: `rumps`

`rumps` es el estándar para menu bar apps en Python/macOS.
Requiere ser el **main thread** (NSApplication loop).

**Cambio de arquitectura en `server.py` main():**
```
ACTUAL:   httpd.serve_forever()   ← bloquea main thread
NUEVO:    threading.Thread(target=httpd.serve_forever).start()
          rumps_app.run()         ← toma el main thread
```

### Librería de ventana: `tkinter` (ya incluida)

Tkinter ya está en el proyecto (usado para QR popup). La ventana principal
puede construirse con `tkinter.Toplevel` + `ttk` para un look más limpio.
En el futuro puede migrarse a PyObjC/AppKit para UI 100% nativa.

### Módulos nuevos

| Módulo | Responsabilidad |
|---|---|
| `macos_menubar.py` | `rumps.App` subclass — ícono, menú, callbacks de estado |
| `macos_main_window.py` | Ventana principal Tkinter — secciones, actualización de estado |

### Módulos modificados

| Módulo | Cambio |
|---|---|
| `agent_ux.py` | `AgentUx.start_ui()` detecta plataforma: macOS → rumps, otro → stdin_loop |
| `server.py` | `httpd.serve_forever()` pasa a thread; `rumps_app.run()` toma el main thread |
| `requirements.txt` | agregar `rumps>=0.4.0; sys_platform=="darwin"` |
| `builds/mac/build_mac_app.sh` | `--windowed` + `--osx-bundle-identifier` para `.app` real |

### `.app` bundle (PyInstaller)

```bash
pyinstaller --windowed \          # no Terminal visible
  --name DeckBridge \             # nombre del .app
  --icon builds/mac/DeckBridgeMacAgent.icns \
  --osx-bundle-identifier com.juanes545.deckbridge \
  --hidden-import=rumps \
  ...
  server.py
```

---

## Tareas de implementación (backlog ordenado)

> ⚠️ No ejecutar hasta estado = ✅ Aprobado

### Fase 1 — Menu bar funcional (sin ventana)
- [ ] **T1.1** Agregar `rumps` a `requirements.txt` con marker de plataforma
- [ ] **T1.2** Crear `macos_menubar.py`: `DeckBridgeMenuBar(rumps.App)` con menú estático
- [ ] **T1.3** Conectar callbacks de estado: `update_status(label, device_name, lan_ip)`
- [ ] **T1.4** Mover `httpd.serve_forever()` a thread en `server.py`, correr rumps en main
- [ ] **T1.5** Probar: agente arranca, ícono aparece, menú responde, HTTP sigue funcionando
- [ ] **T1.6** Mantener `stdin_loop` como fallback cuando no hay GUI disponible

### Fase 2 — Ventana principal (UI básica)
- [ ] **T2.1** Crear `macos_main_window.py`: ventana Tkinter con secciones
- [ ] **T2.2** Sección "Estado de conexión" — datos en tiempo real
- [ ] **T2.3** Sección "Acciones rápidas" — botones Parear / Copiar deeplink / Olvidar
- [ ] **T2.4** Sección "Diagnósticos" — lista últimas 10 acciones (cola en `AgentUx`)
- [ ] **T2.5** Footer con versión + estado de accesibilidad + UDP
- [ ] **T2.6** Conectar menú "Abrir DeckBridge..." a esta ventana
- [ ] **T2.7** Cerrar ventana = ocultar (no destruir), el agente sigue corriendo

### Fase 3 — Audio outputs interactivo
- [ ] **T3.1** Sección "Salidas de audio" con radio buttons desde `macos_audio`
- [ ] **T3.2** Clic en salida → llama `set_default_output(uid)`
- [ ] **T3.3** Observer de cambios actualiza la UI en tiempo real

### Fase 4 — `.app` bundle real
- [ ] **T4.1** Actualizar `build_mac_app.sh` a `--windowed`
- [ ] **T4.2** `LSUIElement = 1` en Info.plist → sin ícono en el Dock (patrón Stream Deck)
- [ ] **T4.3** Bundle identifier: `com.juanes545.deckbridge`
- [ ] **T4.4** Probar Gatekeeper + permisos de Accesibilidad con el `.app` buildeado
- [ ] **T4.5** Login item: `LaunchAgent` plist en `~/Library/LaunchAgents/com.juanes545.deckbridge.plist`

---

## Preguntas abiertas (para refinar)

1. **Ícono:** ¿usamos el `.icns` existente o diseñamos uno nuevo para la barra de menús? (Los íconos de menu bar deben ser template images en blanco/negro)
2. **Ventana principal:** ¿Tkinter o WebView (HTML/CSS)? Tkinter es más simple; WebView daría más control visual
3. **Fase 4 primero?** ¿Quieres el `.app` real antes que la ventana, o primero la ventana y luego el bundle?
4. **Audio en la ventana:** ¿quieres que el cambio de salida de audio esté en la ventana principal o solo en el menú?
5. **Windows:** ¿el agente Windows recibirá una mejora similar en paralelo o es post-Mac?

---

## Criterios de aceptación (DoD)

- [ ] El agente Mac arranca sin abrir ninguna ventana de Terminal
- [ ] El ícono aparece en la barra de menús dentro de 2 segundos de abrir la app
- [ ] El menú muestra el estado correcto (conectado/pareado/idle) en tiempo real
- [ ] "Abrir DeckBridge..." abre una ventana con información real del agente
- [ ] Cerrar la ventana NO detiene el agente (sigue corriendo en background)
- [ ] "Salir" en el menú detiene el agente limpiamente
- [ ] El flujo de pairing completo funciona desde la ventana (QR visible, token guardado)
- [ ] El agente sigue siendo 100% funcional para Android (HTTP, pairing, acciones)

