#!/usr/bin/env python3
"""
DeckBridge LAN agent for macOS (Python).

- GET  /health  -> {"ok": true, "pairing": ...}
- POST /action  -> JSON action (see README): combo | media | text | key (pynput)
- Pairing v1: POST/GET /v1/pairing/sessions, POST .../cancel, POST /v1/pairing/host/respond, …
- Console UX: structured status + optional stdin menu (`agent_ux.py`).

Run: python server.py [port]
Default port 8765 (must match DeckBridge Settings on the phone).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Union
from urllib.parse import urlparse


def _package_dir() -> Path:
    """Source tree when running as `python server.py`; bundle dir when frozen (PyInstaller)."""
    if getattr(sys, "frozen", False):
        # onefile: extracted files under _MEIPASS; onedir: dependencies live next to the executable
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_PKG_DIR = _package_dir()
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))
from agent_ux import AgentUx, configure_logging
from pairing_manager import PairingManager

_action_log = logging.getLogger("deckbridge.action")
_discovery_log = logging.getLogger("deckbridge.discovery")
_http_log = logging.getLogger("deckbridge.http")
_pairing_http_log = logging.getLogger("deckbridge.pairing_http")

_single_instance_mutex = None  # set in main() to hold the Win32 mutex handle

# UDP port for LAN discovery (Android sends MAGIC here; we reply with JSON ip + HTTP port).
DISCOVERY_PORT = 8766
DISCOVER_MAGIC = b"DECKBRIDGE_DISCOVER_v1"

_discovery_lock = threading.Lock()
# Thread-safe counters for /health + Logcat (helps debug “phone does not see PC”).
_discovery_stats: dict[str, Any] = {
    "listening": False,
    "replies_sent": 0,
    "packets_ignored_wrong_magic": 0,
    "send_errors": 0,
    "last_client": None,
    "last_reply_preview": None,
}


def _discovery_snapshot() -> dict[str, Any]:
    with _discovery_lock:
        return dict(_discovery_stats)

# v2 names + profile=all: older rules may only have applied to "Private" Wi‑Fi profile.
_FW_RULE_TCP = "DeckBridge LAN Agent TCP 8765"
_FW_RULE_UDP = "DeckBridge LAN Agent UDP 8766"
_SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:
    from pynput.keyboard import Controller, Key
except ImportError:
    print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
    raise

KEY_ALIASES = {
    "ctrl": Key.ctrl_l,
    "control": Key.ctrl_l,
    "shift": Key.shift,
    "alt": Key.alt,
    "cmd": Key.cmd,
    "win": Key.cmd,
    "super": Key.cmd,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
}

kb = Controller()

MEDIA_ACTIONS: dict[str, Any] = {
    "vol_up": Key.media_volume_up,
    "vol_down": Key.media_volume_down,
    "mute": Key.media_volume_mute,
    "play_pause": Key.media_play_pause,
    "next_track": Key.media_next,
    "prev_track": Key.media_previous,
}

SINGLE_KEY_TOKENS: dict[str, Any] = {
    "enter": Key.enter,
    "return": Key.enter,
    "escape": Key.esc,
    "esc": Key.esc,
    "tab": Key.tab,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
}

_MAX_TEXT_LEN = 4000


def _agent_os_label() -> str:
    """Stable label for Android discovery /health (`windows`, `darwin`, …)."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return sys.platform


def resolve_token(tok: str) -> Union[Key, str]:
    t = tok.lower().strip()
    if t in KEY_ALIASES:
        return KEY_ALIASES[t]
    if len(t) == 1:
        return t
    raise ValueError(f"Unknown key token: {tok!r}")


def press_combo(keys: list[str]) -> None:
    resolved = [resolve_token(k) for k in keys]
    for k in resolved:
        kb.press(k)
    for k in reversed(resolved):
        kb.release(k)


def tap_media(action: str) -> None:
    k = MEDIA_ACTIONS.get(action.strip().lower())
    if k is None:
        raise ValueError(f"unknown media action: {action!r}")
    kb.press(k)
    kb.release(k)


def tap_named_key(key_token: str) -> None:
    t = key_token.strip().lower()
    k = SINGLE_KEY_TOKENS.get(t)
    if k is None:
        k = resolve_token(t)
    kb.press(k)
    kb.release(k)


def type_text_payload(text: str) -> None:
    if len(text) > _MAX_TEXT_LEN:
        raise ValueError(f"text too long (max {_MAX_TEXT_LEN})")
    kb.type(text)


