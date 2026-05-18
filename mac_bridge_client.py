"""
DeckBridge Mac Bridge Client — inverted-architecture transport.

Problem: GlobalProtect full-tunnel VPN on corporate Macs blocks ALL inbound TCP/UDP,
so Android can't connect to the Mac agent's HTTP server.

Solution: the Mac agent is the TCP *client*; Android runs a small HTTP server (port 8767).
All connections are outbound from the Mac — transparent to GlobalProtect / CrowdStrike.

Transport priority (auto-selected on each reconnect):
  1. ADB forward  →  adb forward tcp:8767 tcp:8767, Mac polls localhost:8767.
                     Works always when USB cable is connected (or Wi-Fi ADB is active).
                     After first success the last ADB device serial is remembered in config.
  2. Config file  →  Mac polls <android_ip>:8767.
                     Populated automatically after any successful connection.
                     Works for direct LAN and Tailscale IPs.
  3. Tailscale    →  Reads `tailscale status --json`, finds Android peer by OS/hostname,
                     tries its Tailscale IP (100.x.x.x). Persists on success.
  4. UDP discovery → Broadcast 255.255.255.255:8766 on local Wi-Fi. Last resort.
                     Does NOT work through Tailscale or GlobalProtect — LAN-only.

First-time pairing (one-off):
  1. Start the Mac agent (python server.py).
  2. Press  z  in the agent console → QR appears.
  3. Scan QR from DeckBridge on Android → phone connects automatically.
     (MAC_BRIDGE direct token — works behind GlobalProtect / corporate VPN)
  4. pair_token is stored in ~/.deckbridge/paired_device.json automatically.
  From then on, mac_bridge_client uses the stored token transparently.

Manual config (optional): ~/.deckbridge/mac_bridge.json
  {"android_ip": "192.168.1.31", "android_port": 8767}
  or for Tailscale:
  {"android_ip": "100.x.x.x", "android_port": 8767}

  Shortcut: type  i <ip>  in the agent console to set the Android IP without editing the file.
  The Android WiFi IP is shown in DeckBridge → Settings → Mac section when Mac Bridge is selected.
"""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

_log = logging.getLogger("deckbridge.mac_bridge")

# ── Constants ────────────────────────────────────────────────────────────────
BRIDGE_PORT = 8767
DISCOVERY_PORT = 8766           # UDP port — matches MacBridgeServer.DISCOVERY_PORT on Android
DISCOVERY_MAGIC = b"DECKBRIDGE_DISCOVER_v1"
DISCOVERY_TIMEOUT_S = 4.0      # How long to wait for a UDP reply per attempt
LONG_POLL_TIMEOUT_S = 58       # Android holds the request ≤55 s; we wait a bit longer
CONNECT_TIMEOUT_S = 5
# When an ADB device is connected, retry quickly; otherwise back off to 30 s max.
RECONNECT_BASE_S = 3
RECONNECT_MAX_ADB_S = 5        # Fast retry when cable/Wi-Fi ADB is present
RECONNECT_MAX_S = 30

_STATE_DIR = Path.home() / ".deckbridge"
_PAIRED_DEVICE_JSON = _STATE_DIR / "paired_device.json"
_BRIDGE_CONFIG_JSON = _STATE_DIR / "mac_bridge.json"


# ── Credentials ──────────────────────────────────────────────────────────────

def _read_pair_token() -> Optional[str]:
    """Read the stored pair token written by the existing QR-pairing flow."""
    try:
        data = json.loads(_PAIRED_DEVICE_JSON.read_text(encoding="utf-8"))
        tok = str(data.get("pair_token") or "").strip()
        return tok if tok else None
    except Exception:
        return None


