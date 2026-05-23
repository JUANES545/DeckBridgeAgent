# DeckBridge Agent

Cross-platform host agent for the [DeckBridge Android app](https://github.com/JUANES545/DeckBridge). Runs on **macOS** and **Windows** from a single codebase.

Receives macro actions over LAN from the Android app and executes them on the desktop: keyboard shortcuts, media keys, text injection, and (macOS) audio output switching.

---

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
python server.py                   # default port 8765
python server.py 9000              # custom port
```

On the phone: **Settings → PC over LAN**, enter the agent's IPv4, port 8765, tap **Test connection**.

---

## Platform setup

### macOS

Grant **Accessibility** and **Input Monitoring** for Terminal (or the built binary) in System Settings → Privacy & Security.

**Build a double-click launcher:**
```bash
chmod +x builds/mac/build_mac_app.sh
./builds/mac/build_mac_app.sh
# Then launch: builds/mac/DeckBridge Mac Agent.command
```

### Windows

When running the `.exe`, a UAC prompt appears once to add scoped firewall Allow rules (TCP 8765 + UDP 8766). Accept it.

**Build `.exe`:**
```bat
builds\windows\build_windows_exe.bat
```
Produces `DeckBridgeAgent.exe` at the repo root. No Python required to run it.

---

## HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `agent_os` (`darwin` / `windows`), pairing status, discovery counters |
| POST | `/action` | `combo`, `media`, `text`, `key`. Requires `X-DeckBridge-Pair-Token` when paired |
| POST | `/v1/pairing/sessions` | Phone starts pairing |
| GET | `/v1/pairing/sessions/{id}` | Phone polls status |
| POST | `/v1/pairing/host/respond` | Operator approves/rejects |

### Action types

| `type` | Fields | Behaviour |
|---|---|---|
| `combo` | `keys: string[]` | Modifier + key chord (e.g. `["ctrl","c"]`) |
| `media` | `action: string` | `vol_up/down`, `mute`, `play_pause`, `next/prev_track` |
| `text` | `text: string` | Unicode typing (max 4000 chars) |
| `key` | `key: string` | Single key: `enter`, `escape`, `tab`, `space`, `backspace`, `delete` |
| `audio_output_select` | `uid: string` | Switch macOS audio output (macOS only) |

---

## Console operator menu

Type a letter + Enter while `server.py` is running:

`h` help · `s` status · `p` pairing block · `a` approve · `r` reject · `u` unpair · `z` QR link · `q` quit

---

## Mac Bridge (macOS — corporate VPN)

For Macs behind GlobalProtect/CrowdStrike (all inbound TCP blocked), `mac_bridge_client.py` reverses the connection: the Mac connects **outbound** to Android's server (port 8767). Transport priority: ADB forward → saved IP → Tailscale → UDP broadcast.

---

## State & environment

State in `~/.deckbridge/` (override: `DECKBRIDGE_STATE_DIR`). Key env vars: `DECKBRIDGE_SKIP_FIREWALL`, `DECKBRIDGE_NO_CONSOLE_MENU`, `DECKBRIDGE_HTTP_TRACE`, `DECKBRIDGE_DEBUG`.

---

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) · [Releases](https://github.com/JUANES545/DeckBridgeAgent/releases)
