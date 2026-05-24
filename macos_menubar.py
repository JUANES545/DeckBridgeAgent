"""
macOS menu-bar icon and menu for DeckBridge.

Only imported on macOS — raises ImportError on other platforms so Windows code paths
are never accidentally affected.
"""

from __future__ import annotations

import sys

if sys.platform != "darwin":
    raise ImportError("macos_menubar is macOS-only")

import logging
import subprocess
from pathlib import Path
from typing import Callable

import rumps

_LOG = logging.getLogger("deckbridge.menubar")

def _menubar_icon_path() -> str | None:
    """Resolve the template icon path — works from source and PyInstaller bundle."""
    candidates = [
        Path(__file__).resolve().parent / "builds" / "mac" / "menubar_template.png",
        Path(__file__).resolve().parent / "menubar_template.png",  # PyInstaller onedir
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


class DeckBridgeMenuBar(rumps.App):
    """System-tray menu bar app for DeckBridge (macOS).

    Call `run()` on the main thread — rumps takes over the run loop.
    The icon appears immediately on startup; accessibility is checked
    in the background after the run loop starts.
    """

    def __init__(self) -> None:
        icon = _menubar_icon_path()
        super().__init__(
            "DeckBridge",
            icon=icon,
            template=True,   # macOS inverts automatically for light/dark menu bar
            quit_button=None,
        )
        if not icon:
            _LOG.warning("menubar_template.png not found — using text title fallback")

        # Menu item references kept for dynamic updates.
        self._item_header = rumps.MenuItem("DeckBridge")
        self._item_header.set_callback(None)

        self._item_status = rumps.MenuItem("Iniciando…")
        self._item_status.set_callback(None)

        self._item_ip = rumps.MenuItem("")
        self._item_ip.set_callback(None)

        # Accessibility warning — hidden until needed.
        self._item_accessibility = rumps.MenuItem(
            "⚠️  Permitir Accesibilidad…",
            callback=self._open_accessibility_settings,
        )

        self._item_open = rumps.MenuItem("Abrir DeckBridge…", callback=self.open_window_clicked)
        self._item_pair = rumps.MenuItem("Parear con Android…", callback=self.pair_clicked)
        self._item_forget = rumps.MenuItem("Olvidar dispositivo", callback=self.forget_clicked)
        self._item_quit = rumps.MenuItem("Salir de DeckBridge", callback=rumps.quit_application)

        self.menu = [
            self._item_header,
            self._item_status,
            self._item_ip,
            rumps.separator,
            self._item_open,
            rumps.separator,
            self._item_pair,
            self._item_forget,
            rumps.separator,
            self._item_quit,
        ]

        # Disabled (non-clickable) items must have their callback cleared after menu assembly
        # because rumps re-sets callbacks during menu construction.
        self._item_header.set_callback(None)
        self._item_status.set_callback(None)
        self._item_ip.set_callback(None)

        # Callbacks wired by the caller after construction.
        self._trigger_pairing: Callable[[], None] | None = None
        self._trigger_forget: Callable[[], None] | None = None
        self._accessibility_ok: bool = True
        self._window_manager = None
        # Native NSWindow reference (kept to prevent garbage collection)
        self._native_window = None
        self._native_webview = None

    # ------------------------------------------------------------------
    # Accessibility check (runs after the run loop starts)
    # ------------------------------------------------------------------

    @rumps.timer(5)
    def _check_accessibility(self, _sender) -> None:
        """Poll accessibility permission every 5 s and update the menu accordingly."""
        try:
            from macos_accessibility import accessibility_trusted
            trusted = accessibility_trusted()
        except Exception:
            return

        if trusted and not self._accessibility_ok:
            # Just got granted — remove the warning item
            self._accessibility_ok = True
            try:
                del self.menu["⚠️  Permitir Accesibilidad…"]
            except Exception:
                pass
            _LOG.info("Accessibility permission granted — warning removed from menu")

        elif not trusted and self._accessibility_ok:
            # Just lost / not yet granted — insert warning item at the top
            self._accessibility_ok = False
            self.menu.insert_before("DeckBridge", self._item_accessibility)
            _LOG.warning("Accessibility permission missing — warning shown in menu")

    def _open_accessibility_settings(self, _sender) -> None:
        """Open System Settings → Privacy & Security → Accessibility."""
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])

    # ------------------------------------------------------------------
    # Public API called by the rest of the agent
    # ------------------------------------------------------------------

    def set_ux_callbacks(
        self,
        trigger_pairing_fn: Callable[[], None],
        trigger_forget_fn: Callable[[], None],
    ) -> None:
        """Wire the pairing and forget callbacks after construction."""
        self._trigger_pairing = trigger_pairing_fn
        self._trigger_forget = trigger_forget_fn

    def set_window_manager(self, wm) -> None:
        self._window_manager = wm

    def update_status(self, state: str, device_name: str | None, lan_ip: str) -> None:
        """Update the two dynamic menu items (status line and IP line).

        state values: "connected" | "paired" | "waiting_for_pairing" | "idle" | "error"
        """
        state_labels = {
            "connected": f"🟢  {device_name}",
            "paired": f"🟡  {device_name} (pareado)",
            "waiting_for_pairing": "⏳  Esperando confirmación…",
            "idle": "⚫  Sin dispositivo pareado",
            "error": "🔴  Error de accesibilidad",
        }
        status_text = state_labels.get(state, f"⚫  {state}")
        self._item_status.title = status_text

        if lan_ip:
            self._item_ip.title = f"   {lan_ip}  ·  :8765"
        else:
            self._item_ip.title = ""

        _LOG.debug("menubar update_status state=%s device=%s ip=%s", state, device_name, lan_ip)

    # ------------------------------------------------------------------
    # Menu action handlers
    # ------------------------------------------------------------------

    def open_window_clicked(self, _sender: rumps.MenuItem) -> None:
        """Open a native NSWindow with WKWebView loading the companion UI.

        This callback runs on the main thread (rumps dispatches menu clicks there),
        so NSWindow and WKWebView can be created safely without any thread conflict.
        """
        # If already open, bring to front
        if self._native_window is not None:
            try:
                self._native_window.makeKeyAndOrderFront_(None)
                return
            except Exception:
                self._native_window = None

        try:
            from AppKit import (
                NSWindow, NSBackingStoreBuffered, NSMakeRect,
                NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                NSWindowStyleMaskMiniaturizable,
            )
            from WebKit import WKWebView, WKWebViewConfiguration
            from Foundation import NSURL, NSURLRequest

            frame = NSMakeRect(0, 0, 420, 630)
            style = (
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
            )
            win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame, style, NSBackingStoreBuffered, False
            )
            win.setTitle_("DeckBridge")
            win.setReleasedWhenClosed_(False)

            cfg = WKWebViewConfiguration.alloc().init()
            wv = WKWebView.alloc().initWithFrame_configuration_(frame, cfg)
            win.setContentView_(wv)

            url = NSURL.URLWithString_("http://localhost:8765/ui")
            wv.loadRequest_(NSURLRequest.requestWithURL_(url))

            win.center()
            win.makeKeyAndOrderFront_(None)

            # Keep strong references to prevent GC
            self._native_window = win
            self._native_webview = wv
            _LOG.info("native window opened")

        except Exception as e:
            _LOG.error("failed to open native window: %s", e)
            # Fallback to browser
            subprocess.Popen(["open", "http://localhost:8765/ui"])

    def pair_clicked(self, _sender: rumps.MenuItem) -> None:
        if self._trigger_pairing is not None:
            self._trigger_pairing()
        else:
            _LOG.warning("[menubar] pair_clicked but no trigger_pairing callback set")

    def forget_clicked(self, _sender: rumps.MenuItem) -> None:
        if self._trigger_forget is not None:
            self._trigger_forget()
        else:
            _LOG.warning("[menubar] forget_clicked but no trigger_forget callback set")
