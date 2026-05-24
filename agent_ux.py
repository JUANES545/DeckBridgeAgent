"""
Minimal console UX for the DeckBridge LAN agent: structured status, pairing blocks,
QR deeplink, and a lightweight stdin command loop (no desktop GUI).

All stdout here is meant for the human operator; HTTP request lines are filtered separately.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pairing_console_qr import print_pairing_qr_to_stdout
from pairing_manager import PairingManager, PairingSession

# QR popup window (Tkinter) — available on macOS; gracefully absent on Windows.
try:
    from pairing_qr_popup import close_active_qr_popup, launch_pairing_qr_window
    _QR_POPUP_AVAILABLE = True
except ImportError:
    _QR_POPUP_AVAILABLE = False
    def close_active_qr_popup() -> None: pass  # noqa: E704
    def launch_pairing_qr_window(*_a, **_kw) -> None: pass  # noqa: E704

_LOG = logging.getLogger("deckbridge.agent")

W = 62


def _rule(char: str = "─") -> str:
    return char * W


def _box(title: str, lines: list[str]) -> str:
    out = [f"╔{_rule('═')}╗", f"║ {title[: W - 4]:<{W - 4}} ║", f"╠{_rule('═')}╣"]
    for ln in lines:
        s = ln[: W - 4] if len(ln) > W - 4 else ln
        out.append(f"║ {s:<{W - 4}} ║")
    out.append(f"╚{_rule('═')}╝")
    return "\n".join(out)


def build_deeplink(
    host: str,
    http_port: int,
    session_id: str | None,
    host_display: str | None = None,
) -> str:
    """Same shape as Android `DeckbridgePairingPayload` (query keys h, p, v, optional sid, n, os)."""
    h = quote(host.strip(), safe="")
    parts = [f"h={h}", f"p={int(http_port)}", "v=1"]
    if session_id and session_id.strip():
        parts.append(f"sid={quote(session_id.strip(), safe='')}")
    if host_display and str(host_display).strip():
        parts.append(f"n={quote(str(host_display).strip(), safe='')}")
    # Lets Android switch LAN persistence slot before bootstrap (Mac vs Windows).
    if sys.platform == "darwin":
        parts.append("os=mac")
    elif sys.platform == "win32":
        parts.append("os=win")
    return "deckbridge://pair?" + "&".join(parts)


def build_mac_bridge_deeplink(token: str) -> str:
    """
    MAC_BRIDGE direct pairing QR payload.
    No host/port — Android is the server; Mac connects outbound.
    Android reads tok= and calls applyMacBridgeToken() directly (no LAN HTTP needed).
    """
    return f"deckbridge://pair?os=mac&tok={quote(token.strip(), safe='')}&v=1"


def operational_label(pm: PairingManager, last_client_ms: float | None) -> str:
    """
    High-level UX state (not identical to pairing_manager.agent_pairing_state strings).
    """
    try:
        st = pm.agent_pairing_state()
        pr = pm.paired_record()
    except Exception:
        return "error"
    now = time.monotonic()
    recent = last_client_ms is not None and (now - last_client_ms) < 45.0
    if pr is not None and recent:
        return "connected"
    if pr is not None:
        return "paired"
    if st in ("waiting_for_confirmation", "paired_with_pending"):
        return "waiting_for_pairing"
    return "idle"


class AgentUx:
    """Thread-safe operator console + last pairing hints for menu actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lan_ip = "127.0.0.1"
        self._http_port = 8765
        self._state_dir = Path.home() / ".deckbridge"
        self._last_pending_code: str | None = None
        self._last_pending_sid: str | None = None
        self._last_pending_expires_ms: int = 0
        self._last_pending_name: str = ""
        self._last_client_monotonic: float | None = None
        self._startup_error: str | None = None
        self._menu_bar: Any = None
        self._last_ux_label: str = "idle"
        self._recent_actions: list[dict] = []   # ring buffer, max 10
        self._recent_actions_lock = threading.Lock()

    def set_menu_bar(self, mb) -> None:
        self._menu_bar = mb

    def configure(self, lan_ip: str, http_port: int, state_dir: Path) -> None:
        with self._lock:
            self._lan_ip = lan_ip.strip() or "127.0.0.1"
            self._http_port = int(http_port)
            self._state_dir = state_dir

    def set_startup_error(self, msg: str | None) -> None:
        with self._lock:
            self._startup_error = msg

    def note_client_activity(self, pm: Any = None) -> None:
        with self._lock:
            self._last_client_monotonic = time.monotonic()
        if self._menu_bar is not None and pm is not None:
            new_label = operational_label(pm, self._last_client_monotonic)
            if new_label != self._last_ux_label:
                self._last_ux_label = new_label
                pr = pm.paired_record()
                device_name: str | None = None
                if pr is not None:
                    device_name = pr.mobile_display_name if pr.mobile_display_name else pr.mobile_device_id[:8]
                self._menu_bar.update_status(new_label, device_name, self._lan_ip)

    def on_server_ready(self, state_dir: Path, http_port: int, lan_ip: str) -> None:
        self.configure(lan_ip, http_port, state_dir)
        lines = [
            f"http://{lan_ip}:{http_port}/",
            "",
            "  z  vincular QR  ·  s  estado  ·  q  salir",
            "  h  ayuda",
        ]
        if self._startup_error:
            lines += ["", f"⚠  {self._startup_error}"]
        _emit(_box("DeckBridge — listo ✓", lines))
        if self._menu_bar is not None:
            self._menu_bar.update_status("idle", None, lan_ip)

    def on_pairing_session_created(self, pm: PairingManager, sess: PairingSession) -> None:
        with self._lock:
            self._last_pending_code = sess.pairing_code
            self._last_pending_sid = sess.session_id
            self._last_pending_expires_ms = sess.expires_ms
            self._last_pending_name = sess.mobile_display_name
        deeplink = build_deeplink(self._lan_ip, self._http_port, sess.session_id, None)
        curl = (
            f'curl -s -X POST http://127.0.0.1:{self._http_port}/v1/pairing/host/respond '
            f'-H "Content-Type: application/json" '
            f"-d '{{\"pairing_code\":\"{sess.pairing_code}\",\"approve\":true}}'"
        )
        ttl_s = max(0, (sess.expires_ms - int(time.time() * 1000)) // 1000)
        lines = [
            f"Session : {sess.session_id}",
            f"Phone   : {sess.mobile_display_name!r}  (device id prefix: {(sess.mobile_device_id or '')[:12]}…)",
            f"Code    :  {sess.pairing_code}   (TTL ~{ttl_s // 60}m {ttl_s % 60}s)",
            "",
            "Approve on this Mac (or type  a  in this console):",
            f"  {curl}",
            "",
            "Reject:",
            f'  curl -s -X POST http://127.0.0.1:{self._http_port}/v1/pairing/host/respond '
            f'-H "Content-Type: application/json" '
            f"-d '{{\"pairing_code\":\"{sess.pairing_code}\",\"approve\":false}}'",
            "",
            "QR / deep link (scan from DeckBridge app):",
            f"  {deeplink}",
        ]
        _emit(_box("Pairing — waiting for approval", lines))
        self._write_deeplink_file(deeplink)
        _LOG.info(
            "pairing UX session_created session_id=%s code=%s expires_ms=%s",
            sess.session_id,
            sess.pairing_code,
            sess.expires_ms,
        )
        if self._menu_bar is not None:
            self._menu_bar.update_status("waiting_for_pairing", None, self._lan_ip)

    def on_host_qr_session_created(
        self,
        pm: PairingManager,
        sess: PairingSession,
        lan_ip: str,
        http_port: int,
        host_label: str,
    ) -> None:
        """HTTP POST /v1/pairing/host/qr-sessions or console [z] (via loopback) created a host invite."""
        deeplink = build_deeplink(lan_ip, http_port, sess.session_id, host_label)
        with self._lock:
            self._last_pending_code = sess.pairing_code
            self._last_pending_sid = sess.session_id
            self._last_pending_expires_ms = sess.expires_ms
            self._last_pending_name = sess.mobile_display_name
        _LOG.info(
            "host QR session_created session_id=%s code=%s deeplink=%s",
            sess.session_id,
            sess.pairing_code,
            deeplink,
        )
        self._write_deeplink_file(deeplink)
        _emit(
            _box(
                "Pairing — host QR invite",
                [
                    f"Code: {sess.pairing_code}  ·  session: {sess.session_id[:20]}…",
                    "Scan below (console) or the popup window if it opens.",
                    f"Deeplink: {deeplink}",
                ],
            ),
        )
        printed = print_pairing_qr_to_stdout(deeplink)
        if not printed:
            _LOG.warning("console QR not printed (install qrcode package)")
        _LOG.info("host QR launching Tk popup session_id=%s", sess.session_id)
        launch_pairing_qr_window(
            pairing_manager=pm,
            session=sess,
            deeplink=deeplink,
            http_port=http_port,
            host_label=host_label,
        )
        _emit("(menu) If no window appeared: use the ASCII QR above or open the deeplink on the phone.)")
        if self._menu_bar is not None:
            self._menu_bar.update_status("waiting_for_pairing", None, self._lan_ip)

    def on_host_qr_invite_cancelled(self, session_id: str) -> None:
        close_active_qr_popup()
        with self._lock:
            if self._last_pending_sid == session_id:
                self._last_pending_code = None
                self._last_pending_sid = None
        _LOG.info("host QR invite cancelled session_id=%s", session_id)

    def on_host_respond_result(self, pm: PairingManager, ok: bool, reason: str, sess: Any) -> None:
        close_active_qr_popup()
        if ok and reason == "consumed":
            pr = pm.paired_record()
            with self._lock:
                self._last_pending_code = None
                self._last_pending_sid = None
                self._last_pending_expires_ms = 0
            lines = [
                f"Session consumed: {getattr(sess, 'session_id', '?')}",
                f"Link saved under: {self._state_dir / 'paired_device.json'}",
            ]
            if pr:
                lines += [
                    f"Paired device: {pr.mobile_display_name!r}",
                    f"  mobile_device_id prefix: {pr.mobile_device_id[:12]}…",
                    f"  pair_token prefix: {pr.pair_token[:18]}…",
                ]
            _emit(_box("Pairing — approved (device linked)", lines))
            _LOG.info("pairing UX consumed session_id=%s", getattr(sess, "session_id", None))
            if self._menu_bar is not None:
                label = operational_label(pm, self._last_client_monotonic)
                device_name: str | None = None
                if pr is not None:
                    device_name = pr.mobile_display_name if pr.mobile_display_name else pr.mobile_device_id[:8]
                self._menu_bar.update_status(label, device_name, self._lan_ip)
            return
        if ok and reason == "rejected":
            with self._lock:
                self._last_pending_code = None
                self._last_pending_sid = None
            _emit(_box("Pairing — rejected by host", [f"session_id={getattr(sess, 'session_id', '?')}"]))
            _LOG.info("pairing UX rejected session_id=%s", getattr(sess, "session_id", None))
            return
        _emit(_box("Pairing — host respond finished", [f"ok={ok}", f"reason={reason}"]))

    def on_host_respond_failed(self, reason: str) -> None:
        _emit(_box("Pairing — host respond failed", [f"reason={reason}"]))
        _LOG.warning("pairing UX host_respond_failed reason=%s", reason)

    def on_session_cancelled_remote(self, session_id: str) -> None:
        close_active_qr_popup()
        with self._lock:
            if self._last_pending_sid == session_id:
                self._last_pending_code = None
                self._last_pending_sid = None
        _emit(_box("Pairing — cancelled from phone", [f"session_id={session_id}"]))
        _LOG.info("pairing UX cancelled session_id=%s", session_id)

    def on_unpair(self) -> None:
        close_active_qr_popup()
        with self._lock:
            self._last_pending_code = None
            self._last_pending_sid = None
        _emit(_box("Link — forgotten on this Mac", ["paired_device.json removed; POST /action no longer requires token."]))
        _LOG.info("pairing UX unpair")
        if self._menu_bar is not None:
            self._menu_bar.update_status("idle", None, self._lan_ip)

    def print_status(self, pm: PairingManager) -> None:
        with self._lock:
            lan = self._lan_ip
            port = self._http_port
            code = self._last_pending_code
            sid = self._last_pending_sid
            exp = self._last_pending_expires_ms
            name = self._last_pending_name
            last_m = self._last_client_monotonic
        pr = pm.paired_record()
        st = pm.agent_pairing_state()
        label = operational_label(pm, last_m)
        now_ms = int(time.time() * 1000)
        pending_line = "—"
        if code and sid:
            left = max(0, (exp - now_ms) // 1000)
            pending_line = f"code={code} session={sid[:16]}… TTL ~{left // 60}m {left % 60}s  ({name})"
        paired_line = "—"
        if pr:
            paired_line = f"{pr.mobile_display_name!r}  id={pr.mobile_device_id[:16]}…  token={pr.pair_token[:16]}…"
        lines = [
            f"UX state     : {label}",
            f"Agent state  : {st}",
            f"LAN IP (hint): {lan}",
            f"HTTP port    : {port}",
            f"Pending      : {pending_line}",
            f"Paired       : {paired_line}",
            "",
            "Endpoints: GET /health | POST /v1/pairing/… | POST /action",
        ]
        _emit(_box("Status", lines))

    def reprint_pairing_block(self, pm: PairingManager) -> None:
        with self._lock:
            sid = self._last_pending_sid
            code = self._last_pending_code
        if not sid or not code:
            _emit(_box("Pairing — nothing pending", ["No active pairing code in this console session. Start pairing from the phone."]))
            return
        s = pm.get_session(sid)
        if s is None:
            _emit(_box("Pairing — session gone", [f"session_id={sid} (expired, superseded, or purged)."]))
            with self._lock:
                self._last_pending_code = None
                self._last_pending_sid = None
            return
        self.on_pairing_session_created(pm, s)

    def menu_approve(self, pm: PairingManager) -> None:
        with self._lock:
            code = self._last_pending_code
            sid = self._last_pending_sid
        if not code and not sid:
            _emit("(menu) No pending pairing remembered. Use curl from the phone's block, or start pairing from the app.")
            return
        ok, reason, sess = pm.host_respond(approve=True, pairing_code=code, session_id=sid)
        if ok:
            self.on_host_respond_result(pm, ok, reason, sess)
        else:
            _emit(_box("Pairing — approve failed", [f"reason={reason}"]))
            _LOG.warning("menu approve failed: %s", reason)

    def menu_reject(self, pm: PairingManager) -> None:
        with self._lock:
            code = self._last_pending_code
            sid = self._last_pending_sid
        if not code and not sid:
            _emit("(menu) No pending pairing to reject.")
            return
        ok, reason, sess = pm.host_respond(approve=False, pairing_code=code, session_id=sid)
        if ok:
            self.on_host_respond_result(pm, ok, reason, sess)
        else:
            _emit(_box("Pairing — reject failed", [f"reason={reason}"]))
            _LOG.warning("menu reject failed: %s", reason)

    def menu_unpair(self, pm: PairingManager) -> None:
        close_active_qr_popup()
        pm.unpair()
        self.on_unpair()

    def menu_mac_bridge_pairing(self, pm: PairingManager) -> None:
        """
        MAC_BRIDGE direct pairing (macOS only).
        Generates a pair token, persists it, then shows a QR that Android scans to connect
        without any LAN HTTP round-trip. Works behind GlobalProtect / corporate VPN.
        """
        from pairing_qr_popup import launch_mac_bridge_qr_window

        token = pm.persist_bridge_token()
        deeplink = build_mac_bridge_deeplink(token)
        with self._lock:
            self._last_pending_code = None
            self._last_pending_sid = None
        self._write_deeplink_file(deeplink)
        _emit(
            _box(
                "Pairing — MAC Bridge (direct token)",
                [
                    "Scan this QR from DeckBridge on Android.",
                    "Phone connects automatically — no LAN required.",
                    f"Token: {token[:20]}…",
                    f"Deeplink: {deeplink}",
                ],
            )
        )
        _LOG.info("mac_bridge pairing token generated prefix=%s… deeplink_len=%s", token[:16], len(deeplink))
        printed = print_pairing_qr_to_stdout(deeplink)
        if not printed:
            _LOG.warning("console QR not printed (install qrcode package)")
        launch_mac_bridge_qr_window(deeplink=deeplink, token_prefix=token[:20])

    def menu_set_android_ip(self, ip: str) -> None:
        """Persist Android WiFi IP so the bridge client reconnects without Tailscale."""
        from mac_bridge_client import write_bridge_config, BRIDGE_PORT
        ip = ip.strip()
        if not ip:
            _emit("(menu) Usage:  i <ip>   e.g.  i 192.168.1.31")
            return
        write_bridge_config(ip, BRIDGE_PORT)
        _emit(_box("Android IP saved", [
            f"android_ip={ip}  port={BRIDGE_PORT}",
            "Bridge client will try this IP on the next reconnect cycle.",
            "Tip: see the Android IP in DeckBridge → Settings → Mac section.",
        ]))
        _LOG.info("menu_set_android_ip: saved ip=%s port=%d", ip, BRIDGE_PORT)

    def menu_host_qr_pairing(self, pm: PairingManager) -> None:
        """
        Show pairing QR. On macOS uses MAC_BRIDGE direct token flow (works behind VPN).
        On Windows falls back to the traditional LAN HTTP session flow.
        """
        if sys.platform == "darwin":
            self.menu_mac_bridge_pairing(pm)
            return
        # Windows: LAN HTTP session flow
        port = self._http_port
        label = (socket.gethostname() or "PC").strip() or "PC"
        data = json.dumps({"host_label": label}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/pairing/host/qr-sessions",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            _LOG.info("menu_host_qr_pairing POST ok bytes=%s", len(body))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:300]
            _emit(_box("QR pairing — HTTP error", [f"code={e.code}", err]))
            _LOG.warning("menu_host_qr_pairing HTTPError %s: %s", e.code, err)
        except Exception as e:
            _emit(_box("QR pairing — failed to start", [repr(e), "", "Is the agent HTTP server running on this port?"]))
            _LOG.exception("menu_host_qr_pairing failed")

    def menu_deeplink(self) -> None:
        with self._lock:
            sid = self._last_pending_sid
        uri = build_deeplink(self._lan_ip, self._http_port, sid, None)
        _emit(_box("QR / deep link", [uri, "", f"Also: {self._state_dir / 'last_pairing_deeplink.txt'}"]))
        self._write_deeplink_file(uri)

    def _write_deeplink_file(self, uri: str) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            p = self._state_dir / "last_pairing_deeplink.txt"
            p.write_text(uri + "\n", encoding="utf-8")
        except OSError as e:
            _LOG.warning("could not write deeplink file: %s", e)

    def record_action(self, action_type: str, detail: str, ok: bool) -> None:
        """Called by server.py after each /action execution."""
        import time as _time
        entry = {
            "time": _time.strftime("%H:%M:%S"),
            "type": action_type,
            "detail": detail,
            "ok": ok,
        }
        with self._recent_actions_lock:
            self._recent_actions.insert(0, entry)
            if len(self._recent_actions) > 10:
                self._recent_actions.pop()

    def get_recent_actions(self) -> list:
        with self._recent_actions_lock:
            return list(self._recent_actions)

    def stdin_loop(self, pm: PairingManager, httpd: Any = None) -> None:
        if os.environ.get("DECKBRIDGE_NO_CONSOLE_MENU", "").strip() == "1":
            _LOG.info("console menu disabled (DECKBRIDGE_NO_CONSOLE_MENU=1)")
            return
        _emit("\n(menu) Ready. Type  h  for help.\n")
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                break
            if not line:
                break
            cmd = line.strip()
            cmd_lower = cmd.lower()
            if cmd_lower in ("h", "?", "help"):
                _emit(
                    "\n".join(
                        [
                            _rule("·"),
                            "  h  help     |  s  status   |  p  re-print pairing block",
                            "  z  host QR   |  a  approve   |  r  reject    |  u  unpair (forget link)",
                            "  d  deeplink  |  q  quit agent (HTTP shutdown)",
                            "  i <ip>  set Android WiFi IP (e.g.  i 192.168.1.31)",
                            _rule("·"),
                        ]
                    )
                )
            elif cmd_lower in ("s", "status"):
                self.print_status(pm)
            elif cmd_lower == "p":
                self.reprint_pairing_block(pm)
            elif cmd_lower in ("z", "qr", "qrcode"):
                self.menu_host_qr_pairing(pm)
            elif cmd_lower == "a":
                self.menu_approve(pm)
            elif cmd_lower == "r":
                self.menu_reject(pm)
            elif cmd_lower == "u":
                self.menu_unpair(pm)
            elif cmd_lower == "d":
                self.menu_deeplink()
            elif cmd_lower == "q":
                _emit("(menu) Shutting down HTTP server…")
                _LOG.info("operator requested quit from console menu")
                if httpd is not None:
                    httpd.shutdown()
                break
            elif cmd_lower.startswith("i "):
                self.menu_set_android_ip(cmd[2:].strip())
            elif cmd_lower == "":
                continue
            else:
                _emit(f"(menu) Unknown command: {cmd!r}  (try  h )")


def _emit(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def configure_logging() -> None:
    """Structured logs: less noise than per-request stderr spam.

    Never raises: a bad env or logging edge case must not prevent the HTTP agent from starting.
    """
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    datefmt = "%H:%M:%S"

    def _apply(level: int) -> None:
        logging.basicConfig(
            level=level,
            format=fmt,
            datefmt=datefmt,
            stream=sys.stderr,
            force=True,
        )
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    try:
        debug = os.environ.get("DECKBRIDGE_DEBUG", "")
        level = logging.DEBUG if str(debug).strip() == "1" else logging.INFO
        _apply(level)
    except Exception as e:
        sys.stderr.write(
            f"[deckbridge] configure_logging failed ({e!r}); falling back to INFO on stderr.\n",
        )
        try:
            _apply(logging.INFO)
        except Exception as e2:
            sys.stderr.write(f"[deckbridge] logging fallback also failed ({e2!r}).\n")
