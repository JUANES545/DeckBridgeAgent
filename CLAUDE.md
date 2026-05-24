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

## Build & install (macOS)

```bash
# Build + install in /Applications (dev workflow)
./builds/mac/install.sh

# Build + install + generate DMG for distribution
./builds/mac/install.sh --release

# Only generate DMG (needs dist/DeckBridge.app already built)
./builds/mac/build_dmg.sh 1.7.0
```

Output: `DeckBridge-v1.7.0.dmg` ready to upload to GitHub Release.

## Build (Windows)

```bat
builds\windows\build_windows_exe.bat
```
Produces `DeckBridgeAgent.exe` at the repo root. For the full Setup.exe installer,
GitHub Actions handles it automatically on tag push.

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
├── macos_menubar.py       ← macOS only: rumps menu bar app (DeckBridgeMenuBar)
├── macos_window.py        ← macOS only: NSWindow+WKWebView manager + DeckBridgeApi
├── macos_audio.py         ← macOS only: CoreAudio output switching via ctypes
├── pairing_qr_popup.py    ← macOS only: Tkinter popup (try/except in agent_ux.py)
├── requirements.txt       ← pynput + rumps + pyobjc-framework-WebKit (macOS)
├── requirements-build.txt ← pyinstaller + build deps
├── ui/
│   └── index.html         ← companion window UI (Tailwind CSS + Alpine.js, 700×400)
├── builds/
│   ├── mac/               ← build_mac_app.sh, install.sh, build_dmg.sh, .icns
│   └── windows/           ← build_windows_exe.bat, DeckBridgeAgent.iss (Inno Setup)
├── packaging/
│   └── dmg_background.png ← 800×400 background for DMG installer
├── .github/workflows/
│   └── release.yml        ← CI: builds DMG + Setup.exe on tag push
├── CHANGELOG.md
├── TASK.md                ← macOS app UX plan + lessons learned
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
| `agent_ux.py` | both | Console menu (h/s/p/a/r/u/z/d/q), deeplink builder, action log ring buffer |
| `macos_menubar.py` | macOS | `DeckBridgeMenuBar(rumps.App)` — menu bar icon, dropdown, NSWindow creation |
| `macos_window.py` | macOS | `DeckBridgeWindow` + `DeckBridgeApi` — pywebview bridge (unused) + HTTP API helpers |
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
| GET | `/ui` | Serves `ui/index.html` — companion window HTML |
| GET | `/api/status` | JSON: state, device_name, lan_ip, last_actions, version, accessibility_ok, udp_ok |
| POST | `/api/pair` | Trigger pairing from the companion window |
| POST | `/api/forget` | Unpair from the companion window |
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

## macOS companion app

The macOS app (`DeckBridge.app`) is a native menu-bar-only app:
- **Menu bar icon** (template image) — always visible, no Dock icon by default
- **"Abrir DeckBridge…"** → opens `NSWindow + WKWebView` (700×400, horizontal layout)
- **Dock + ⌘Tab** — app appears while window is open (Tailscale pattern), disappears on close
- **Window backend** — loads `ui/index.html` via `loadHTMLString_baseURL_("http://localhost:8765/")`,
  polls `/api/status` every second via Alpine.js `fetch()`

### macOS permissions
Grant in System Settings → Privacy & Security:
- **Accessibility** — keyboard shortcuts injection
- **Input Monitoring** — keyboard event capture

`request_accessibility_prompt()` is called at startup to register the app in TCC.

### PyObjC critical notes (do NOT regress)
- `NSWindowStyleMaskTitled` not `NSWindowStyleMask.titled` (NewType, no attributes)
- `initWithContentRect_styleMask_backing_defer_` not `deferred_`
- Activation policy: use integers `0`=Regular `1`=Accessory, not imported constants
- Load HTML with `loadHTMLString_baseURL_` not `url=file://` (WKWebView CDN restrictions)
- Close detection: `@rumps.timer(1)` checking `win.isVisible()`, not NSNotificationCenter blocks
- Keep `open_window_clicked` error blocks separate — never let policy errors fall through to browser fallback

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
2. Update `CHANGELOG.md` — entry `## [X.Y.Z] - YYYY-MM-DD`
3. Commit: `git config commit.gpgsign false` then `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit`
4. Push: `git push origin master` (HTTPS only — SSH key has passphrase)
5. Tag + push: `git tag vX.Y.Z && git push origin vX.Y.Z`
6. **GitHub Actions automatically builds and uploads:**
   - `DeckBridge-vX.Y.Z.dmg` (macOS, ~1m)
   - `DeckBridgeAgent-vX.Y.Z-Setup.exe` (Windows, ~2m)

**Deploy to Windows PC after release:**
```bash
ssh windows-pc "\"C:\Program Files\Git\cmd\git.exe\" -C Documents\Andes\DeckBridgeAgent pull"
```

**macOS companion app — install locally:**
```bash
./builds/mac/install.sh          # build + install in /Applications
./builds/mac/install.sh --release # build + install + generate DMG
```

**Before `gh` commands:** verify active account is JUANES545 — `gh auth switch --user JUANES545`
**workflow scope:** if push of `.github/workflows/` fails — `gh auth refresh -h github.com -s workflow`

---

## Related repositories

| Repo | Description |
|---|---|
| [DeckBridge](https://github.com/JUANES545/DeckBridge) | Android app (macros deck) — consumes this agent |
| [studio](https://github.com/JUANES545/studio) | Personal Studio page |

Protocol documentation (ports, pairing v1 API, action JSON): `README.md`

---

## How changes are made in this project

**Every modification to this repo follows this workflow — do not skip steps.**

### 1. Implement (subagent)
When a change is requested, delegate the implementation to a subagent:

```
Agent(subagent_type="general-purpose", run_in_background=True, prompt="""
Implement <task> in /Users/juamejia/Andes/DeckBridgeAgent.
- Read the relevant files first
- Make the minimal change needed
- Run syntax check: python3 -c "import <module>"
- Do NOT commit
- Report: what changed, which lines, test result
""")
```

### 2. Review (supervisor — this instance)
While the subagent runs, or after it finishes:
- Read the modified files
- Verify the change is correct and minimal
- If wrong: send a correction message to the subagent via `SendMessage`
- If correct: proceed to step 3

### 3. Test on Windows via SSH
```bash
# Pull changes on Windows PC
ssh windows-pc "\"C:\Program Files\Git\cmd\git.exe\" -C Documents\Andes\DeckBridgeAgent pull"

# Restart agent and verify
ssh windows-pc "netstat -an | findstr 8765"
curl -s http://192.168.1.29:8765/health | python3 -m json.tool
```

### 4. Release
Only after review + Windows test pass:
```bash
git config commit.gpgsign false
PRE_COMMIT_ALLOW_NO_CONFIG=1 git add <files> && git commit -m "fix/feat/..."
# Update CHANGELOG.md
git push origin master
git tag vX.Y.Z && git push origin vX.Y.Z
gh release create vX.Y.Z --repo JUANES545/DeckBridgeAgent --latest
```

### Guiding principles
- Subagent implements, supervisor reviews — never skip review
- Changes must be tested on the real Windows PC before release
- Keep changes minimal — one concern per commit
- CHANGELOG entry required for every release
