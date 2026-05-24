"""
Manages the DeckBridge main window (pywebview).

Pattern: rumps owns the main thread. pywebview.start() runs in a
daemon thread, created on-demand when the user clicks "Abrir DeckBridge...".
Closing the window terminates the thread; the next click creates a new one.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if sys.platform != "darwin":
    raise ImportError("macos_window is macOS-only")

if TYPE_CHECKING:
    from agent_ux import AgentUx
    from pairing_manager import PairingManager


def _html_path() -> str:
    """Resolve ui/index.html — works from source and PyInstaller bundle."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass) / "ui" / "index.html"
    else:
        p = Path(__file__).resolve().parent / "ui" / "index.html"
    return str(p)


class DeckBridgeApi:
    """Python methods exposed to the JS frontend via pywebview bridge."""

    def __init__(self, udp_ok_fn: Callable[[], bool] | None = None) -> None:
        self._ux_ref: "AgentUx | None" = None
        self._pm_ref: "PairingManager | None" = None
        self._win_ref = None  # webview.Window, set after window created
        self._udp_ok_fn = udp_ok_fn  # callable -> bool

    def set_ux(self, ux: "AgentUx", pm: "PairingManager") -> None:
        self._ux_ref = ux
        self._pm_ref = pm

    def set_window(self, win) -> None:
        self._win_ref = win

    # ------------------------------------------------------------------
    # Bridge API — called from JavaScript
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        ux = self._ux_ref
        pm = self._pm_ref
        if ux is None or pm is None:
            return {
                "state": "idle",
                "device_name": None,
                "lan_ip": "—",
                "port": 8765,
                "last_action_ago": None,
                "last_actions": [],
                "version": _read_version(),
                "accessibility_ok": True,
                "udp_ok": False,
            }

        # State
        from agent_ux import operational_label
        state = operational_label(pm, ux._last_client_monotonic)

        # Device name
        device_name: str | None = None
        try:
            pr = pm.paired_record()
            if pr is not None:
                device_name = pr.mobile_display_name or pr.mobile_device_id[:8]
        except Exception:
            pass

        # LAN IP (thread-safe read via attribute — AgentUx stores it as _lan_ip)
        lan_ip = getattr(ux, "_lan_ip", "—") or "—"

        # Port
        port = getattr(ux, "_http_port", 8765)

        # Last action ago
        last_action_ago = _format_ago(ux._last_client_monotonic)

        # Recent actions
        last_actions = ux.get_recent_actions()

        # Version
        version = _read_version()

        # Accessibility
        accessibility_ok = True
        try:
            from macos_accessibility import accessibility_trusted
            result = accessibility_trusted()
            accessibility_ok = result is not False
        except Exception:
            pass

        # UDP
        udp_ok = True
        if self._udp_ok_fn is not None:
            try:
                udp_ok = bool(self._udp_ok_fn())
            except Exception:
                udp_ok = False

        return {
            "state": state,
            "device_name": device_name,
            "lan_ip": lan_ip,
            "port": port,
            "last_action_ago": last_action_ago,
            "last_actions": last_actions,
            "version": version,
            "accessibility_ok": accessibility_ok,
            "udp_ok": udp_ok,
        }

    def pair(self) -> None:
        ux = self._ux_ref
        pm = self._pm_ref
        if ux is None or pm is None:
            return
        threading.Thread(
            target=ux.menu_host_qr_pairing,
            args=(pm,),
            daemon=True,
            name="deckbridge-win-pair",
        ).start()

    def forget(self) -> None:
        ux = self._ux_ref
        pm = self._pm_ref
        if ux is None or pm is None:
            return
        threading.Thread(
            target=ux.menu_unpair,
            args=(pm,),
            daemon=True,
            name="deckbridge-win-forget",
        ).start()

    def copy_deeplink(self) -> None:
        ux = self._ux_ref
        pm = self._pm_ref
        if ux is None or pm is None:
            return
        try:
            from agent_ux import build_deeplink
            sid: str | None = None
            with ux._lock:
                sid = ux._last_pending_sid
            lan_ip = getattr(ux, "_lan_ip", "127.0.0.1") or "127.0.0.1"
            port = getattr(ux, "_http_port", 8765)
            deeplink = build_deeplink(lan_ip, port, sid, None)
            _copy_to_clipboard(deeplink)
        except Exception:
            pass

    def close_window(self) -> None:
        if self._win_ref is not None:
            try:
                self._win_ref.hide()
            except Exception:
                pass

    def open_accessibility_settings(self) -> None:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])


class DeckBridgeWindow:
    """Opens and manages the pywebview main window."""

    def __init__(self, api: DeckBridgeApi) -> None:
        self._api = api
        self._thread: threading.Thread | None = None

    def open_or_focus(self) -> None:
        """Called from the menu bar click (rumps main thread)."""
        if self._thread is not None and self._thread.is_alive():
            # Window already open — bring to front
            if self._api._win_ref is not None:
                try:
                    self._api._win_ref.show()
                except Exception:
                    pass
            return
        # Start a new window thread
        self._thread = threading.Thread(
            target=self._run_window,
            name="deckbridge-webview",
            daemon=True,
        )
        self._thread.start()

    def _run_window(self) -> None:
        try:
            import webview  # type: ignore[import]
        except ImportError:
            import sys as _sys
            _sys.stderr.write(
                "[deckbridge] pywebview not installed — cannot open window. "
                "Run: pip install pywebview\n"
            )
            return

        # Load HTML content directly — avoids file:// access restrictions in WKWebView
        # when running inside a PyInstaller .app bundle on macOS.
        html_file = _html_path()
        try:
            with open(html_file, encoding="utf-8") as f:
                html_content = f.read()
        except OSError as e:
            import sys as _sys
            _sys.stderr.write(f"[deckbridge] Cannot read UI file {html_file}: {e}\n")
            return

        win = webview.create_window(
            title="DeckBridge",
            html=html_content,
            width=420,
            height=630,
            resizable=False,
            frameless=False,
            js_api=self._api,
            background_color="#0f1117",
        )
        self._api.set_window(win)
        # webview.start() blocks until all windows are closed.
        # On macOS this runs a Cocoa event loop on this thread via GCD dispatch queues,
        # which is compatible with rumps owning the NSApplication main runloop.
        webview.start()
        # Window closed — clear the reference
        self._api.set_window(None)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _format_ago(monotonic: float | None) -> str | None:
    if monotonic is None:
        return None
    elapsed = time.monotonic() - monotonic
    if elapsed < 0:
        return "ahora"
    if elapsed < 60:
        return f"hace {int(elapsed)} s"
    if elapsed < 3600:
        return f"hace {int(elapsed // 60)} m"
    return f"hace {int(elapsed // 3600)} h"


def _read_version() -> str:
    """Read version from CHANGELOG.md first ## [...] heading, or return fallback."""
    try:
        changelog = Path(__file__).resolve().parent / "CHANGELOG.md"
        with changelog.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("## ["):
                    # e.g.  ## [1.3.0] - 2026-05-23
                    rest = line[4:]
                    end = rest.find("]")
                    if end > 0:
                        return rest[:end]
    except Exception:
        pass
    return "1.3.0"


def _copy_to_clipboard(text: str) -> None:
    """Copy text to macOS clipboard via pbcopy."""
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))
    except Exception:
        pass