def execute_lan_action(data: dict[str, Any]) -> None:
    """Dispatch POST /action JSON. Raises ValueError on bad input; other errors propagate."""
    typ = str(data.get("type") or "").strip().lower()
    if typ == "combo":
        keys = data.get("keys") or []
        if not isinstance(keys, list) or not keys:
            raise ValueError("keys required for type combo")
        press_combo([str(k) for k in keys])
        _action_log.info("executed combo keys=%s", keys)
        return
    if typ == "media":
        action = str(data.get("action") or "").strip().lower()
        tap_media(action)
        _action_log.info("executed media action=%s", action)
        return
    if typ == "text":
        text = str(data.get("text") or "")
        type_text_payload(text)
        _action_log.info("executed text len=%d", len(text))
        return
    if typ == "key":
        key = str(data.get("key") or "").strip().lower()
        if not key:
            raise ValueError("key required for type key")
        tap_named_key(key)
        _action_log.info("executed key token=%s", key)
        return
    if typ == "audio_output_select":
        if sys.platform != "darwin":
            raise ValueError("audio_output_select is only supported on macOS")
        uid = str(data.get("uid") or "").strip()
        if not uid:
            raise ValueError("uid required for type audio_output_select")
        try:
            from macos_audio import set_default_output, get_cache
            ok = set_default_output(uid)
            if not ok:
                raise ValueError(f"device uid not found or CoreAudio error: {uid!r}")
            # Refresh cache so the next state push reflects the new active device
            get_cache().refresh()
            _action_log.info("audio_output_select uid=%s ok=%s", uid, ok)
        except ImportError:
            raise ValueError("macos_audio module not available")
        return
    raise ValueError(f"unsupported action type: {typ!r}")


def _ui_html_path() -> str | None:
    """Resolve ui/index.html — source tree and PyInstaller bundle."""
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [
        Path(meipass) / "ui" / "index.html" if meipass else None,
        Path(__file__).resolve().parent / "ui" / "index.html",
    ]
    for p in candidates:
        if p and p.exists():
            return str(p)
    return None


def _read_ui_version() -> str:
    try:
        changelog = Path(__file__).resolve().parent / "CHANGELOG.md"
        with changelog.open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("## ["):
                    return line[4:line.index("]")]
    except Exception:
        pass
    return "—"


def _get_update_state() -> dict:
    try:
        from update_checker import get_update_state
        return get_update_state()
    except Exception:
        return {"update_available": False, "latest_version": None, "download_url": None}


def _action_summary(typ: str, data: dict[str, Any]) -> str:
    """Short human-readable summary of an /action payload for the recent-actions log."""
    t = (typ or "").strip().lower()
    if t == "combo":
        keys = data.get("keys") or []
        return " + ".join(str(k) for k in keys)
    if t == "media":
        return str(data.get("action", "?"))
    if t == "text":
        txt = str(data.get("text", ""))
        short = txt[:20]
        return f'"{short}"' + ("…" if len(txt) > 20 else "")
    if t == "key":
        return str(data.get("key", "?"))
    if t == "audio_output_select":
        return str(data.get("uid", "?"))[:20]
    return t or "?"


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _pair_token_from_headers(handler: BaseHTTPRequestHandler) -> str | None:
    direct = handler.headers.get("X-DeckBridge-Pair-Token") or handler.headers.get(
        "x-deckbridge-pair-token"
    )
    if direct:
        return direct.strip()
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