def _read_bridge_config() -> dict[str, Any]:
    try:
        return json.loads(_BRIDGE_CONFIG_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_bridge_config(updates: dict[str, Any]) -> None:
    """Merge *updates* into the existing config file atomically."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _read_bridge_config()
    cfg.update({k: v for k, v in updates.items() if v is not None})
    _BRIDGE_CONFIG_JSON.write_text(
        json.dumps(cfg, indent=2),
        encoding="utf-8",
    )


def write_bridge_config(android_ip: str, android_port: int = BRIDGE_PORT) -> None:
    """Persist Android LAN endpoint (called from console or UDP auto-detect). Never use for Tailscale IPs."""
    _write_bridge_config({"android_ip": android_ip.strip(), "android_port": android_port})
    _log.info("mac_bridge: saved config android=%s:%d", android_ip.strip(), android_port)


# ── ADB helpers ───────────────────────────────────────────────────────────────

def _adb_connected_device() -> Optional[str]:
    """
    Return the device serial to use for ADB, preferring the last known device.
    Falls back to the first available device.
    """
    try:
        out = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        ).stdout
        devices = [
            line.split("\t")[0].strip()
            for line in out.splitlines()[1:]
            if "\tdevice" in line
        ]
        if not devices:
            return None
        # Prefer the device we used last time
        last_serial = str(_read_bridge_config().get("last_adb_serial") or "").strip()
        if last_serial and last_serial in devices:
            return last_serial
        return devices[0]
    except Exception as e:
        _log.debug("adb not available: %s", e)
    return None


def _adb_setup_forward(device: str) -> bool:
    """Run adb forward tcp:BRIDGE_PORT tcp:BRIDGE_PORT. Returns True on success."""
    try:
        r = subprocess.run(
            ["adb", "-s", device, "forward",
             f"tcp:{BRIDGE_PORT}", f"tcp:{BRIDGE_PORT}"],
            capture_output=True, text=True, timeout=5,
        )
        ok = r.returncode == 0
        if ok:
            _log.info("adb: forward tcp:%d ok (device=%s)", BRIDGE_PORT, device)
        else:
            _log.warning("adb: forward failed: %s", r.stderr.strip())
        return ok
    except Exception as e:
        _log.warning("adb: forward exception: %s", e)
        return False


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get(url: str, pair_token: Optional[str], timeout: float) -> Optional[dict]:
    """GET url → parsed JSON dict, or None on any error."""
    try:
        req = urllib.request.Request(url)
        if pair_token:
            req.add_header("X-DeckBridge-Pair-Token", pair_token)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log.debug("GET %s → %s", url, type(e).__name__)
        return None


def _health_ok(base_url: str, pair_token: Optional[str]) -> bool:
    body = _http_get(f"{base_url}/health", pair_token, CONNECT_TIMEOUT_S)
    return bool(body and body.get("ok"))


def _post_state(base_url: str, pair_token: Optional[str], payload: dict) -> bool:
    """POST JSON payload to {base_url}/state. Returns True on HTTP 200."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/state", data=data, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Content-Length", str(len(data)))
        if pair_token:
            req.add_header("X-DeckBridge-Pair-Token", pair_token)
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT_S) as resp:
            return resp.status == 200
    except Exception as e:
        _log.debug("POST /state failed: %s", type(e).__name__)
        return False


# ── Tailscale discovery ───────────────────────────────────────────────────────

