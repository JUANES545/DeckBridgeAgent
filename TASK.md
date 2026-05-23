# TASK — DeckBridge Mac Agent: Native macOS App Experience

**Estado:** 🟡 En refinamiento — NO implementar hasta que el estado sea ✅ Aprobado
**Última actualización:** 2026-05-23
**Referencia visual:** Elgato Stream Deck, Logitech Options+, Tailscale macOS app

## Decisiones confirmadas

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Ícono de barra de menús | **Template image** monocromática (blanco/negro, patrón macOS nativo) |
| 2 | Tecnología de ventana | **pywebview 5.x** — HTML/CSS/JS en WKWebView nativo de macOS |
| 3 | Orden de fases | **Fases 1→2→3→4** en ese orden (menú bar primero, `.app` al final) |
| 4 | Audio en ventana | **⏳ Pendiente** — se decide después de ver el prototipo de la ventana |
| 5 | Plataformas | **Mac primero**, Windows después (una vez Mac esté refinado) |

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

**Referencia visual exacta:** [Tailscale windowed macOS UI](https://tailscale.com/blog/windowed-macos-ui-beta) — dark, minimal, status a la vista, sensación nativa.

**Stack UI:** Tailwind CSS CDN + Alpine.js (sin build step, sin Node.js — puro HTML servido por pywebview)

**Sistema de diseño:**
```css
--bg-window:   #0f1117;                        /* fondo ventana */
--bg-card:     #1a1f2e;                        /* cards / secciones */
--border:      rgba(255,255,255,0.07);         /* bordes sutiles */
--accent:      #3b82f6;                        /* azul Tailwind */
--dot-online:  #22c55e + glow 0 0 8px #22c55e80;
--dot-offline: #ef4444;
--text:        #f1f5f9;
--text-muted:  #64748b;
--font:        -apple-system, "SF Pro Text", sans-serif;
--radius-card: 12px;
--radius-btn:  8px;
```

**Componentes a tomar de [Flowbite](https://flowbite.com) (MIT):**
- [Indicators](https://flowbite.com/docs/components/indicators/) — puntos de estado con glow
- [Sidebar](https://flowbite.com/docs/components/sidebar/) — navegación lateral si se necesita
- Cards, badges, buttons — todos en modo dark

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

### Librería de ventana: `pywebview 5.x`

**Por qué pywebview sobre Qt/Tkinter:**
- **Máxima libertad de diseño** — HTML + CSS (Tailwind) + JS: se ve exactamente como una web app moderna
- **Bundle más pequeño** — WKWebView es parte del SO (macOS) y WebView2 está preinstalado en Windows 10/11; no se empaqueta un motor de browser. Bundle ~20-40 MB vs ~100-200 MB de Qt
- **Cross-platform** — mismo HTML/CSS funciona en macOS y Windows
- **Bridge Python↔JS** — la UI llama funciones Python directamente vía API de pywebview

**Arquitectura de threading (clave):**
```
Main thread  →  rumps.App.run()       (siempre dueño del main thread)
Thread B     →  httpd.serve_forever() (HTTP server)
Thread C     →  webview.start()       (creado on-demand cuando el usuario abre la ventana)
Thread D     →  mac_bridge_client     (existente)
```
`webview.start()` se lanza en un thread solo cuando el usuario hace clic en "Abrir DeckBridge...".
Cuando cierra la ventana, el thread termina. `rumps` sigue en el main thread siempre.

**Stack de la ventana:**
- HTML + Tailwind CSS (via CDN o bundled)
- JS vanilla para interactividad
- Python bridge para leer estado del agente y ejecutar acciones

### Módulos nuevos

| Módulo | Responsabilidad |
|---|---|
| `macos_menubar.py` | `rumps.App` subclass — ícono template, menú, callbacks de estado |
| `ui/index.html` | Ventana principal — HTML/Tailwind UI con secciones |
| `ui/app.js` | JS bridge — consume la API Python expuesta por pywebview |

### Módulos modificados

| Módulo | Cambio |
|---|---|
| `agent_ux.py` | En macOS: delega al `DeckBridgeMenuBar`; mantiene `stdin_loop` como fallback CLI |
| `server.py` | `httpd.serve_forever()` pasa a thread; `rumps_app.run()` toma el main thread |
| `requirements.txt` | agregar `rumps>=0.4.0; sys_platform=="darwin"` y `pywebview>=5.0; sys_platform=="darwin"` |
| `builds/mac/build_mac_app.sh` | `--windowed` + `--osx-bundle-identifier` + `--add-data ui` para `.app` real |

### Dependencias nuevas (macOS only)

```
rumps>=0.4.0; sys_platform=="darwin"
pywebview>=5.0; sys_platform=="darwin"
```

Nota: en Windows no se instalan estas dependencias (platform markers). La ventana en Windows usará CustomTkinter o pywebview con QSystemTray en una fase posterior.

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

### Fase 2 — Ventana principal (pywebview + HTML/Tailwind)
- [ ] **T2.1** Crear `ui/index.html`: estructura base con Tailwind CSS (via CDN)
- [ ] **T2.2** Crear `ui/app.js`: JS bridge — consume la API Python de pywebview
- [ ] **T2.3** Crear `macos_window.py`: lanza `webview.start()` en thread on-demand
- [ ] **T2.4** Sección "Estado de conexión" — badge, nombre dispositivo, IP, última acción
- [ ] **T2.5** Sección "Acciones rápidas" — botones Parear / Copiar QR deeplink / Olvidar
- [ ] **T2.6** Sección "Diagnósticos" — lista últimas 10 acciones con timestamp
- [ ] **T2.7** Footer: versión, estado Accesibilidad, UDP discovery
- [ ] **T2.8** Conectar menú "Abrir DeckBridge..." → abre/trae la ventana pywebview
- [ ] **T2.9** Cerrar ventana = ocultar (thread termina limpiamente), agente sigue corriendo

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

| # | Pregunta | Estado |
|---|---|---|
| 4 | Audio en la ventana | ⏳ Pendiente — se decide después de ver el prototipo visual |

> Las preguntas 1, 2, 3, 5 están respondidas y registradas en "Decisiones confirmadas".

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