class DeckBridgeHTTPServer(ThreadingHTTPServer):
    """Holds [pairing_manager] for handlers (set after construction)."""

    pairing_manager: PairingManager
    agent_ux: AgentUx | None = None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _operator_ux(self) -> AgentUx | None:
        return getattr(self.server, "agent_ux", None)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("DECKBRIDGE_HTTP_TRACE", "").strip() != "1":
            try:
                line = format % args if args else format
            except Exception:
                line = str(format)
            if "GET /health" in line:
                return
        super().log_message(format, *args)

    def send_json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        pm: PairingManager = self.server.pairing_manager  # type: ignore[attr-defined]
        if path == "/health":
            _http_log.info(
                "GET /health peer=%s:%s",
                self.client_address[0],
                self.client_address[1],
            )
            st = pm.agent_pairing_state()
            pr = pm.paired_record()
            pairing: dict[str, Any] = {
                "agent_state": st,
                "paired": pr is not None,
                "action_requires_pair_token": pr is not None,
            }
            # Optional X-DeckBridge-Pair-Token: lets the phone validate a persisted link without POST /action.
            tok = _pair_token_from_headers(self)
            if tok is not None:
                if pr is None:
                    pairing["pair_token_valid"] = False
                else:
                    pairing["pair_token_valid"] = pm.verify_pair_token(tok)
            self.send_json(
                200,
                {
                    "ok": True,
                    "agent_os": _agent_os_label(),
                    "pairing": pairing,
                    "lan_discovery": _discovery_snapshot(),
                },
            )
            ux = self._operator_ux()
            if ux:
                ux.note_client_activity()
            return
        if path == "/v1/pairing/host/status":
            pr = pm.paired_record()
            body: dict[str, Any] = {
                "ok": True,
                "agent_pairing_state": pm.agent_pairing_state(),
                "paired_device": None,
            }
            if pr:
                body["paired_device"] = {
                    "mobile_device_id": pr.mobile_device_id,
                    "mobile_display_name": pr.mobile_display_name,
                    "paired_at_ms": pr.paired_at_ms,
                }
            self.send_json(200, body)
            return
        parts = path.split("/")
        if len(parts) == 5 and parts[1] == "v1" and parts[2] == "pairing" and parts[3] == "sessions":
            sid = parts[4]
            sess = pm.get_session(sid)
            if sess is None:
                _pairing_http_log.info(
                    "GET /v1/pairing/sessions/%s peer=%s:%s → 404 session_not_found",
                    sid,
                    self.client_address[0],
                    self.client_address[1],
                )
                self.send_json(404, {"ok": False, "error": "session_not_found"})
                return
            _pairing_http_log.info(
                "GET /v1/pairing/sessions/%s peer=%s:%s status=%s code=%s",
                sid,
                self.client_address[0],
                self.client_address[1],
                sess.status,
                sess.pairing_code,
            )
            self.send_json(200, sess.to_public_dict())
            return
        # Serve the companion UI
        if path == "/ui":
            html_path = _ui_html_path()
            if html_path is None:
                self.send_json(404, {"ok": False, "error": "ui not found"})
                return
            try:
                with open(html_path, encoding="utf-8") as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            except OSError as e:
                self.send_json(500, {"ok": False, "error": str(e)})
            return
        # Status API for the companion UI
        if path == "/api/status":
            ux = self._operator_ux()
            from agent_ux import operational_label
            import time as _time
            state = operational_label(pm, ux._last_client_monotonic) if ux else "idle"
            pr = pm.paired_record()
            device_name = None
            if pr:
                device_name = pr.mobile_display_name or pr.mobile_device_id[:8]
            last_ago = None
            if ux and ux._last_client_monotonic is not None:
                elapsed = _time.monotonic() - ux._last_client_monotonic
                last_ago = f"hace {int(elapsed)} s" if elapsed < 60 else f"hace {int(elapsed // 60)} m"
            acc_ok = True
            try:
                from macos_accessibility import accessibility_trusted
                acc_ok = accessibility_trusted() is not False
            except Exception:
                pass
            self.send_json(200, {
                "state": state,
                "device_name": device_name,
                "lan_ip": getattr(ux, "_lan_ip", "—") if ux else "—",
                "port": getattr(ux, "_http_port", 8765) if ux else 8765,
                "last_action_ago": last_ago,
                "last_actions": ux.get_recent_actions() if ux else [],
                "version": _read_ui_version(),
                "accessibility_ok": acc_ok,
                "udp_ok": _discovery_stats.get("listening", False),
                "update": _get_update_state(),
            })
            return
        self.send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        pm: PairingManager = self.server.pairing_manager  # type: ignore[attr-defined]

        # Companion UI actions (localhost-only, no auth required)
        if path == "/api/pair":
            ux = self._operator_ux()
            if ux is None:
                self.send_json(503, {"ok": False, "error": "agent not ready"})
                return
            threading.Thread(target=ux.menu_host_qr_pairing, args=(pm,), daemon=True).start()
            self.send_json(200, {"ok": True})
            return
        if path == "/api/forget":
            ux = self._operator_ux()
            if ux is None:
                self.send_json(503, {"ok": False, "error": "agent not ready"})
                return
            threading.Thread(target=ux.menu_unpair, args=(pm,), daemon=True).start()
            self.send_json(200, {"ok": True})
            return

        if path == "/v1/pairing/sessions":
            data = _read_json_body(self)
            if data is None:
                self.send_json(400, {"ok": False, "error": "invalid json"})
                return
            mid = str(data.get("mobile_device_id") or "").strip()
            if not mid:
                self.send_json(400, {"ok": False, "error": "mobile_device_id required"})
                return
            name = str(data.get("mobile_display_name") or "Android")
            sess = pm.create_session(mid, name)
            http_port = int(self.server.server_address[1])
            _pairing_http_log.info(
                "POST /v1/pairing/sessions peer=%s:%s mobile_id=%s… name=%r → session_id=%s code=%s agent_state=%s",
                self.client_address[0],
                self.client_address[1],
                mid[:12],
                name,
                sess.session_id,
                sess.pairing_code,
                pm.agent_pairing_state(),
            )
            ux = self._operator_ux()
            if ux:
                ux.on_pairing_session_created(pm, sess)
            self.send_json(
                200,
                {
                    "ok": True,
                    "session_id": sess.session_id,
                    "pairing_code": sess.pairing_code,
                    "expires_at_ms": sess.expires_ms,
                    "status": sess.status,
                },
            )
            return

        if path == "/v1/pairing/host/qr-sessions":
            data = _read_json_body(self) or {}
            label = str(data.get("host_label") or "").strip() or socket.gethostname()
            sess = pm.create_host_qr_session(label)
            http_port = int(self.server.server_address[1])
            lan_ip = _lan_ipv4_for_reply()
            _pairing_http_log.info(
                "POST /v1/pairing/host/qr-sessions peer=%s:%s host_label=%r → session_id=%s code=%s",
                self.client_address[0],
                self.client_address[1],
                label,
                sess.session_id,
                sess.pairing_code,
            )
            ux = self._operator_ux()
            if ux:
                ux.on_host_qr_session_created(pm, sess, lan_ip, http_port, label)
            self.send_json(
                200,
                {
                    "ok": True,
                    "session_id": sess.session_id,
                    "pairing_code": sess.pairing_code,
                    "expires_at_ms": sess.expires_ms,
                    "status": sess.status,
                },
            )
            return

        if path.startswith("/v1/pairing/sessions/") and path.endswith("/claim"):
            inner = path[len("/v1/pairing/sessions/") : -len("/claim")]
            sid = inner.strip("/")
            data = _read_json_body(self)
            if data is None:
                self.send_json(400, {"ok": False, "error": "invalid json"})
                return
            mid = str(data.get("mobile_device_id") or "").strip()
            name = str(data.get("mobile_display_name") or "Android")
            ok, reason = pm.claim_session(sid, mid, name)
            if not ok:
                code = 404 if reason == "session_not_found" else 409 if reason == "device_mismatch" else 400
                _pairing_http_log.warning(
                    "POST …/sessions/%s/claim FAIL peer=%s:%s reason=%s http=%s",
                    sid,
                    self.client_address[0],
                    self.client_address[1],
                    reason,
                    code,
                )
                self.send_json(code, {"ok": False, "error": reason})
                return
            _pairing_http_log.info(
                "POST …/sessions/%s/claim peer=%s:%s mobile_id=%s… ok",
                sid,
                self.client_address[0],
                self.client_address[1],
                mid[:12],
            )
            self.send_json(200, {"ok": True, "session_id": sid})
            return

        if path.startswith("/v1/pairing/host/qr-sessions/") and path.endswith("/cancel"):
            inner = path[len("/v1/pairing/host/qr-sessions/") : -len("/cancel")]
            sid = inner.strip("/")
            ok, reason = pm.cancel_host_qr_invite(sid)
            if not ok:
                self.send_json(400, {"ok": False, "error": reason})
                return
            ux = self._operator_ux()
            if ux:
                ux.on_host_qr_invite_cancelled(sid)
            self.send_json(200, {"ok": True})
            return

        if path.startswith("/v1/pairing/sessions/") and path.endswith("/cancel"):
            inner = path[len("/v1/pairing/sessions/") : -len("/cancel")]
            sid = inner.strip("/")
            data = _read_json_body(self)
            if data is None:
                self.send_json(400, {"ok": False, "error": "invalid json"})
                return
            mid = str(data.get("mobile_device_id") or "").strip()
            ok, reason = pm.cancel_session(sid, mid)
            if not ok:
                self.send_json(400, {"ok": False, "error": reason})
                return
            ux = self._operator_ux()
            if ux:
                ux.on_session_cancelled_remote(sid)
            self.send_json(200, {"ok": True})
            return

        if path == "/v1/pairing/host/respond":
            data = _read_json_body(self)
            if data is None:
                self.send_json(400, {"ok": False, "error": "invalid json"})
                return
            if "approve" not in data:
                self.send_json(400, {"ok": False, "error": "approve_required"})
                return
            approve = bool(data["approve"])
            _pairing_http_log.info(
                "POST /v1/pairing/host/respond peer=%s:%s approve=%s session_id=%r code=%r",
                self.client_address[0],
                self.client_address[1],
                approve,
                data.get("session_id"),
                data.get("pairing_code"),
            )
            pcode = data.get("pairing_code")
            sid = data.get("session_id")
            ok, reason, sess = pm.host_respond(
                approve=approve,
                pairing_code=str(pcode) if pcode else None,
                session_id=str(sid) if sid else None,
            )
            ux = self._operator_ux()
            if not ok:
                if ux:
                    ux.on_host_respond_failed(reason)
                code = 404 if reason == "session_not_found" else 400
                self.send_json(code, {"ok": False, "error": reason})
                return
            out: dict[str, Any] = {"ok": True, "result": reason}
            if sess and reason == "consumed":
                out["session_id"] = sess.session_id
                out["pair_token"] = sess.pair_token
                out["mobile_device_id"] = sess.mobile_device_id
            if ux:
                ux.on_host_respond_result(pm, ok, reason, sess)
            self.send_json(200, out)
            return

        if path == "/v1/pairing/host/unpair":
            pm.unpair()
            ux = self._operator_ux()
            if ux:
                ux.on_unpair()
            self.send_json(200, {"ok": True})
            return

        if path != "/action":
            self.send_json(404, {"ok": False, "error": "not found"})
            return

        if not pm.verify_pair_token(_pair_token_from_headers(self)):
            _http_log.warning(
                "POST /action unauthorized peer=%s:%s (pair token missing or invalid)",
                self.client_address[0],
                self.client_address[1],
            )
            self.send_json(
                401,
                {
                    "ok": False,
                    "error": "pair_token_required",
                    "detail": "This agent is paired; send header X-DeckBridge-Pair-Token from the phone.",
                },
            )
            return

        data = _read_json_body(self)
        if data is None:
            self.send_json(400, {"ok": False, "error": "invalid json"})
            return
        typ = str(data.get("type") or "")
        _http_log.info(
            "POST /action peer=%s:%s type=%s",
            self.client_address[0],
            self.client_address[1],
            typ,
        )
        _action_log.info("received /action type=%s", typ)
        try:
            execute_lan_action(data)
        except ValueError as e:
            _action_detail = _action_summary(typ, data)
            ux = self._operator_ux()
            if ux is not None:
                ux.record_action(typ, _action_detail, ok=False)
            self.send_json(400, {"ok": False, "error": str(e)})
            return
        except Exception as e:
            _action_log.exception("action execution failed")
            err_body: dict[str, Any] = {"ok": False, "error": str(e)}
            if sys.platform == "darwin":
                try:
                    from macos_accessibility import accessibility_trusted

                    if accessibility_trusted() is False:
                        err_body["accessibility_trusted"] = False
                        err_body["hint"] = (
                            "macOS Accessibility is off for this process: System Settings → "
                            "Privacy & Security → Accessibility (enable DeckBridgeMacAgent, or Terminal/IDE "
                            "if you run from source). Pairing and GET /health do not require this; POST /action does."
                        )
                        _http_log.warning(
                            "POST /action 500 while Accessibility not trusted (pairing still OK): %s",
                            e,
                        )
                except Exception:
                    pass
            _action_detail = _action_summary(typ, data)
            ux = self._operator_ux()
            if ux is not None:
                ux.record_action(typ, _action_detail, ok=False)
            self.send_json(500, err_body)
            return
        _action_detail = _action_summary(typ, data)
        ux = self._operator_ux()
        if ux:
            ux.note_client_activity()
            ux.record_action(typ, _action_detail, ok=True)
        self.send_json(200, {"ok": True})


