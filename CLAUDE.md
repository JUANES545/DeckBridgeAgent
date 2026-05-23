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
./builds/mac/build_mac_app.sh
./builds/mac/build_mac_app.sh --recreate-venv   # if .venv is stale
```

### Windows
```bat
builds\windows\build_windows_exe.bat
```
Produces `DeckBridgeAgent.exe` at the repo root.

## Repository structure

```
DeckBridgeAgent/
├── server.py              ← unified entry point (sys.platform guards)
├── pairing_manager.py     ← shared pairing v1 lifecycle
├── agent_ux.py            ← shared console menu; QR popup conditional on macOS
├── session_file_log.py    ← shared rotating logger
├── pairing_console_qr.py  ← terminal QR (all platforms)
├── mac_bridge_client.py   ← macOS only: outbound TCP to Android MacBridgeServer
├── macos_accessibility.py ← macOS only: keyboard injection via pynput
├── macos_audio.py         ← macOS only: CoreAudio output switching via ctypes
├── pairing_qr_popup.py    ← macOS only: Tkinter popup (try/except in agent_ux.py)
├── requirements.txt       ← shared: pynput
├── requirements-build.txt ← pyinstaller + build deps
├── builds/
│   ├── mac/               ← build_mac_app.sh, .command launcher, .icns
│   └── windows/           ← build_windows_exe.bat, install README
├── CHANGELOG.md
└── README.md
```

## Architecture overview

Single-process Python agent. `server.py` is the sole entry point for both platforms.
Uses `http.server.ThreadingHTTPServer` — no web framework.

### Platform detection
Mac-specific modules imported with `if sys.platform == "darwin":` blocks.
Windows firewall code guarded with `if sys.platform == "win32":`.
`pairing_manager.py` and `session_file_log.py` are fully cross-platform.

### Module responsibilities

| File | Platform | Responsibility |
|---|---|---|
| `server.py` | both | HTTP 8765, UDP discovery 8766, action dispatch, pairing endpoints, Windows firewall |
| `pairing_manager.py` | both | Pairing v1: create/poll/approve/reject/cancel/unpair/host-QR |
| `agent_ux.py` | both | Console menu (h/s/p/a/r/u/z/d/q), deeplink builder, tray on macOS |
| `session_file_log.py` | both | Rotating logs → `~/.deckbridge/logs/` |
| `pairing_console_qr.py` | both | Terminal QR rendering |
| `mac_bridge_client.py` | macOS | Outbound TCP to Android (port 8767); ADB→IP→Tailscale→UDP |
| `macos_accessibility.py` | macOS | Keyboard injection via pynput |
| `macos_audio.py` | macOS | CoreAudio device list + switch; handles `audio_output_select` |
| `pairing_qr_popup.py` | macOS | Tkinter QR popup |

### HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `agent_os` (darwin/windows), pairing status, discovery counters |
| POST | `/action` | combo/media/text/key/audio_output_select. Requires `X-DeckBridge-Pair-Token` when paired |
| POST | `/v1/pairing/sessions` | Phone starts pairing |
| GET | `/v1/pairing/sessions/{id}` | Phone polls status |
| POST | `/v1/pairing/sessions/{id}/cancel` | Phone cancels |
| POST | `/v1/pairing/host/qr-sessions` | Console `z` — PC-initiated QR invite |
| POST | `/v1/pairing/host/respond` | Operator approves/rejects |
| GET | `/v1/pairing/host/status` | Paired device summary |

### Mac Bridge (macOS — corporate VPN bypass)
Mac connects **outbound** to Android's server (port 8767). Transport priority:
ADB forward → saved IP in `~/.deckbridge/mac_bridge.json` → Tailscale → UDP broadcast.

### Windows firewall
`_maybe_prompt_windows_firewall_inbound()` in `server.py` requests UAC on first `.exe` run
to add netsh Allow rules (TCP 8765 + UDP 8766). Skip: `DECKBRIDGE_SKIP_FIREWALL=1`.

## State & environment

State in `~/.deckbridge/` (override: `DECKBRIDGE_STATE_DIR`):
- `paired_device.json` — paired phone credentials
- `mac_bridge.json` — last-known Android IP (macOS)
- `logs/` — session log files

| Variable | Effect |
|---|---|
| `DECKBRIDGE_STATE_DIR` | Override state directory |
| `DECKBRIDGE_SKIP_FIREWALL` | Skip UAC firewall setup (Windows, testing) |
| `DECKBRIDGE_NO_CONSOLE_MENU` | Disable stdin command loop |
| `DECKBRIDGE_HTTP_TRACE` | Log every HTTP request |
| `DECKBRIDGE_DEBUG` | DEBUG log level |

## macOS permissions
Grant for Terminal (dev) or `dist/DeckBridgeMacAgent` in System Settings → Privacy & Security:
- **Accessibility** — keyboard injection
- **Input Monitoring** — keyboard event capture

---

## Windows PC access (SSH)

The repo is cloned on the Windows PC at `C:\Users\PC\Documents\Andes\DeckBridgeAgent`.

```bash
# Connect
ssh windows-pc "comando"              # via Tailscale (preferred)
ssh PC@192.168.1.8 "comando"          # LAN direct if Tailscale timeout

# Pull latest changes on Windows
ssh windows-pc "\"C:\Program Files\Git\cmd\git.exe\" -C Documents\Andes\DeckBridgeAgent pull"

# Check agent running
ssh windows-pc "netstat -an | findstr 8765"

# Run agent on Windows
ssh windows-pc "cd Documents\Andes\DeckBridgeAgent && .venv\Scripts\python.exe server.py 2>&1"

# Health check from Mac
curl -s http://192.168.1.29:8765/health | python3 -m json.tool

# Test action with pair token
curl -s -X POST http://192.168.1.29:8765/action \
  -H "Content-Type: application/json" \
  -H "X-DeckBridge-Pair-Token: <token>" \
  -d '{"type":"key","key":"enter"}'
```

**Windows PC details:**
- LAN IP: 192.168.1.29 · Tailscale: 100.65.234.99
- SSH may need starting: `Start-Service sshd` (PowerShell admin)
- Git path: `C:\Program Files\Git\cmd\git.exe`

---

## Release process

1. Make changes, verify locally with `python server.py`
2. Deploy to Windows: push → pull via SSH (see above)
3. Update `CHANGELOG.md` — entry `## [X.Y.Z] - YYYY-MM-DD`
4. Commit: `git config commit.gpgsign false` then `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit`
5. Push: `git push origin master` (HTTPS only — SSH key has passphrase)
6. Tag + push: `git tag vX.Y.Z && git push origin vX.Y.Z`
7. Release: `gh release create vX.Y.Z --repo JUANES545/DeckBridgeAgent --title "vX.Y.Z" --latest`

**Before `gh` commands:** verify active account is JUANES545 — `gh auth switch --user JUANES545`

---

## Related repositories

| Repo | Description |
|---|---|
| [DeckBridge](https://github.com/JUANES545/DeckBridge) | Android app (macros deck) — consumes this agent |
| [studio](https://github.com/JUANES545/studio) | Personal Studio page |

Protocol documentation (ports, pairing v1 API, action JSON): `README.md`
