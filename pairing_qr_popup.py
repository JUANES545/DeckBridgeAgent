"""
Minimal Tkinter window: live QR + pairing code + session status for PC-initiated invite.

Runs the UI loop in a daemon thread so the HTTP server is not blocked.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from pairing_manager import PairingManager, PairingSession

_LOG = logging.getLogger("deckbridge.qr_popup")

_lock = threading.Lock()
_global_close: Callable[[], None] | None = None


def close_active_qr_popup() -> None:
    """Close the last QR window if still open (host approved elsewhere, HTTP cancel, new QR)."""
    global _global_close
    with _lock:
        fn = _global_close
        _global_close = None
    if fn is not None:
        try:
            fn()
        except Exception as e:
            _LOG.debug("close_active_qr_popup: %s", e)


def launch_mac_bridge_qr_window(*, deeplink: str, token_prefix: str) -> None:
    """
    Simple non-polling QR popup for MAC_BRIDGE direct pairing.
    No session lifecycle needed — just show the QR and close when done.
    """
    close_active_qr_popup()

    def _run() -> None:
        global _global_close
        try:
            import tkinter as tk
        except Exception as e:
            _LOG.error("tkinter unavailable (%s); cannot show QR window", e)
            return
        try:
            import qrcode
            from PIL import Image, ImageTk
        except Exception as e:
            _LOG.error("qrcode/Pillow missing (%s). pip install qrcode[pil] pillow", e)
            return

        root = tk.Tk()
        root.title("DeckBridge — MAC Bridge pairing QR")
        root.attributes("-topmost", True)
        root.configure(bg="#121218")

        photo_holder: list[object] = []

        def destroy_ui() -> None:
            global _global_close
            _LOG.info("MAC Bridge QR popup closing")
            with _lock:
                if _global_close == destroy_ui:
                    _global_close = None

            def _do_destroy() -> None:
                try:
                    root.destroy()
                except Exception:
                    pass

            try:
                root.after(0, _do_destroy)
            except Exception:
                _do_destroy()

        with _lock:
            _global_close = destroy_ui  # type: ignore[misc]

        _LOG.info("MAC Bridge QR popup opened token_prefix=%s…", token_prefix[:8])

        def make_photo() -> object:
            qr = qrcode.QRCode(version=None, box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(deeplink)
            qr.make(fit=True)
            pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            pil = pil.resize((340, 340), Image.Resampling.NEAREST)
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            buf.seek(0)
            return ImageTk.PhotoImage(data=buf.getvalue())

        outer = tk.Frame(root, bg="#121218", padx=14, pady=14)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="Scan with DeckBridge (Android)",
            fg="#eaeaf0",
            bg="#121218",
            font=("Helvetica Neue", 14, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            outer,
            text="MAC Bridge — works behind GlobalProtect / corporate VPN",
            fg="#9b9bb0",
            bg="#121218",
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(0, 10))

        try:
            ph = make_photo()
            photo_holder.append(ph)
            tk.Label(outer, image=ph, bg="#121218").pack(pady=6)
        except Exception as e:
            _LOG.warning("QR image build failed: %s", e)
            tk.Label(outer, text="(QR render failed — see logs)", fg="#f2a4a4", bg="#121218").pack()

        tk.Label(
            outer,
            text="Phone connects automatically after scanning. Close this window when done.",
            fg="#c8c8d8",
            bg="#121218",
            font=("Helvetica Neue", 11),
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(14, 6))

        tk.Button(
            outer,
            text="Close",
            command=destroy_ui,
            bg="#2a2a36",
            fg="#eaeaf0",
            activebackground="#3d3d4d",
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(16, 0))

        root.protocol("WM_DELETE_WINDOW", destroy_ui)
        try:
            root.mainloop()
        finally:
            _LOG.info("MAC Bridge QR popup mainloop ended")
            destroy_ui()

    threading.Thread(target=_run, name="deckbridge-mac-bridge-qr-popup", daemon=True).start()


def launch_pairing_qr_window(
    *,
    pairing_manager: PairingManager,
    session: PairingSession,
    deeplink: str,
    http_port: int,
    host_label: str,
) -> None:
    close_active_qr_popup()

    def _run() -> None:
        global _global_close
        try:
            import tkinter as tk
        except Exception as e:
            _LOG.error("tkinter unavailable (%s); cannot show QR window", e)
            return
        try:
            import qrcode
            from PIL import Image, ImageTk
        except Exception as e:
            _LOG.error("qrcode/Pillow missing (%s). pip install qrcode[pil] pillow", e)
            return

        root = tk.Tk()
        root.title("DeckBridge — Mac pairing QR")
        root.attributes("-topmost", True)
        root.configure(bg="#121218")

        photo_holder: list[object] = []

        def destroy_ui() -> None:
            global _global_close
            _LOG.info("QR popup closing session_id=%s", session.session_id)
            with _lock:
                if _global_close == destroy_ui:
                    _global_close = None

            def _do_destroy() -> None:
                try:
                    root.destroy()
                except Exception:
                    pass

            try:
                # Safe if called from a non-UI thread (e.g. HTTP handler closing the popup).
                root.after(0, _do_destroy)
            except Exception:
                _do_destroy()

        with _lock:
            _global_close = destroy_ui  # type: ignore[misc]

        _LOG.info(
            "QR popup opened session_id=%s code=%s port=%s host_label=%r deeplink_len=%s",
            session.session_id,
            session.pairing_code,
            http_port,
            host_label,
            len(deeplink),
        )

        def make_photo() -> object:
            qr = qrcode.QRCode(version=None, box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(deeplink)
            qr.make(fit=True)
            pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            pil = pil.resize((340, 340), Image.Resampling.NEAREST)
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            buf.seek(0)
            return ImageTk.PhotoImage(data=buf.getvalue())

        outer = tk.Frame(root, bg="#121218", padx=14, pady=14)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="Scan with DeckBridge (Android)",
            fg="#eaeaf0",
            bg="#121218",
            font=("Helvetica Neue", 14, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            outer,
            text=f"{host_label}  ·  LAN port {http_port}",
            fg="#9b9bb0",
            bg="#121218",
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(0, 10))

        try:
            ph = make_photo()
            photo_holder.append(ph)
            tk.Label(outer, image=ph, bg="#121218").pack(pady=6)
        except Exception as e:
            _LOG.warning("QR image build failed: %s", e)
            tk.Label(outer, text="(QR render failed — see logs)", fg="#f2a4a4", bg="#121218").pack()

        tk.Label(
            outer,
            text=f"Code:  {session.pairing_code}",
            fg="#7ecbff",
            bg="#121218",
            font=("Consolas", 20, "bold"),
        ).pack(pady=(8, 4))

        tk.Label(
            outer,
            text=f"Session: {session.session_id}",
            fg="#7a7a8c",
            bg="#121218",
            font=("Consolas", 9),
        ).pack()

        status_var = tk.StringVar(value="Waiting for phone to scan…")
        tk.Label(
            outer,
            textvariable=status_var,
            fg="#c8c8d8",
            bg="#121218",
            font=("Helvetica Neue", 11),
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(14, 6))

        tk.Label(
            outer,
            text="Approve on this Mac: type  a  in the agent Terminal, or use curl from the logs.",
            fg="#6c6c7a",
            bg="#121218",
            font=("Helvetica Neue", 9),
            wraplength=440,
            justify="left",
        ).pack(anchor="w")

        def on_cancel() -> None:
            ok, reason = pairing_manager.cancel_host_qr_invite(session.session_id)
            _LOG.info("QR popup cancel clicked session_id=%s ok=%s reason=%s", session.session_id, ok, reason)
            destroy_ui()

        tk.Button(
            outer,
            text="Cancel invite",
            command=on_cancel,
            bg="#2a2a36",
            fg="#eaeaf0",
            activebackground="#3d3d4d",
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(16, 0))

        def poll() -> None:
            try:
                if not root.winfo_exists():
                    return
            except tk.TclError:
                return
            s = pairing_manager.get_session(session.session_id)
            now = int(time.time() * 1000)
            if s is None:
                status_var.set("Session ended (expired, cancelled, or completed).")
                root.after(2500, destroy_ui)
                return
            if s.status == "pending_approval":
                from pairing_manager import QR_INVITE_DEVICE_ID

                left = max(0, (s.expires_ms - now) // 1000)
                ttl = f"{left // 60}m {left % 60}s"
                if s.mobile_device_id == QR_INVITE_DEVICE_ID:
                    status_var.set(f"Waiting for phone scan…  (TTL {ttl})")
                else:
                    status_var.set(
                        f"Phone linked — approve on this PC (console: a).  Code: {s.pairing_code}  TTL {ttl}",
                    )
            elif s.status == "consumed":
                status_var.set("Paired successfully.")
                _LOG.info("QR popup session consumed session_id=%s — closing", session.session_id)
                root.after(1200, destroy_ui)
                return
            elif s.status in ("rejected", "cancelled", "expired", "superseded"):
                status_var.set(f"Session {s.status}.")
                _LOG.info("QR popup terminal status=%s session_id=%s", s.status, session.session_id)
                root.after(2200, destroy_ui)
                return
            else:
                status_var.set(f"Status: {s.status}")
            root.after(1200, poll)

        root.protocol("WM_DELETE_WINDOW", on_cancel)
        root.after(400, poll)
        try:
            root.mainloop()
        finally:
            _LOG.info("QR popup mainloop ended session_id=%s", session.session_id)
            destroy_ui()

    threading.Thread(target=_run, name="deckbridge-qr-popup", daemon=True).start()
