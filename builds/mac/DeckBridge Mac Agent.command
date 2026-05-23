#!/bin/bash
# DeckBridge Mac Agent — cyberpunk launcher
cd "$(dirname "$0")"
HERE="$(pwd -P)"
LOG_FILE="${HOME}/.deckbridge/agent.log"

# ── Resolve runtime (before splash so MODE_LABEL is available) ────────────
VENV_PYTHON="${HERE}/.venv/bin/python"
SERVER_PY="${HERE}/server.py"
APP_BIN="${HERE}/dist/DeckBridgeMacAgent.app/Contents/MacOS/DeckBridgeMacAgent"
PLAIN_BIN="${HERE}/dist/DeckBridgeMacAgent/DeckBridgeMacAgent"

if [[ -f "$SERVER_PY" && -x "$VENV_PYTHON" ]]; then
    MODE_LABEL="source (.venv / Python 3)"
    RUN_CMD=("$VENV_PYTHON" "$SERVER_PY")
elif [[ -f "$SERVER_PY" ]] && command -v python3 &>/dev/null; then
    MODE_LABEL="source (system python3)"
    RUN_CMD=(python3 "$SERVER_PY")
elif [[ -x "$APP_BIN" ]]; then
    MODE_LABEL="binary (.app)"
    RUN_CMD=("$APP_BIN")
elif [[ -x "$PLAIN_BIN" ]]; then
    MODE_LABEL="binary (onedir)"
    RUN_CMD=("$PLAIN_BIN")
else
    MODE_LABEL="NOT FOUND"
    RUN_CMD=()
fi

# ── Kill any stale instance on port 8765 ──────────────────────────────────
STALE=$(lsof -ti tcp:8765 2>/dev/null)
[[ -n "$STALE" ]] && kill $STALE 2>/dev/null && sleep 0.8

# ── Window & title ────────────────────────────────────────────────────────
printf '\033]0;◈ DeckBridge // Neural Link\007'
printf '\033[8;42;104t'  # 42 rows × 104 cols
sleep 0.1                # let Terminal resize before printing
clear

# ── Cyberpunk splash (Python for perfect Unicode alignment) ───────────────
MODE_LABEL="$MODE_LABEL" LOG_FILE="$LOG_FILE" \
python3 - << 'PYEOF'
import json, os, subprocess, sys
from pathlib import Path

# ── Palette ──────────────────────────────────────────────────────────────
CY  = '\033[38;2;0;230;255m'    # neon cyan
MG  = '\033[38;2;200;0;255m'    # neon magenta (brighter on black)
GN  = '\033[38;2;0;255;140m'    # neon green
YL  = '\033[38;2;255;215;0m'    # neon yellow
RD  = '\033[38;2;255;80;100m'   # neon red
DM  = '\033[38;2;145;145;195m'  # mid blue-gray (legible on black)
LT  = '\033[38;2;200;225;255m'  # light blue-white (brighter)
B   = '\033[1m'
R   = '\033[0m'

IW  = 100  # inner width (between ║ borders)
TW  = IW + 2  # total = 102

def top(): return f"{MG}╔{'═'*IW}╗{R}"
def bot(): return f"{MG}╚{'═'*IW}╝{R}"
def mid(): return f"{MG}╠{'═'*IW}╣{R}"
def emp(): return f"{MG}║{' '*IW}║{R}"

def sec(label):
    # ╠══[ LABEL ]════...════╣  total inner = IW
    inner_prefix = f"══[ {label} ]"
    fill = IW - len(inner_prefix)
    return f"{MG}╠══{CY}[{B} {label} {R}{CY}]{MG}{'═'*fill}╣{R}"

def row(content: str, vis: int):
    # ║ content<pad> ║  — vis = visual length of content (no ANSI)
    pad = IW - 2 - vis   # 2 = left space + right space
    return f"{MG}║{R} {content}{' '*pad} {MG}║{R}"

def row2(l_content, l_vis, r_content, r_vis, gap=4):
    # Two-column content row
    pad = IW - 2 - l_vis - gap - r_vis
    return f"{MG}║{R} {l_content}{' '*gap}{r_content}{' '*pad} {MG}║{R}"

# ── Read config ───────────────────────────────────────────────────────────
home = Path.home()
state = home / ".deckbridge"

android_ip   = ""
android_port = 8767
ts_saved     = ""
try:
    cfg = json.loads((state / "mac_bridge.json").read_text())
    android_ip   = cfg.get("tailscale_ip") or cfg.get("android_ip") or ""
    android_port = int(cfg.get("android_port") or 8767)
    ts_saved     = cfg.get("tailscale_ip") or ""
except Exception:
    pass

pair_name = ""
try:
    pj = json.loads((state / "paired_device.json").read_text())
    pair_name = pj.get("mobile_display_name") or "device"
except Exception:
    pass

