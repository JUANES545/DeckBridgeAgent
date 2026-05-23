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
from typing import Callable

import rumps

_LOG = logging.getLogger("deckbridge.menubar")


class DeckBridgeMenuBar(rumps.App):
    """System-tray menu bar app for DeckBridge (macOS).

    Call `run()` on the main thread — rumps takes over the run loop.
    """

    def __init__(self) -> None:
        # quit_button=None: we provide our own Quit item so we control placement.
        super().__init__("🎛️", quit_button=None)

        # Menu item references kept for dynamic updates.
        self._item_header = rumps.MenuItem("DeckBridge")
        self._item_header.set_callback(None)

        self._item_status = rumps.MenuItem("Iniciando…")
        self._item_status.set_callback(None)

        self._item_ip = rumps.MenuItem("")
        self._item_ip.set_callback(None)

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
        _LOG.info("[menubar] open window — Phase 2 pending")

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
