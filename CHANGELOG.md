# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