# ── Tailscale info ────────────────────────────────────────────────────────
my_ts_ip    = ""
android_ts  = ""   # hostname of Android peer
android_online = False

try:
    r_ip = subprocess.run(["tailscale", "ip"], capture_output=True, text=True, timeout=4)
    my_ts_ip = next((l.strip() for l in r_ip.stdout.splitlines() if ':' not in l), "")
except Exception:
    pass

try:
    r_st = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
    st = json.loads(r_st.stdout)
    for peer in (st.get("Peer") or {}).values():
        os_tag = str(peer.get("OS") or "").lower()
        hostname = str(peer.get("HostName") or "")
        ips = [ip for ip in (peer.get("TailscaleIPs") or []) if ':' not in ip]
        if "android" in os_tag and ips:
            if not android_ip or ips[0] == android_ip or ips[0] == ts_saved:
                android_ts     = hostname
                android_online = peer.get("Online") or (peer.get("LastSeen") is None) or False
                if not android_ip:
                    android_ip = ips[0]
                break
except Exception:
    pass

mode_label = os.environ.get("MODE_LABEL", "?")
log_file   = os.environ.get("LOG_FILE", "~/.deckbridge/agent.log")
host       = subprocess.run(["hostname", "-s"], capture_output=True, text=True).stdout.strip()

# ── Status strings ─────────────────────────────────────────────────────────
ts_str  = f"{GN}{my_ts_ip}{R}" if my_ts_ip else f"{RD}offline{R}"
ts_vis  = len(my_ts_ip) if my_ts_ip else len("offline")

if android_ip:
    dot = f"{GN}■{R}" if android_online else f"{YL}○{R}"
    lbl = f"  {android_ts}" if android_ts else ""
    and_str = f"{dot} {CY}{android_ip}{R}{DM}{lbl}{R}"
    and_vis = 2 + len(android_ip) + len(lbl)
else:
    and_str = f"{DM}not configured — type  i <ip>  in console{R}"
    and_vis = len("not configured — type  i <ip>  in console")

if pair_name:
    pair_str = f"{GN}■ PAIRED{R}  {DM}·{R}  {LT}{pair_name}{R}"
    pair_vis = len("■ PAIRED") + 4 + len(pair_name)
else:
    pair_str = f"{YL}○ UNPAIRED{R}  {DM}·  press {R}{CY}z{R}{DM} to generate QR{R}"
    pair_vis = len("○ UNPAIRED  ·  press z to generate QR")

# ── Title banner ──────────────────────────────────────────────────────────
title      = "◈  D E C K B R I D G E  ·  M A C  A G E N T  ·  N E U R A L  L I N K"
title_vis  = len(title)
title_pad  = IW - title_vis
title_row  = f"{MG}║{R}{B}{CY}  {title}{R}{' '*title_pad}{MG}║{R}"

# ── Print ─────────────────────────────────────────────────────────────────
print(top())
print(title_row)
print(mid())
print(emp())
print(sec("SYSTEM"))
print(row2(
    f"{DM}HOST{R}     {MG}·{R}  {LT}{host}{R}", 4 + 5 + len(host),
    f"{DM}RUNTIME{R}  {MG}·{R}  {GN}{mode_label}{R}", 7 + 5 + len(mode_label),
))
print(row2(
    f"{DM}PORT{R}     {MG}·{R}  {CY}tcp://0.0.0.0:8765{R}", 4 + 5 + 18,
    f"{DM}LOGS{R}     {MG}·{R}  {DM}{log_file}{R}", 4 + 5 + len(log_file),
))
print(emp())
print(sec("NETWORK"))
print(row(f"{DM}TAILSCALE{R}   {MG}·{R}  {ts_str}", 9 + 5 + ts_vis))
print(row(f"{DM}ANDROID  {R}   {MG}·{R}  {and_str}", 9 + 5 + and_vis))
print(emp())
print(sec("PAIRING"))
print(row(f"{DM}STATUS{R}  {MG}·{R}  {pair_str}", 6 + 4 + pair_vis))
print(emp())
print(sec("CONSOLE SHORTCUTS"))
print(row(f"  {CY}z{R}  {DM}·{R}  show pairing QR     {CY}u{R}  {DM}·{R}  unpair     {CY}i <ip>{R}  {DM}·{R}  set Android IP",
          2+1+4+18+1+4+10+8+4+14))
print(emp())
print(bot())
print()
PYEOF

if [[ ${#RUN_CMD[@]} -eq 0 ]]; then
    echo "  ERROR: No se encontró server.py ni ejecutable compilado."
    echo "  Compila con: python3 -m PyInstaller DeckBridgeMacAgent.spec --noconfirm"
    read -r -p "  Pulsa Enter para cerrar… "
    exit 1
fi

mkdir -p "${HOME}/.deckbridge"
exec "${RUN_CMD[@]}" "$@" 2>>"${LOG_FILE}"