def _lan_ipv4_for_reply() -> str:
    """Best-effort primary IPv4 when we do not know the peer (e.g. console banner)."""
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.connect(("8.8.8.8", 80))
        return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sk.close()


def _lan_ipv4_toward(peer_ip: str) -> str:
    """
    IPv4 to put in discovery JSON so the phone opens HTTP on the same interface that can reach
    the discoverer. Using only 8.8.8.8 breaks on multi-NIC PCs, offline hosts, or wrong default
    route (often returns 127.0.0.1 — the phone then "finds" a host it cannot use).
    """
    p = (peer_ip or "").strip()
    if not p or p == "0.0.0.0":
        return _lan_ipv4_for_reply()
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.connect((p, 9))
        ip = sk.getsockname()[0]
        if ip and ip != "0.0.0.0":
            return ip
    except OSError:
        pass
    finally:
        sk.close()
    return _lan_ipv4_for_reply()


def _discovery_responder_loop(http_port: int) -> None:
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sk.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError as e:
        _discovery_log.error(
            "UDP discovery bind 0.0.0.0:%s failed (%s). Inbound UDP %s may be blocked or port in use — discovery disabled.",
            DISCOVERY_PORT,
            e,
            DISCOVERY_PORT,
        )
        with _discovery_lock:
            _discovery_stats["listening"] = False
        return
    with _discovery_lock:
        _discovery_stats["listening"] = True
    _discovery_log.info(
        "UDP discovery listening on 0.0.0.0:%s http_port=%s magic_prefix=%r",
        DISCOVERY_PORT,
        http_port,
        DISCOVER_MAGIC[:24],
    )
    while True:
        try:
            data, addr = sk.recvfrom(512)
        except OSError as e:
            _discovery_log.warning("UDP discovery recv stopped: %s", e)
            break
        magic_ok = bool(len(data) >= len(DISCOVER_MAGIC) and data.startswith(DISCOVER_MAGIC))
        _discovery_log.info(
            "UDP recv %dB from %s:%s magic_ok=%s",
            len(data),
            addr[0],
            addr[1],
            magic_ok,
        )
        if not magic_ok:
            with _discovery_lock:
                _discovery_stats["packets_ignored_wrong_magic"] += 1
            _discovery_log.info(
                "UDP discovery ignored wrong_magic from %s:%s (want prefix %r)",
                addr[0],
                addr[1],
                DISCOVER_MAGIC[:20],
            )
            continue
        ip = _lan_ipv4_toward(str(addr[0]))
        if ip == "127.0.0.1":
            _discovery_log.warning(
                "UDP reply ip is loopback toward_peer=%s — check NIC/offline; phone cannot use 127.0.0.1",
                addr[0],
            )
        payload = json.dumps(
            {"ok": True, "ip": ip, "port": http_port, "agent_os": _agent_os_label()},
        ).encode("utf-8")
        preview = payload.decode("utf-8", errors="replace")[:200]
        try:
            sk.sendto(payload, addr)
        except OSError as e:
            with _discovery_lock:
                _discovery_stats["send_errors"] += 1
            _discovery_log.warning("UDP discovery sendto failed to %s:%s: %s", addr[0], addr[1], e)
            continue
        with _discovery_lock:
            _discovery_stats["replies_sent"] += 1
            _discovery_stats["last_client"] = f"{addr[0]}:{addr[1]}"
            _discovery_stats["last_reply_preview"] = preview
        _discovery_log.info("UDP discovery reply to %s:%s body=%s", addr[0], addr[1], preview)
    try:
        sk.close()
    except OSError:
        pass
    with _discovery_lock:
        _discovery_stats["listening"] = False
    _discovery_log.info("UDP discovery socket closed")


