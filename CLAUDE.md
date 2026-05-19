# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run commands

```bash
# Dev run (default port 8765)
source .venv/bin/activate
python server.py

# Custom port
python server.py 9000

# Run tests
python test_bridge.py
```

## Build distributable

```bash
chmod +x build_mac_app.sh
./build_mac_app.sh               # creates dist/DeckBridgeMacAgent/DeckBridgeMacAgent
./build_mac_app.sh --recreate-venv   # if .venv is stale or pip can't resolve packages
```

Double-click `DeckBridge Mac Agent.command` in Finder to launch the built binary with a visible console window.

## Architecture overview

Single-process Python agent. Entry point is `server.py`. No framework — uses `http.server.ThreadingHTTPServer` directly.

### Module layout

| File | Responsibility |
|---|---|
| `server.py` | HTTP server (port 8765), UDP discovery (port 8766), action dispatch (`combo`/`media`/`text`/`key` via pynput), `/health` and pairing HTTP endpoints |
| `pairing_manager.py` | Full pairing v1 session lifecycle — create, poll, approve/reject, cancel, unpair. Persists paired device to `~/.deckbridge/paired_device.json` |
| `mac_bridge_client.py` | Outbound TCP client connecting to Android's `MacBridgeServer` (port 8767). Transport auto-selection: ADB forward → saved IP → Tailscale peer → UDP broadcast |
| `macos_accessibility.py` | Keyboard/shortcut injection via pynput. Requires Accessibility + Input Monitoring permissions |
| `macos_audio.py` | CoreAudio output device listing and switching via ctypes (zero external deps). Handles `AUDIO_OUTPUT_SELECT` action kind |
| `agent_ux.py` | macOS menu-bar tray icon + stdin console operator menu (h/s/p/a/r/u/d/q commands) |
| `pairing_qr_popup.py` | Tkinter window showing pairing QR code |
| `pairing_console_qr.py` | Terminal QR rendering (no desktop required) |
| `session_file_log.py` | Rotating log files → `~/.deckbridge/logs/` |

### HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Includes `agent_os: darwin`, pairing status, LAN discovery counters |
| POST | `/action` | `combo`, `media`, `text`, `key` types. Requires `X-DeckBridge-Pair-Token` when paired |
| POST | `/v1/pairing/sessions` | Phone starts pairing session |
| GET | `/v1/pairing/sessions/{id}` | Phone polls status |
| POST | `/v1/pairing/sessions/{id}/cancel` | Phone cancels |
| POST | `/v1/pairing/host/respond` | Console operator approves/rejects |
| GET | `/v1/pairing/host/status` | Paired device summary |

### Mac Bridge (inverted architecture)

When GlobalProtect/CrowdStrike blocks all inbound TCP on corporate Macs, `mac_bridge_client.py` reverses the connection: the Mac is the TCP **client**, Android runs the server (port 8767). Transport priority: ADB forward → saved IP in `~/.deckbridge/mac_bridge.json` → Tailscale peer → UDP broadcast.

### State & persistence

All state files live in `~/.deckbridge/` (override with `DECKBRIDGE_STATE_DIR`):
- `paired_device.json` — paired phone credentials
- `mac_bridge.json` — last-known Android IP for Mac Bridge
- `logs/deckbridge_mac_session_*.log` — session logs

### Environment variables

| Variable | Effect |
|---|---|
| `DECKBRIDGE_STATE_DIR` | Override state directory |
| `DECKBRIDGE_NO_CONSOLE_MENU` | Disable stdin command loop (automation/no TTY) |
| `DECKBRIDGE_HTTP_TRACE` | Log every HTTP request including `/health` polls |
| `DECKBRIDGE_DEBUG` | Set logging to DEBUG level |

### macOS permissions required

- **Accessibility** — keyboard injection via pynput
- **Input Monitoring** — keyboard event capture
- Grant for Terminal (dev) or for the built binary (`dist/DeckBridgeMacAgent`) in System Settings → Privacy & Security

### Versioning

No `__version__` in code. Version tracked via `CHANGELOG.md` and GitHub releases. Bump CHANGELOG, commit, tag `vX.Y.Z`, push tag, create GitHub release.
