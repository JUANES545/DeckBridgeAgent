# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run commands

```bash
# Setup (macOS / Linux)
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Setup (Windows)
py -3.12 -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt

# Dev run (default port 8765)
python server.py

# Custom port
python server.py 9000

# Run tests
python test_bridge.py
```

## Build distributable

### macOS
```bash
chmod +x builds/mac/build_mac_app.sh
./builds/mac/build_mac_app.sh                    # creates dist/DeckBridgeMacAgent/
./builds/mac/build_mac_app.sh --recreate-venv    # if .venv is stale
```
Launch via `builds/mac/DeckBridge Mac Agent.command` (double-click in Finder).

### Windows
```bat
builds\windows\build_windows_exe.bat
```
Produces `DeckBridgeAgent.exe` at the repo root.

## Repository structure

```
DeckBridgeAgent/
├── server.py              ← unified entry point (platform guards via sys.platform)
├── pairing_manager.py     ← shared pairing v1 session lifecycle
├── agent_ux.py            ← shared console menu + tray; QR popup conditional on macOS
├── session_file_log.py    ← shared rotating file logger
├── pairing_console_qr.py  ← terminal QR rendering (all platforms)
├── mac_bridge_client.py   ← macOS only: outbound TCP to Android MacBridgeServer
├── macos_accessibility.py ← macOS only: keyboard injection via pynput
├── macos_audio.py         ← macOS only: CoreAudio output switching via ctypes
├── pairing_qr_popup.py    ← macOS only: Tkinter QR popup (graceful fallback on Windows)
├── requirements.txt       ← shared: pynput
├── requirements-build.txt ← pyinstaller + build deps
├── builds/
│   ├── mac/
│   │   ├── build_mac_app.sh
│   │   ├── DeckBridge Mac Agent.command
│   │   └── DeckBridgeMacAgent.icns / .iconset
│   └── windows/
│       ├── build_windows_exe.bat
│       └── README-WINDOWS-PC-INSTALL.md
├── CHANGELOG.md
└── README.md
```

## Architecture overview

Single-process Python agent. `server.py` is the sole entry point for both platforms. Uses `http.server.ThreadingHTTPServer` directly — no web framework.

### Platform detection pattern

Mac-specific modules are imported conditionally inside `server.py` with `if sys.platform == "darwin":` blocks. Windows-specific code (firewall UAC) is guarded with `if sys.platform == "win32":`. No platform detection is needed in `pairing_manager.py` or `session_file_log.py` — those are fully cross-platform.

### Module responsibilities

| File | Platform | Responsibility |
|---|---|---|
| `server.py` | both | HTTP server (port 8765), UDP discovery (port 8766), action dispatch, `/health` + pairing endpoints, Windows firewall auto-config |
| `pairing_manager.py` | both | Pairing v1 session lifecycle — create, poll, approve/reject, cancel, unpair, host-QR invite. Persists to `~/.deckbridge/paired_device.json` |
| `agent_ux.py` | both | Console operator menu (h/s/p/a/r/u/z/d/q) + deeplink builder. macOS: tray icon, QR popup; Windows: graceful fallback |
| `session_file_log.py` | both | Rotating log files → `~/.deckbridge/logs/` |
| `pairing_console_qr.py` | both | Terminal QR rendering |
| `mac_bridge_client.py` | macOS | Outbound TCP client to Android `MacBridgeServer` (port 8767). Transport: ADB forward → saved IP → Tailscale → UDP broadcast |
| `macos_accessibility.py` | macOS | Keyboard injection via pynput; checks Accessibility permission |
| `macos_audio.py` | macOS | CoreAudio output device listing + switching via ctypes; handles `audio_output_select` action |
| `pairing_qr_popup.py` | macOS | Tkinter QR popup window (imported with try/except in `agent_ux.py`) |

### HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `agent_os` (`darwin`/`windows`), pairing status, LAN discovery counters |
| POST | `/action` | `combo`, `media`, `text`, `key`, `audio_output_select`. Requires `X-DeckBridge-Pair-Token` when paired |
| POST | `/v1/pairing/sessions` | Phone starts pairing |
| GET | `/v1/pairing/sessions/{id}` | Phone polls status |
| POST | `/v1/pairing/sessions/{id}/cancel` | Phone cancels |
| POST | `/v1/pairing/host/qr-sessions` | Console `z` command — PC-initiated QR invite |
| POST | `/v1/pairing/host/respond` | Operator approves/rejects |
| GET | `/v1/pairing/host/status` | Paired device summary |

### Mac Bridge (macOS — inverted architecture)

`mac_bridge_client.py` reverses the TCP direction to bypass GlobalProtect/CrowdStrike: the Mac connects **outbound** to Android's `MacBridgeServer` (port 8767). Transport priority: ADB forward → saved IP in `~/.deckbridge/mac_bridge.json` → Tailscale peer → UDP broadcast.

### Windows firewall

On first `.exe` run, `_maybe_prompt_windows_firewall_inbound()` in `server.py` requests UAC elevation once to add scoped `netsh` Allow rules (TCP 8765 + UDP 8766) and remove conflicting Block rules. Skip with `DECKBRIDGE_SKIP_FIREWALL=1`.

### State & persistence

All state in `~/.deckbridge/` (override: `DECKBRIDGE_STATE_DIR`):
- `paired_device.json` — paired phone credentials
- `mac_bridge.json` — last-known Android IP (macOS)
- `logs/` — session log files

### Environment variables

| Variable | Effect |
|---|---|
| `DECKBRIDGE_STATE_DIR` | Override state directory |
| `DECKBRIDGE_SKIP_FIREWALL` | Skip UAC firewall setup (Windows, testing) |
| `DECKBRIDGE_NO_CONSOLE_MENU` | Disable stdin command loop |
| `DECKBRIDGE_HTTP_TRACE` | Log every HTTP request including `/health` polls |
| `DECKBRIDGE_DEBUG` | Set logging to DEBUG level |

### macOS permissions required

Grant for Terminal (dev) or for `dist/DeckBridgeMacAgent` in System Settings → Privacy & Security:
- **Accessibility** — keyboard injection
- **Input Monitoring** — keyboard event capture

### Versioning

No `__version__` in code. Version tracked via `CHANGELOG.md` and GitHub releases. Bump `CHANGELOG.md`, commit, tag `vX.Y.Z`, push tag, create GitHub release.