def start_discovery_responder(http_port: int) -> None:
    t = threading.Thread(
        target=_discovery_responder_loop,
        args=(http_port,),
        name="deckbridge-discovery",
        daemon=True,
    )
    t.start()


def _windows_try_remove_inbound_block_rules_for_exe(exe_path: Path) -> None:
    """
    Windows may create per-app **Inbound Block** rules for this .exe (e.g. user clicked
    "Block" on a prompt, or duplicate entries). Those blocks override port-scoped Allow rules
    for the same program on **Public** profile — LAN clients (phones) then time out on TCP
    and never see UDP replies, while other apps (e.g. Sunshine) keep working on other ports.

    Best-effort without elevation; removal typically succeeds for rules created in user context.
    """
    if sys.platform != "win32":
        return
    exe = exe_path.name
    env = os.environ.copy()
    env["DECKBRIDGE_EXE"] = str(exe_path.resolve())
    ps = (
        "$n = [System.IO.Path]::GetFileName($env:DECKBRIDGE_EXE); "
        "Get-NetFirewallRule -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DisplayName -ieq $n -and $_.Action -eq 'Block' -and $_.Direction -eq 'Inbound' } | "
        "Remove-NetFirewallRule -ErrorAction SilentlyContinue"
    )
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            creationflags=_SUBPROCESS_FLAGS,
        )
        if p.returncode == 0:
            _discovery_log.info(
                "Windows firewall: removed inbound Block rule(s) matching exe name %s if any existed",
                exe,
            )
        else:
            _discovery_log.debug(
                "Windows firewall cleanup (remove Block for %s): exit=%s err=%s",
                exe,
                p.returncode,
                (p.stderr or "")[:300],
            )
    except OSError as e:
        _discovery_log.debug("Windows firewall cleanup skipped: %s", e)


