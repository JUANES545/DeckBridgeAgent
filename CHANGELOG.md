# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.9.0] - 2026-05-24

### Added

- **Windows system tray:** `windows_tray.py` — `WindowsTray(pystray.Icon)` with status menu, "Abrir DeckBridge…", pair/forget/quit. Runs on main thread like rumps on macOS.
- **Windows native window:** pywebview (WebView2) loading `http://localhost:8765/ui`; fallback to Edge `--app=` mode when pywebview unavailable (e.g. SSH session).
- **Windows native installer (Inno Setup):** `DeckBridgeAgent-vX.Y.Z-Windows-Setup.exe` — installs to `%APPDATA%\DeckBridge`, Start Menu, optional desktop shortcut, optional autostart at login, uninstaller in Apps & Features.
- **`DeckBridge.ico`:** multi-size Windows icon (16→256 px) generated from original iconset.
- **`builds/windows/tray_icon.png`:** 32px colored icon for Windows system tray.
- **Desktop shortcut** created automatically with proper icon.
- **Consistent installer naming:** `DeckBridgeAgent-vX.Y.Z-macOS.dmg` and `DeckBridgeAgent-vX.Y.Z-Windows-Setup.exe`.

### Fixed

- Icons now fill available space — auto-crop + scale from original iconset instead of using padded source.
- macOS menu bar template `@2x` (44px Retina) version added.
- `DECKBRIDGE_NO_GUI=1` now also suppresses `tray.run()` on Windows (headless/SSH mode).
- CHANGELOG.md bundled in `.app` so version displays correctly in the companion window.

## [1.7.0] - 2026-05-24

### Added

- **Native macOS app window:** "Abrir DeckBridge…" now opens a native `NSWindow + WKWebView` (via PyObjC) instead of a browser tab or pywebview. The window runs on the macOS main thread — no thread conflicts with rumps.
- **Dock + Cmd-Tab integration (Tailscale pattern):** app appears in Dock and `⌘Tab` while the window is open; reverts to menu-bar-only when the window closes.
- **Horizontal 700×400 layout:** two-column design — status/controls on the left, action log on the right. Replaces the original vertical layout.
- **Redesigned UI:** status dot with glow animation, pill-shaped state badge (Conectado/Pareado/Sin dispositivo), cleaner card layout, SF Pro typography, accessibility warning banner.
- **Accessibility permission prompt:** `request_accessibility_prompt()` called on startup so DeckBridge appears in System Settings → Accessibility on first launch.
- **DMG installer:** `builds/mac/build_dmg.sh` creates a styled `DeckBridge-vX.Y.Z.dmg` with drag-to-Applications window. `builds/mac/install.sh --release` builds + installs + generates DMG.
- **Inno Setup template:** `builds/windows/DeckBridgeAgent.iss` — Windows installer config ready for future use.
- **GitHub Actions CI/CD (`.github/workflows/release.yml`):** pushing a `vX.Y.Z` tag automatically builds and uploads `DeckBridge-vX.Y.Z.dmg` (macOS, ~51s) and `DeckBridgeAgent-vX.Y.Z-Setup.exe` (Windows, ~2m) to the GitHub Release.

### Fixed

- Blank window in `.app` bundle: switched from `url=file://` to `loadHTMLString_baseURL_` with base `http://localhost:8765/` so CDN scripts and `fetch('/api/status')` resolve correctly.
- `NSWindowStyleMask` constants: use `NSWindowStyleMaskTitled` directly instead of `.titled` attribute (PyObjC NewType).
- `initWithContentRect_styleMask_backing_defer_` typo (`deferred_` → `defer_`).
- Activation policy: use integer constants (`0`=Regular, `1`=Accessory) to avoid import failures in bundle.
- Removed custom HTML titlebar that duplicated the native macOS window chrome.
- `--skip-jenkins` in `build_dmg.sh` now only active in CI environments; local builds get the styled background.

## [1.5.0] - 2026-05-23

### Changed

- **`.app` bundle (Phase 4):** `build_mac_app.sh` now produces `dist/DeckBridge.app` — a proper windowed macOS app bundle. No Terminal window opens on launch.
  - `--windowed` PyInstaller flag (no console)
  - `LSUIElement = true` patched into `Info.plist` after build — app runs as menu-bar-only, no Dock icon
  - Bundle identifier: `com.juanes545.deckbridge`
  - App icon: `DeckBridgeMacAgent.icns`
  - `ui/` folder and `menubar_template.png` bundled via `--add-data`
  - All new modules (`macos_menubar`, `macos_window`, `rumps`, `webview`) included as hidden imports
- **Accessibility:** when built as `DeckBridge.app`, macOS shows the correct app name in System Settings → Privacy & Security → Accessibility.
- **`builds/mac/DeckBridge.command`** — new fallback Terminal launcher for developer/headless use.

## [1.4.0] - 2026-05-23

### Added

