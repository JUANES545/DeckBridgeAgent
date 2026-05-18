# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-05-18

### Added

- **HTTP agent server** (`server.py`): HTTP/1.1 server on port 8765 handling `GET /health`, `POST /action`, and pairing v1 endpoints. Protocol-compatible with the DeckBridge Android app and the Windows agent.
- **LAN discovery** (`server.py`): UDP listener on port 8766 replying to `DECKBRIDGE_DISCOVER_v1` broadcasts with agent IP, port, and `agent_os: darwin`.
- **macOS input simulation** (`macos_accessibility.py`): Keyboard shortcut injection via `pynput`; requires Accessibility and Input Monitoring permissions.
- **Audio output switching** (`macos_audio.py`): Lists and switches macOS system audio output devices via CoreAudio; supports `AUDIO_OUTPUT_SELECT` action kind.
- **Mac Bridge client** (`mac_bridge_client.py`): Outbound TCP connection to the Android `MacBridgeServer` (port 8767) as an alternative to LAN HTTP. Supports ADB forward, saved IP, Tailscale peer, and UDP broadcast auto-discovery.
- **Pairing flow**: QR code generation (`pairing_qr_popup.py`, `pairing_console_qr.py`) and session management (`pairing_manager.py`) compatible with DeckBridge Android pairing v1.
- **Agent UX** (`agent_ux.py`): macOS menu-bar tray icon with status, pairing, and quit actions.
- **Session file logging** (`session_file_log.py`): Rotating log files written to `~/.deckbridge/logs/`.
- **PyInstaller build** (`build_mac_app.sh`, `DeckBridge Mac Agent.command`): Produces a standalone `dist/DeckBridgeMacAgent` binary launchable via double-click from Finder.
- **State persistence**: Pairing credentials and discovered endpoints stored in `~/.deckbridge/` (overridable via `DECKBRIDGE_STATE_DIR`).