def _windows_firewall_rule_exists(rule_name: str) -> bool:
    p = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
        creationflags=_SUBPROCESS_FLAGS,
    )
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        return False
    low = out.lower()
    if "no rules match" in low or "ninguna regla coincide" in low:
        return False
    return len(out.strip()) > 30


def _maybe_prompt_windows_firewall_inbound(exe_path: Path, http_port: int) -> None:
    """
    Windows only: if inbound rules for this exe are missing, launch an elevated cmd batch
    so the user gets a UAC prompt once. Cannot add rules without admin — this is the
    standard Windows behaviour.
    """
    if sys.platform != "win32":
        return
    if os.environ.get("DECKBRIDGE_SKIP_FIREWALL", "").strip() == "1":
        return
    if not getattr(sys, "frozen", False):
        # python server.py — skip UAC (developer); use .exe for auto rules
        return
    exe_str = str(exe_path.resolve())
    if _windows_firewall_rule_exists(_FW_RULE_TCP) and _windows_firewall_rule_exists(_FW_RULE_UDP):
        return
    try:
        import ctypes
    except ImportError:
        return

    # Two rules: TCP (HTTP) + UDP (discovery), scoped to this executable.
    bat_body = "\r\n".join(
        [
            "@echo off",
            "setlocal EnableDelayedExpansion",
            f'set "DECK_EXE={exe_str}"',
            'set "DECKBRIDGE_EXE=!DECK_EXE!"',
            f"set HTTP_PORT={http_port}",
            f"set UDP_PORT={DISCOVERY_PORT}",
            "powershell -NoProfile -Command \""
            "$n=[System.IO.Path]::GetFileName($env:DECKBRIDGE_EXE); "
            "Get-NetFirewallRule -ErrorAction SilentlyContinue | "
            "Where-Object { $_.DisplayName -ieq $n -and $_.Action -eq 'Block' -and $_.Direction -eq 'Inbound' } | "
            "Remove-NetFirewallRule -ErrorAction SilentlyContinue\"",
            f'netsh advfirewall firewall show rule name="{_FW_RULE_TCP}" >nul 2>&1 || netsh advfirewall firewall add rule name="{_FW_RULE_TCP}" dir=in action=allow protocol=TCP localport=!HTTP_PORT! program="!DECK_EXE!" profile=private,public,domain enable=yes',
            f'netsh advfirewall firewall show rule name="{_FW_RULE_UDP}" >nul 2>&1 || netsh advfirewall firewall add rule name="{_FW_RULE_UDP}" dir=in action=allow protocol=UDP localport=!UDP_PORT! program="!DECK_EXE!" profile=private,public,domain enable=yes',
            "endlocal",
            "exit /b 0",
        ]
    )
    fd, bat_path = tempfile.mkstemp(prefix="deckbridge_fw_", suffix=".bat", text=False)
    os.close(fd)
    bat_file = Path(bat_path)
    bat_file.write_text(bat_body, encoding="utf-8")

    params = f'/c ""{bat_file}""'
    rc = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, None, 1) or 0)
    if rc <= 32:
        if sys.stderr is not None:
            sys.stderr.write(
                "[firewall] No se pudo abrir UAC o fue cancelado. Si el móvil no conecta, "
                "añade reglas entrantes TCP %d y UDP %d para este .exe en el Firewall de Windows.\n"
                % (http_port, DISCOVERY_PORT),
            )
    else:
        if sys.stderr is not None:
            sys.stderr.write(
                "[firewall] Si apareció UAC, acéptalo para permitir TCP %d y UDP %d solo a este programa.\n"
                % (http_port, DISCOVERY_PORT),
            )