def _tailscale_android_ip() -> Optional[str]:
    """
    Query `tailscale status --json` and return the IPv4 address of an Android peer.
    Identifies Android devices by OS field or hostname containing "android".
    Returns None if Tailscale is not installed, not running, or no Android peer found.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        status = json.loads(result.stdout)
        peers = status.get("Peer") or {}
        for peer in peers.values():
            os_tag = str(peer.get("OS") or "").lower()
            hostname = str(peer.get("HostName") or "").lower()
            # Android peers report OS as "android" in Tailscale
            if "android" in os_tag or "android" in hostname:
                for ip in peer.get("TailscaleIPs") or []:
                    if ":" not in ip:  # IPv4 only
                        _log.info(
                            "mac_bridge: Tailscale peer found android ip=%s hostname=%s",
                            ip,
                            peer.get("HostName", "?"),
                        )
                        return ip
    except FileNotFoundError:
        _log.debug("mac_bridge: tailscale binary not found")
    except Exception as e:
        _log.debug("mac_bridge: tailscale discovery error: %s", type(e).__name__)
    return None


# ── UDP LAN discovery ─────────────────────────────────────────────────────────

def _local_subnet_broadcasts() -> list[str]:
    """
    Return broadcast addresses for all active local network interfaces.
    Uses `ifconfig -a` (macOS) to avoid external dependencies.
    Falls back to an empty list on any error.
    """
    import re
    import subprocess as _sp
    try:
        out = _sp.run(["ifconfig", "-a"], capture_output=True, text=True, timeout=5).stdout
        addrs = re.findall(r"\bbroadcast (\d+\.\d+\.\d+\.\d+)\b", out)
        # Filter out loopback/link-local
        return [a for a in addrs if not a.startswith("127.") and not a.startswith("169.254.")]
    except Exception as e:
        _log.debug("mac_bridge: ifconfig for subnet broadcasts failed: %s", e)
        return []


def _udp_discover_android(timeout_s: float = DISCOVERY_TIMEOUT_S) -> Optional[str]:
    """
    Broadcast DECKBRIDGE_DISCOVER_v1 on UDP port 8766 and wait for a reply from the
    Android MacBridgeServer.  Returns 'http://<ip>:<port>' on success, None otherwise.

    Sends to both 255.255.255.255 and each local subnet broadcast address so that
    discovery works even when GlobalProtect blocks the global broadcast.

    The Android server replies with:
      {"ok": true, "ip": "<phone_wifi_ip>", "port": 8767, "agent_os": "android"}
    """
    # Build list of broadcast targets: subnet-specific first (bypass GlobalProtect),
    # then the global broadcast as a fallback.
    targets = list(dict.fromkeys(_local_subnet_broadcasts() + ["255.255.255.255"]))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout_s)
        try:
            for target in targets:
                sock.sendto(DISCOVERY_MAGIC, (target, DISCOVERY_PORT))
                _log.debug("mac_bridge: UDP discovery sent to %s:%d", target, DISCOVERY_PORT)
            data, addr = sock.recvfrom(512)
            body = json.loads(data.decode("utf-8"))
            if not body.get("ok"):
                return None
            agent_os = str(body.get("agent_os") or "").strip()
            if agent_os and agent_os != "android":
                _log.debug(
                    "mac_bridge: UDP reply from %s is agent_os=%s (not android) — skip",
                    addr[0], agent_os,
                )
                return None
            ip = str(body.get("ip") or addr[0]).strip()
            port = int(body.get("port") or BRIDGE_PORT)
            url = f"http://{ip}:{port}"
            _log.info("mac_bridge: UDP discovery found Android %s (replied from %s)", url, addr[0])
            return url
        finally:
            sock.close()
    except (TimeoutError, OSError, json.JSONDecodeError, KeyError) as e:
        _log.debug("mac_bridge: UDP discovery no reply (%s)", type(e).__name__)
        return None


# ── Transport resolution ──────────────────────────────────────────────────────

def _resolve_base_url(pair_token: Optional[str]) -> Optional[str]:
    """
    Find the Android server URL, trying four transports in order:

      1. ADB forward  → localhost:8767  (always tried first if device is connected)
         Persists last_adb_serial so we reconnect to the same device on next call.

      2. Config file  → android_ip:8767  (LAN or Tailscale IP saved from prior connection)

      3. Tailscale    → reads `tailscale status --json`, finds Android peer by OS/hostname.
         Persists discovered IP on success.

      4. UDP broadcast → 255.255.255.255:8766  (LAN-only, last resort)
         Persists discovered IP on success.
    """
    # ── 1. ADB forward ────────────────────────────────────────────────────────
    device = _adb_connected_device()
    if device and _adb_setup_forward(device):
        url = f"http://127.0.0.1:{BRIDGE_PORT}"
        if _health_ok(url, pair_token):
            _log.info("mac_bridge: connected via ADB forward (device=%s)", device)
            # Remember this device serial for faster reconnect next time
            _write_bridge_config({"last_adb_serial": device})
            return url
        _log.debug("mac_bridge: ADB forward up but Android not responding at %s", url)

    # ── 2. Config file (LAN IP saved from previous session) ──────────────────
    cfg = _read_bridge_config()
    android_ip = str(cfg.get("android_ip") or "").strip()
    if android_ip:
        port = int(cfg.get("android_port") or BRIDGE_PORT)
        url = f"http://{android_ip}:{port}"
        if _health_ok(url, pair_token):
            _log.info("mac_bridge: connected via saved LAN IP %s", url)
            return url
        _log.debug("mac_bridge: saved LAN IP %s not reachable", url)

    # ── 2b. Saved Tailscale IP from previous session ───────────────────────────
    ts_saved = str(cfg.get("tailscale_ip") or "").strip()
    if ts_saved:
        url = f"http://{ts_saved}:{BRIDGE_PORT}"
        if _health_ok(url, pair_token):
            _log.info("mac_bridge: connected via saved Tailscale IP %s", url)
            return url
        _log.debug("mac_bridge: saved Tailscale IP %s not reachable", url)

    # ── 3. Tailscale peer discovery ───────────────────────────────────────────
    ts_ip = _tailscale_android_ip()
    if ts_ip:
        url = f"http://{ts_ip}:{BRIDGE_PORT}"
        if _health_ok(url, pair_token):
            _log.info("mac_bridge: connected via Tailscale IP %s", ts_ip)
            # Save as tailscale_ip — do NOT overwrite android_ip so the LAN IP
            # (192.168.x.x) survives for sessions without Tailscale.
            _write_bridge_config({"tailscale_ip": ts_ip})
            return url
        _log.debug("mac_bridge: Tailscale IP %s not reachable (bridge server may be off)", ts_ip)

    # ── 4. UDP broadcast (LAN only — fails on Tailscale/GlobalProtect) ────────
    _log.info("mac_bridge: trying UDP broadcast discovery on port %d …", DISCOVERY_PORT)
    discovered_url = _udp_discover_android()
    if discovered_url:
        if _health_ok(discovered_url, pair_token):
            discovered_ip = discovered_url.split("//")[1].split(":")[0]
            write_bridge_config(discovered_ip, BRIDGE_PORT)
            _log.info("mac_bridge: connected via UDP discovery, saved IP %s", discovered_ip)
            return discovered_url
        _log.debug("mac_bridge: UDP-discovered url %s not healthy", discovered_url)

    return None


# ── Main bridge loop ──────────────────────────────────────────────────────────

def _poll_next_action(base_url: str, pair_token: Optional[str]) -> Optional[dict]:
    """
    Long-poll GET /action/next.
    Returns action dict when ready, None on timeout (normal) or error.
    """
    body = _http_get(f"{base_url}/action/next", pair_token, LONG_POLL_TIMEOUT_S + 5)
    if body is None:
        return None
    if not body.get("ok"):
        err = body.get("error", "unknown")
        _log.warning("mac_bridge: /action/next error=%s", err)
        if err in ("invalid_token", "not_paired"):
            _log.warning(
                "mac_bridge: pair token rejected — re-pair via: "
                "adb reverse tcp:8765 tcp:8765  then scan QR in Mac agent console (z)"
            )
        return None
    return body.get("action")  # None = poll timeout (normal); dict = action ready


def _bridge_loop(
    execute_action_fn: Callable[[dict], None],
    stop_event: threading.Event,
    get_state_fn: Optional[Callable[[], dict]] = None,
) -> None:
    backoff = RECONNECT_BASE_S
    base_url: Optional[str] = None
    # Mutable refs so the audio observer closure can always use the current URL/token.
    _url_ref: list[Optional[str]] = [None]
    _token_ref: list[Optional[str]] = [None]
    _observer_registered = False

    while not stop_event.is_set():
        pair_token = _read_pair_token()

        # Re-probe if we have no URL or lost connectivity
        if base_url is None or not _health_ok(base_url, pair_token):
            base_url = _resolve_base_url(pair_token)
            if base_url is None:
                # Use shorter backoff when an ADB device is connected so we recover
                # as soon as the Android app (re)starts the bridge server.
                adb_present = _adb_connected_device() is not None
                effective_max = RECONNECT_MAX_ADB_S if adb_present else RECONNECT_MAX_S
                _log.info(
                    "mac_bridge: Android bridge not reachable "
                    "(adb_present=%s). Retry in %ds.",
                    adb_present,
                    backoff,
                )
                stop_event.wait(backoff)
                backoff = min(backoff * 2, effective_max)
                continue
            backoff = RECONNECT_BASE_S
            _url_ref[0] = base_url
            _token_ref[0] = pair_token
            _log.info("mac_bridge: polling %s/action/next", base_url)

            # Push current state on every new connection.
            if get_state_fn is not None:
                try:
                    state = get_state_fn()
                    ok = _post_state(base_url, pair_token, state)
                    _log.info("mac_bridge: POST /state on connect ok=%s", ok)
                except Exception as _se:
                    _log.warning("mac_bridge: POST /state on connect failed: %s", _se)

            # Register the audio observer once so it pushes state on every device change.
            if not _observer_registered and get_state_fn is not None:
                import sys as _sys
                if _sys.platform == "darwin":
                    try:
                        from macos_audio import get_cache as _get_cache

                        def _on_audio_change(_devs: list) -> None:
                            url = _url_ref[0]
                            tok = _token_ref[0]
                            if url:
                                try:
                                    _post_state(url, tok, get_state_fn())
                                except Exception as _ce:
                                    _log.warning("mac_bridge: audio observer POST failed: %s", _ce)

                        _get_cache().start_observer(_on_audio_change, interval_s=5.0)
                        _log.info("mac_bridge: audio observer registered for state push")
                    except Exception as _oe:
                        _log.warning("mac_bridge: could not register audio observer: %s", _oe)
                _observer_registered = True

        action = _poll_next_action(base_url, pair_token)
        if action is None:
            continue  # Normal long-poll timeout or transient error — re-poll immediately

        _log.info("mac_bridge: action type=%s", action.get("type", "?"))
        try:
            execute_action_fn(action)
            # For audio selections: push updated state immediately so the Android UI
            # reflects the new active device without waiting for the observer interval.
            if action.get("type") == "audio_output_select" and get_state_fn is not None:
                try:
                    import time as _t
                    _t.sleep(0.3)  # brief wait for CoreAudio to propagate the change
                    _post_state(base_url, pair_token, get_state_fn())
                    _log.info("mac_bridge: post-action state push after audio_output_select")
                except Exception as _pe:
                    _log.warning("mac_bridge: post-action state push failed: %s", _pe)
        except Exception as e:
            _log.warning("mac_bridge: execute error: %s", e)


def start_mac_bridge(
    execute_action_fn: Callable[[dict], None],
    stop_event: threading.Event,
    get_state_fn: Optional[Callable[[], dict]] = None,
) -> threading.Thread:
    """
    Start the Mac bridge client in a daemon thread.
    execute_action_fn(action_dict) is called for each action from Android.
    Same JSON format as POST /action on the traditional agent.

    get_state_fn() — optional; called to build the POST /state payload on connect
    and whenever the audio device list changes (macOS only).
    Should return e.g. {"audio_outputs": [...]} or an empty dict.
    """
    t = threading.Thread(
        target=_bridge_loop,
        args=(execute_action_fn, stop_event, get_state_fn),
        name="deckbridge-mac-bridge",
        daemon=True,
    )
    t.start()
    _log.info(
        "mac_bridge: started (ADB → saved IP → Tailscale → UDP). Config: %s",
        _BRIDGE_CONFIG_JSON,
    )
    return t