# TASK — DeckBridge Mac Agent: Native macOS App Experience

**Estado:** ✅ Objetivo principal cumplido — pendiente: rediseño visual, audio interactivo, login item
**Última actualización:** 2026-05-24
**Referencia visual:** Elgato Stream Deck, Logitech Options+, Tailscale macOS app

---

## Decisiones confirmadas

| # | Decisión |
|---|---|
| 1 | Ícono barra de menús: **template image** monocromática ✅ |
| 2 | Ventana: **NSWindow + WKWebView** (PyObjC, nativo — reemplazó pywebview por conflicto de main thread) ✅ |
| 3 | Orden: Fases 1→2→4 completadas, Fase 3 pendiente ✅ |
| 4 | Audio en ventana: **pendiente** — Fase 3 |
| 5 | Mac primero, Windows después ✅ |

---

## Criterios de aceptación (DoD)

- [x] El agente Mac arranca sin abrir ninguna ventana de Terminal
- [x] El ícono aparece en la barra de menús dentro de 2 segundos
- [x] El menú muestra el estado correcto en tiempo real
- [x] "Abrir DeckBridge..." abre ventana nativa (NSWindow + WKWebView) con datos reales
- [x] Cerrar la ventana NO detiene el agente
- [x] "Salir" en el menú detiene el agente limpiamente
- [x] El flujo de pairing funciona (QR, token guardado)
- [x] El agente sigue siendo 100% funcional para Android

---

## Estado de implementación

### Fase 1 — Menu bar ✅ (v1.3.0)
- [x] `rumps` en requirements.txt
- [x] `macos_menubar.py`: DeckBridgeMenuBar con menú, ícono template, callbacks de estado
- [x] `httpd.serve_forever()` → thread, `rumps.run()` en main thread
- [x] `stdin_loop` como fallback con `DECKBRIDGE_NO_GUI=1`

### Fase 2 — Ventana principal ✅ (v1.4.0 → v1.6.x)
- [x] `ui/index.html`: Tailwind CSS + Alpine.js, UI dark
- [x] `/ui` endpoint en server.py sirve el HTML
- [x] `/api/status` endpoint — datos en tiempo real
- [x] `/api/pair` y `/api/forget` endpoints
- [x] Sección estado de conexión, acciones rápidas, diagnósticos, footer
- [x] Ventana: NSWindow + WKWebView (PyObjC) — corre en main thread desde callback del menú
- [x] `action log`: `record_action()` en AgentUx — últimas 10 acciones

### Fase 3 — Audio outputs interactivo ⏸️ PENDIENTE
- [ ] **T3.1** Sección "Salidas de audio" con radio buttons desde `macos_audio`
- [ ] **T3.2** Clic en salida → llama `set_default_output(uid)`
- [ ] **T3.3** Observer actualiza la UI en tiempo real

### Fase 4 — `.app` bundle ✅ (v1.5.0)
- [x] `build_mac_app.sh` → `--windowed`, re-sign después de plist patch
- [x] `LSUIElement = true` → sin ícono en el Dock
- [x] Bundle identifier: `com.juanes545.deckbridge`
- [x] `install.sh` — script de una línea que hace todo
- [ ] **T4.5** Login item: `LaunchAgent` plist *(pendiente)*

### Fase 5 — Rediseño visual 🔄 EN PROGRESO
- [ ] **T5.1** Header con ícono real de la app y título elegante
- [ ] **T5.2** Status card rediseñada — glow animado, layout más limpio
- [ ] **T5.3** Botones con mejor jerarquía visual
- [ ] **T5.4** Paleta de colores refinada — más cerca de Tailscale/Stream Deck
- [ ] **T5.5** Tipografía SF Pro cargada correctamente
- [ ] **T5.6** Animaciones suaves en cambios de estado
- [ ] **T5.7** Rebuild + install post-rediseño

---

## Notas de implementación (decisiones tomadas en marcha)

- **pywebview descartado**: conflicto de main thread con rumps. Solución: NSWindow + WKWebView via PyObjC directo, creado desde el callback del menú (que corre en el main thread).
- **HTTP bridge en vez de JS API**: la ventana carga `http://localhost:8765/ui` y usa `fetch('/api/status')` cada segundo. Más simple y confiable.
- **`defer_` no `deferred_`**: bug de typo en el nombre del método PyObjC que causó que la ventana fallara silenciosamente.
- **`ditto` en vez de `cp -r`**: para copiar `.app` bundles en macOS — preserva extended attributes.
- **`xattr -dr com.apple.quarantine`**: el install.sh lo hace automáticamente para evitar el bloqueo de Gatekeeper.
