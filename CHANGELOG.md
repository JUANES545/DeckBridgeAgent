# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