- **Main window — Phase 2 (pywebview + Tailwind CSS):** clicking "Abrir DeckBridge…" in the menu bar opens a native macOS window (420×630 px) with the full dark UI. Sections: connection status card with animated dot, quick action buttons (Pair / Copy QR / Forget device), scrollable recent-actions log, accessibility warning, and footer with version + status indicators.
- **`macos_window.py`:** `DeckBridgeWindow` manages the pywebview window lifecycle (open-or-focus pattern, daemon thread). `DeckBridgeApi` exposes `get_status`, `pair`, `forget`, `copy_deeplink`, `close_window`, and `open_accessibility_settings` to the JS frontend.
- **`ui/index.html`:** Tailwind CDN + Alpine.js CDN. Polls `pywebview.api.get_status()` every second. Status dot with glow animation, monospace action log, toast notification on copy.
- **`pywebview>=5.0`** added to `requirements.txt` (macOS only).
- **Action log:** `AgentUx.record_action()` captures every `/action` execution; `get_recent_actions()` exposes the last 10 to the window.

## [1.3.0] - 2026-05-23

### Added

- **macOS menu bar icon (Phase 1):** the agent now runs as a native macOS menu bar app. A `🎛️` icon appears in the status bar; clicking it opens a native dropdown with connection status, device name, LAN IP, "Pair with Android", "Forget device", and "Quit". No Terminal window is required to keep the agent running.
- **`macos_menubar.py`:** new `DeckBridgeMenuBar(rumps.App)` class — all five connection states (`connected`, `paired`, `waiting_for_pairing`, `idle`, `error`) are reflected in real time in the menu.
- **`rumps>=0.4.0`** added to `requirements.txt` (macOS only via platform marker).

### Changed

- **`server.py` (macOS):** HTTP server now runs in a daemon thread; `rumps.App.run()` takes the main thread. The `stdin_loop` is disabled on macOS by default (set `DECKBRIDGE_NO_GUI=1` to re-enable it for headless use).
- **`agent_ux.py`:** all pairing and connection callbacks now push state updates to the menu bar when it is active.

## [1.2.0] - 2026-05-23

### Fixed

- **Session log filename on Windows:** log files were named `deckbridge_mac_session_*` regardless of platform. Introduced `_session_prefix()` helper — returns `deckbridge_mac_session_` on macOS, `deckbridge_pc_session_` on Windows, and `deckbridge_agent_session_` on any other platform. Both filename generation and purge glob use the helper.

## [1.1.0] - 2026-05-23

### Fixed

- **Windows console encoding crash:** `server.py` now reconfigures `stdout`/`stderr` to UTF-8 at startup on Windows, preventing a `UnicodeEncodeError` (cp1252) when printing the startup banner containing `✓` and `—`. The agent now starts cleanly on any Windows locale.

## [1.0.0] - 2026-05-18

### Added

- **Unified codebase:** single repository replacing the separate `DeckBridgeMacAgent` and `DeckBridgePcAgent` repos. Platform detection via `sys.platform`; Mac-specific modules (`mac_bridge_client`, `macos_accessibility`, `macos_audio`, QR popup) are imported conditionally.
- **HTTP agent** (`server.py`): port 8765, `GET /health`, `POST /action`, full pairing v1 endpoints. `agent_os` field in health and discovery replies (`darwin` / `windows`).
- **UDP LAN discovery** (port 8766): responds to `DECKBRIDGE_DISCOVER_v1` broadcasts.
- **Action types:** `combo`, `media`, `text`, `key` via pynput. `audio_output_select` on macOS via CoreAudio.
- **Pairing v1** (`pairing_manager.py`): full session lifecycle — create, poll, approve/reject, cancel, unpair, host-QR invite. Persists to `~/.deckbridge/paired_device.json`.
- **Mac Bridge** (`mac_bridge_client.py`): outbound TCP client to Android's server (port 8767). Transport auto-selection: ADB forward → saved IP → Tailscale → UDP broadcast. Bypasses GlobalProtect / CrowdStrike inbound blocks.
- **macOS input simulation** (`macos_accessibility.py`): keyboard injection via pynput; requires Accessibility + Input Monitoring.
- **CoreAudio output switching** (`macos_audio.py`): zero external deps, ctypes against CoreAudio.framework.
- **Console operator menu** (`agent_ux.py`): `h/s/p/a/r/u/z/d/q` commands; QR popup on macOS (Tkinter), terminal QR on all platforms.
- **Session file logging** (`session_file_log.py`): rotating logs to `~/.deckbridge/logs/`.
- **Windows firewall auto-config**: UAC elevation on first `.exe` run to add scoped TCP/UDP Allow rules and remove conflicting Block rules.
- **Build scripts:** `builds/mac/build_mac_app.sh` (macOS app bundle) and `builds/windows/build_windows_exe.bat` (single-file `.exe`). Both use PyInstaller.
