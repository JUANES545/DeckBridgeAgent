"""
DeckBridge LAN pairing: in-memory sessions + JSON persistence of the paired phone.

Thread-safe for ThreadingHTTPServer. Session lifecycle is explicit; terminal sessions are
purged from memory after a short retention window so retries and logs stay sane.
"""

from __future__ import annotations

import json
import logging
import secrets
import string
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal

_log = logging.getLogger("deckbridge.pairing")

CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")

# Placeholder until the phone scans the QR and POSTs /v1/pairing/sessions/{id}/claim (must match Android).
QR_INVITE_DEVICE_ID = "__deckbridge_qr_invite__"

# pending_approval: phone is waiting for host curl approve/reject.
# consumed: host approved; pair_token returned here until session row is purged; disk has paired_device.json.
# superseded: same phone started a newer session, or another session won approval and this pending was voided.
PairingStatus = Literal[
    "pending_approval",
    "consumed",
    "rejected",
    "cancelled",
    "expired",
    "superseded",
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _random_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _new_session_id() -> str:
    return "ps_" + secrets.token_hex(10)


def _new_pair_token() -> str:
    return "pt_" + secrets.token_urlsafe(32).rstrip("=")


@dataclass
class PairingSession:
    session_id: str
    pairing_code: str
    mobile_device_id: str
    mobile_display_name: str
    created_ms: int
    expires_ms: int
    status: PairingStatus
    pair_token: str | None = None
    """When status became consumed (host approved); used for retention."""
    consumed_at_ms: int | None = None
    """When session reached any terminal state; used to purge from RAM."""
    terminal_at_ms: int | None = None

    def to_public_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ok": True,
            "session_id": self.session_id,
            "status": self.status,
            "pairing_code": self.pairing_code,
            "expires_at_ms": self.expires_ms,
            "mobile_device_id": self.mobile_device_id,
            "created_at_ms": self.created_ms,
        }
        if self.status == "consumed" and self.pair_token:
            d["pair_token"] = self.pair_token
        return d