def main() -> None:
    global _single_instance_mutex
    if sys.platform == "win32":
        import ctypes as _ctypes
        _single_instance_mutex = _ctypes.windll.kernel32.CreateMutexW(None, False, "DeckBridgeAgentMutex")
        if _ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            import sys as _sys
            _sys.exit(0)

    # Windows consoles default to cp1252; reconfigure to UTF-8 so the banner
    # and operator menu render correctly regardless of the system code page.
    if sys.platform == "win32":
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    configure_logging()
    from session_file_log import start_session_file_log

    start_session_file_log()
    if sys.platform == "darwin":
        try:
            from macos_accessibility import (
                accessibility_trusted,
                request_accessibility_prompt,
                log_accessibility_banner_if_needed,
            )
            log_accessibility_banner_if_needed()
            # If not trusted, trigger the system dialog once (non-blocking).
            # This registers the app in TCC so the user can grant access in System Settings.
            if not accessibility_trusted():
                request_accessibility_prompt()
        except Exception:
            pass

        # Audio device cache — load at startup and watch for changes.
        try:
            from macos_audio import get_cache
            _audio_cache = get_cache()
            devices = _audio_cache.refresh()
            active = next((d["name"] for d in devices if d["is_active"]), "none")
            logging.getLogger("deckbridge.audio").info(
                "audio: %d output device(s) found, active=%r — %s",
                len(devices),
                active,
                ", ".join(d["name"] for d in devices),
            )
            _audio_cache.start_observer(
                lambda devs: logging.getLogger("deckbridge.audio").info(
                    "audio: change detected — %d devices, active=%r",
                    len(devs),
                    next((d["name"] for d in devs if d["is_active"]), "none"),
                ),
                interval_s=5.0,
            )
        except Exception as _ae:
            logging.getLogger("deckbridge.audio").warning(
                "audio: cache init failed (%s) — audio_output_select will still work on demand", _ae
            )
    host = "0.0.0.0"
    port = 8765
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    exe = Path(sys.executable)
    if sys.platform == "win32":
        _windows_try_remove_inbound_block_rules_for_exe(exe)
    _maybe_prompt_windows_firewall_inbound(exe, port)
    start_discovery_responder(port)

    # Mac Bridge Client (inverted arch — Mac connects outbound to Android).
    # Bypasses GlobalProtect inbound blocking on corporate Macs.
    # No-op on Windows (Windows uses the traditional inbound HTTP path).
    if sys.platform == "darwin":
        try:
            from mac_bridge_client import start_mac_bridge

            def _get_bridge_state() -> dict:
                try:
                    from macos_audio import get_cache as _get_cache
                    return {"audio_outputs": _get_cache().get()}
                except Exception:
                    return {}

            _bridge_stop = threading.Event()
            start_mac_bridge(execute_lan_action, _bridge_stop, get_state_fn=_get_bridge_state)
        except Exception as _be:
            logging.getLogger("deckbridge.mac_bridge").warning(
                "mac_bridge: failed to start (%s) — traditional inbound LAN only", _be
            )

    state_dir = Path(os.environ.get("DECKBRIDGE_STATE_DIR", str(Path.home() / ".deckbridge")))
    pairing = PairingManager(state_dir)
    httpd = DeckBridgeHTTPServer((host, port), Handler)
    httpd.pairing_manager = pairing
    ux = AgentUx()
    httpd.agent_ux = ux
    lan_ip = _lan_ipv4_for_reply()

    if sys.platform == "darwin":
        from macos_menubar import DeckBridgeMenuBar
        mb = DeckBridgeMenuBar()
        mb.set_ux_callbacks(
            lambda: ux.menu_host_qr_pairing(pairing),
            lambda: ux.menu_unpair(pairing),
        )
        ux.set_menu_bar(mb)

        from macos_window import DeckBridgeWindow, DeckBridgeApi
        api = DeckBridgeApi(udp_ok_fn=lambda: _discovery_stats.get("listening", False))
        api.set_ux(ux, pairing)
        wm = DeckBridgeWindow(api)
        mb.set_window_manager(wm)

    if sys.platform == "win32":
        from windows_tray import WindowsTray
        tray = WindowsTray()
        tray.set_ux_callbacks(
            lambda: ux.menu_host_qr_pairing(pairing),
            lambda: ux.menu_unpair(pairing),
        )
        ux.set_windows_tray(tray)
        tray.set_agent_version(_read_ui_version())

    ux.on_server_ready(state_dir, port, lan_ip)

    http_thread = threading.Thread(
        target=httpd.serve_forever,
        name="deckbridge-http",
        daemon=True,
    )
    http_thread.start()

    # Start update checker in background (non-blocking, daemon thread).
    try:
        from update_checker import start_update_checker
        _no_gui_flag = os.environ.get("DECKBRIDGE_NO_GUI", "").strip() == "1"
        def _on_update(version: str, url: str) -> None:
            if sys.platform == "darwin" and not _no_gui_flag:
                try:
                    mb.notify_update_available(version, url)
                except Exception:
                    pass
            elif sys.platform == "win32" and not _no_gui_flag:
                try:
                    tray.notify_update_available(version, url)
                except Exception:
                    pass
        start_update_checker(_on_update)
    except Exception as _ue:
        logging.getLogger("deckbridge.update").warning("update checker failed to start: %s", _ue)

    _no_gui = os.environ.get("DECKBRIDGE_NO_GUI", "").strip() == "1"
    if sys.platform not in ("darwin", "win32") or _no_gui:
        threading.Thread(
            target=ux.stdin_loop,
            args=(pairing, httpd),
            name="deckbridge-console-menu",
            daemon=True,
        ).start()

    if sys.platform == "darwin" and not _no_gui:
        mb.run()
    elif sys.platform == "win32" and not _no_gui:
        tray.run()
    else:
        # Headless / DECKBRIDGE_NO_GUI=1 / non-GUI platform
        httpd.serve_forever()


if __name__ == "__main__":
    main()