@dataclass
class PairedDeviceRecord:
    mobile_device_id: str
    pair_token: str
    mobile_display_name: str
    paired_at_ms: int

    def to_json(self) -> dict[str, Any]:
        return {
            "mobile_device_id": self.mobile_device_id,
            "pair_token": self.pair_token,
            "mobile_display_name": self.mobile_display_name,
            "paired_at_ms": self.paired_at_ms,
        }

    @staticmethod
    def from_json(data: dict[str, Any]) -> PairedDeviceRecord | None:
        try:
            return PairedDeviceRecord(
                mobile_device_id=str(data["mobile_device_id"]),
                pair_token=str(data["pair_token"]),
                mobile_display_name=str(data.get("mobile_display_name", "")),
                paired_at_ms=int(data["paired_at_ms"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


class PairingManager:
    """
    - Pairing sessions are ephemeral (RAM). Successful approval writes paired_device.json.
    - POST /action requires X-DeckBridge-Pair-Token when a paired record exists.
    - Only one pending_approval per mobile_device_id (older ones -> superseded).
    - When host approves one session, other pending sessions are superseded (competing phones).
    """

    # Phone must complete approval within this window.
    DEFAULT_SESSION_TTL_MS = 900_000  # 15 minutes
    # GET /sessions/{id} keeps consumed rows briefly so the client can read pair_token idempotently.
    CONSUMED_RETENTION_MS = 900_000  # 15 minutes
    # Failed / void terminal rows removed after this delay.
    TERMINAL_FAIL_RETENTION_MS = 120_000  # 2 minutes

    def __init__(self, state_dir: Path, session_ttl_ms: int | None = None) -> None:
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._paired_path = self._state_dir / "paired_device.json"
        self._ttl_ms = int(session_ttl_ms) if session_ttl_ms is not None else self.DEFAULT_SESSION_TTL_MS
        self._lock = RLock()
        self._sessions: dict[str, PairingSession] = {}
        self._paired: PairedDeviceRecord | None = None
        self._load_paired_from_disk()

    def _load_paired_from_disk(self) -> None:
        if not self._paired_path.is_file():
            return
        try:
            raw = json.loads(self._paired_path.read_text(encoding="utf-8"))
            rec = PairedDeviceRecord.from_json(raw)
            if rec:
                self._paired = rec
                _log.info(
                    "persist loaded paired_device mobile_id=%r name=%r paired_at_ms=%s",
                    rec.mobile_device_id,
                    rec.mobile_display_name,
                    rec.paired_at_ms,
                )
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("persist could not load paired_device.json: %s", e)

    def _save_paired(self, rec: PairedDeviceRecord) -> None:
        tmp = self._paired_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec.to_json(), indent=2), encoding="utf-8")
        tmp.replace(self._paired_path)

    def paired_record(self) -> PairedDeviceRecord | None:
        with self._lock:
            return self._paired

    def verify_pair_token(self, token: str | None) -> bool:
        with self._lock:
            if self._paired is None:
                return True
            if not token:
                return False
            return secrets.compare_digest(token, self._paired.pair_token)

    def _mark_terminal(self, s: PairingSession, new_status: PairingStatus, log_line: str) -> None:
        now = _now_ms()
        s.status = new_status
        s.terminal_at_ms = now
        _log.info("%s", log_line)

    def _purge_sessions_locked(self) -> None:
        """Drop expired pendings, then remove old terminal rows from RAM."""
        now = _now_ms()
        for sid, s in list(self._sessions.items()):
            if s.status == "pending_approval" and now > s.expires_ms:
                self._mark_terminal(
                    s,
                    "expired",
                    f"[pairing] lifecycle expired session_id={sid} mobile_id={s.mobile_device_id!r}",
                )
        to_delete: list[str] = []
        for sid, s in list(self._sessions.items()):
            t = s.terminal_at_ms
            if t is None:
                continue
            age = now - t
            if s.status == "consumed" and age > self.CONSUMED_RETENTION_MS:
                to_delete.append(sid)
            elif s.status != "consumed" and s.status != "pending_approval" and age > self.TERMINAL_FAIL_RETENTION_MS:
                to_delete.append(sid)
        for sid in to_delete:
            del self._sessions[sid]
            _log.info("purged session from memory session_id=%s", sid)

    def create_session(self, mobile_device_id: str, mobile_display_name: str) -> PairingSession:
        mid = mobile_device_id.strip()
        name = (mobile_display_name or "Android")[:120]
        with self._lock:
            self._purge_sessions_locked()
            # A real phone starting pairing voids an open PC QR invite (same operator flow).
            if mid != QR_INVITE_DEVICE_ID:
                for sid, s in list(self._sessions.items()):
                    if s.status == "pending_approval" and s.mobile_device_id == QR_INVITE_DEVICE_ID:
                        self._mark_terminal(
                            s,
                            "superseded",
                            f"[pairing] lifecycle superseded session_id={sid} reason=phone_started_pairing",
                        )
            # Same phone: only the latest session stays pending; older pendings -> superseded.
            for sid, s in list(self._sessions.items()):
                if s.status == "pending_approval" and s.mobile_device_id == mid:
                    self._mark_terminal(
                        s,
                        "superseded",
                        f"[pairing] lifecycle superseded session_id={sid} reason=newer_session_same_device",
                    )
            sid = _new_session_id()
            code = _random_code()
            now = _now_ms()
            sess = PairingSession(
                session_id=sid,
                pairing_code=code,
                mobile_device_id=mid,
                mobile_display_name=name,
                created_ms=now,
                expires_ms=now + self._ttl_ms,
                status="pending_approval",
            )
            self._sessions[sid] = sess
            _log.info(
                "session created session_id=%s status=pending_approval code=%s ttl_ms=%s mobile_id=%r display_name=%r",
                sid,
                code,
                self._ttl_ms,
                mid,
                name,
            )
            return sess

    def create_host_qr_session(self, host_display_name: str) -> PairingSession:
        """PC-initiated invite: placeholder device id until the phone calls [claim_session]."""
        label = (host_display_name or "PC").strip()[:120] or "PC"
        with self._lock:
            self._purge_sessions_locked()
            for sid, s in list(self._sessions.items()):
                if s.status == "pending_approval" and s.mobile_device_id == QR_INVITE_DEVICE_ID:
                    self._mark_terminal(
                        s,
                        "superseded",
                        f"[pairing] lifecycle superseded session_id={sid} reason=newer_host_qr_session",
                    )
            sid = _new_session_id()
            code = _random_code()
            now = _now_ms()
            sess = PairingSession(
                session_id=sid,
                pairing_code=code,
                mobile_device_id=QR_INVITE_DEVICE_ID,
                mobile_display_name=label,
                created_ms=now,
                expires_ms=now + self._ttl_ms,
                status="pending_approval",
            )
            self._sessions[sid] = sess
            _log.info(
                "host QR invite created session_id=%s code=%s ttl_ms=%s host_label=%r (awaiting phone scan + claim)",
                sid,
                code,
                self._ttl_ms,
                label,
            )
            return sess

    def claim_session(self, session_id: str, mobile_device_id: str, mobile_display_name: str) -> tuple[bool, str]:
        mid = mobile_device_id.strip()
        name = (mobile_display_name or "Android")[:120]
        if not mid:
            return False, "mobile_device_id_required"
        with self._lock:
            self._purge_sessions_locked()
            s = self._sessions.get(session_id.strip())
            if s is None:
                _log.warning("claim rejected session_id=%s reason=session_not_found", session_id)
                return False, "session_not_found"
            if s.status != "pending_approval":
                _log.warning(
                    "claim rejected session_id=%s reason=invalid_status status=%s",
                    session_id,
                    s.status,
                )
                return False, f"invalid_status:{s.status}"
            if _now_ms() > s.expires_ms:
                self._mark_terminal(
                    s,
                    "expired",
                    f"[pairing] lifecycle expired session_id={session_id} (on claim)",
                )
                _log.warning("claim rejected session_id=%s reason=expired", session_id)
                return False, "expired"
            if s.mobile_device_id == QR_INVITE_DEVICE_ID:
                s.mobile_device_id = mid
                s.mobile_display_name = name
                _log.info(
                    "session claimed session_id=%s mobile_id=%r display_name=%r",
                    session_id,
                    mid[:24],
                    name,
                )
                return True, "ok"
            if secrets.compare_digest(s.mobile_device_id, mid):
                return True, "ok"
            _log.warning(
                "claim rejected session_id=%s reason=device_mismatch session_owner_prefix=%r",
                session_id,
                (s.mobile_device_id or "")[:16],
            )
            return False, "device_mismatch"

    def cancel_host_qr_invite(self, session_id: str) -> tuple[bool, str]:
        with self._lock:
            self._purge_sessions_locked()
            s = self._sessions.get(session_id.strip())
            if s is None:
                return False, "session_not_found"
            if s.mobile_device_id != QR_INVITE_DEVICE_ID:
                return False, "not_host_qr_invite"
            if s.status != "pending_approval":
                return False, "not_pending"
            self._mark_terminal(
                s,
                "cancelled",
                f"[pairing] host QR invite cancelled session_id={session_id}",
            )
            return True, "ok"

    def get_session(self, session_id: str) -> PairingSession | None:
        with self._lock:
            self._purge_sessions_locked()
            s = self._sessions.get(session_id)
            if s is None:
                return None
            if s.status == "pending_approval" and _now_ms() > s.expires_ms:
                self._mark_terminal(
                    s,
                    "expired",
                    f"[pairing] lifecycle expired session_id={session_id} (lazy on GET)",
                )
            return s

    def cancel_session(self, session_id: str, mobile_device_id: str) -> tuple[bool, str]:
        with self._lock:
            self._purge_sessions_locked()
            s = self._sessions.get(session_id)
            if s is None:
                return False, "session_not_found"
            if s.mobile_device_id != mobile_device_id.strip():
                return False, "device_mismatch"
            if s.status != "pending_approval":
                return False, "not_pending"
            self._mark_terminal(
                s,
                "cancelled",
                f"[pairing] lifecycle cancelled session_id={session_id} mobile_id={s.mobile_device_id!r}",
            )
            return True, "ok"

    def host_respond(
        self,
        *,
        approve: bool,
        pairing_code: str | None = None,
        session_id: str | None = None,
    ) -> tuple[bool, str, PairingSession | None]:
        with self._lock:
            self._purge_sessions_locked()
            s: PairingSession | None = None
            if session_id:
                s = self._sessions.get(session_id.strip())
            if s is None and pairing_code:
                code = pairing_code.strip().upper()
                for cand in self._sessions.values():
                    if cand.pairing_code == code and cand.status == "pending_approval":
                        s = cand
                        break
            if s is None:
                _log.warning("host_respond miss session_id/code not found or purged")
                return False, "session_not_found", None
            if s.status != "pending_approval":
                _log.warning(
                    "host_respond invalid_status session_id=%s status=%s",
                    s.session_id,
                    s.status,
                )
                return False, f"invalid_status:{s.status}", s
            if _now_ms() > s.expires_ms:
                self._mark_terminal(
                    s,
                    "expired",
                    f"[pairing] lifecycle expired session_id={s.session_id} (on host_respond)",
                )
                return False, "expired", s
            if not approve:
                self._mark_terminal(
                    s,
                    "rejected",
                    f"[pairing] lifecycle rejected session_id={s.session_id} mobile_id={s.mobile_device_id!r}",
                )
                return True, "rejected", s
            now = _now_ms()
            token = _new_pair_token()
            # Void every other pending session (competing phones or stray flows).
            for sid, other in list(self._sessions.items()):
                if other.session_id == s.session_id:
                    continue
                if other.status == "pending_approval":
                    self._mark_terminal(
                        other,
                        "superseded",
                        f"[pairing] lifecycle superseded session_id={sid} "
                        f"reason=another_session_approved winner={s.session_id}",
                    )
            s.pair_token = token
            s.status = "consumed"
            s.consumed_at_ms = now
            s.terminal_at_ms = now
            rec = PairedDeviceRecord(
                mobile_device_id=s.mobile_device_id,
                pair_token=token,
                mobile_display_name=s.mobile_display_name,
                paired_at_ms=now,
            )
            self._paired = rec
            self._save_paired(rec)
            _log.info(
                "lifecycle consumed session_id=%s mobile_id=%r pair_token_prefix=%s… persist=paired_device.json",
                s.session_id,
                s.mobile_device_id,
                token[:16],
            )
            return True, "consumed", s

    def persist_bridge_token(self) -> str:
        """
        MAC_BRIDGE direct pairing: generate a new pair token and persist it immediately.
        No pairing session needed — the token is embedded in the QR and Android calls
        applyMacBridgeToken() directly, skipping the LAN HTTP round-trip entirely.
        """
        token = _new_pair_token()
        rec = PairedDeviceRecord(
            mobile_device_id="mac_bridge_direct",
            pair_token=token,
            mobile_display_name="",
            paired_at_ms=_now_ms(),
        )
        with self._lock:
            self._paired = rec
            self._save_paired(rec)
        _log.info(
            "MAC_BRIDGE direct token persisted pair_token_prefix=%s…",
            token[:16],
        )
        return token

    def unpair(self) -> None:
        with self._lock:
            self._paired = None
            try:
                if self._paired_path.is_file():
                    self._paired_path.unlink()
            except OSError as e:
                _log.warning("unpair unlink failed: %s", e)
            _log.info("persist cleared host unpaired — /action no longer requires token")

    def agent_pairing_state(self) -> str:
        with self._lock:
            pending = [x for x in self._sessions.values() if x.status == "pending_approval"]
            if self._paired:
                if pending:
                    return "paired_with_pending"
                return "paired"
            if pending:
                return "waiting_for_confirmation"
            return "idle"
