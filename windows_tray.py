"""
Windows system-tray icon and menu for DeckBridge.

Only imported on Windows — raises ImportError on other platforms so macOS
code paths are never accidentally affected.
"""

from __future__ import annotations

import sys

if sys.platform != "win32":
    raise ImportError("windows_tray is Windows-only")

import logging
import threading
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image, ImageDraw

_LOG = logging.getLogger("deckbridge.tray")


def _tray_icon_image() -> Image.Image:
    """Load Windows tray icon (32×32 RGBA with color) or fall back."""
    candidates = [
        Path(__file__).resolve().parent / "builds" / "windows" / "tray_icon.png",
        Path(__file__).resolve().parent / "tray_icon.png",         # PyInstaller bundle
        Path(__file__).resolve().parent / "builds" / "mac" / "menubar_template.png",
        Path(__file__).resolve().parent / "menubar_template.png",
    ]
    for p in candidates:
        if p.exists():
            try:
                img = Image.open(p).convert("RGBA").resize((32, 32), Image.LANCZOS)
                _LOG.info("tray icon loaded from %s", p)
                return img
            except Exception as e:
                _LOG.warning("failed to load icon from %s: %s", p, e)

    # Programmatic fallback: blue square with a white 3x2 grid
    size = 22
    img = Image.new("RGBA", (size, size), (30, 100, 220, 255))
    draw = ImageDraw.Draw(img)
    # Draw a simple white grid (3 columns x 2 rows)
    cell_w = size // 3
    cell_h = size // 2
    for col in range(3):
        for row in range(2):
            x0 = col * cell_w + 2
            y0 = row * cell_h + 2
            x1 = x0 + cell_w - 4
            y1 = y0 + cell_h - 4
            draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 220))
    return img


class WindowsTray:
    """System-tray icon and right-click menu for DeckBridge on Windows.

    Call `run()` on the main thread — pystray.Icon.run() blocks like rumps.App.run().
    """

    def __init__(self) -> None:
        self._trigger_pairing: Callable[[], None] | None = None
        self._trigger_forget: Callable[[], None] | None = None

        self._status_text: str = "Iniciando..."
        self._ip_text: str = ""
        self._window_thread: threading.Thread | None = None

        self._icon = pystray.Icon(
            "DeckBridge",
            _tray_icon_image(),
            "DeckBridge",
            menu=self._build_menu(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_ux_callbacks(
        self,
        trigger_pairing_fn: Callable[[], None],
        trigger_forget_fn: Callable[[], None],
    ) -> None:
        self._trigger_pairing = trigger_pairing_fn
        self._trigger_forget = trigger_forget_fn

    def update_status(self, state: str, device_name: str | None, lan_ip: str) -> None:
        """Update status and IP lines in the tray menu.

        state values: "connected" | "paired" | "waiting_for_pairing" | "idle" | "error"
        """
        state_labels = {
            "connected": f"Verde  {device_name}",
            "paired": f"Amarillo  {device_name} (pareado)",
            "waiting_for_pairing": "Esperando confirmacion...",
            "idle": "Sin dispositivo pareado",
            "error": "Error",
        }
        self._status_text = state_labels.get(state, state)
        self._ip_text = f"{lan_ip}  :8765" if lan_ip else ""
        # Rebuild menu so pystray picks up the updated text
        self._icon.menu = self._build_menu()
        _LOG.debug("tray update_status state=%s device=%s ip=%s", state, device_name, lan_ip)

    def run(self) -> None:
        """Block the calling thread running the pystray event loop."""
        _LOG.info("tray icon starting")
        self._icon.run()

    # ------------------------------------------------------------------
    # Menu builder
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("DeckBridge", None, enabled=False),
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.MenuItem(self._ip_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Abrir DeckBridge...", self.open_window_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Parear con Android...", self.pair_clicked),
            pystray.MenuItem("Olvidar dispositivo", self.forget_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self.quit_clicked),
        )

    # ------------------------------------------------------------------
    # Menu action handlers
    # ------------------------------------------------------------------

    def open_window_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._window_thread and self._window_thread.is_alive():
            return  # window already open
        self._window_thread = threading.Thread(
            target=self._run_window, name="deckbridge-webview", daemon=True
        )
        self._window_thread.start()

    def _run_window(self) -> None:
        try:
            import webview
            win = webview.create_window(
                "DeckBridge",
                url="http://localhost:8765/ui",
                width=700,
                height=400,
                resizable=False,
                frameless=True,          # content fills 700×400 exactly — no title bar overhead
                background_color="#0d1117",
            )
            webview.start()
        except Exception as e:
            _LOG.warning("webview failed (%s) — trying Edge app mode", e)
            self._open_edge_app_window()

    def _open_edge_app_window(self) -> None:
        """Open DeckBridge UI in Edge --app mode (frameless, app-like window)."""
        import subprocess
        url = "http://localhost:8765/ui"
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for edge in edge_paths:
            try:
                subprocess.Popen([
                    edge,
                    f"--app={url}",
                    "--window-size=700,430",
                    "--window-position=200,100",
                ])
                _LOG.info("opened Edge app window")
                return
            except FileNotFoundError:
                continue
        # Last resort: default browser
        import webbrowser
        webbrowser.open(url)

    def pair_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._trigger_pairing is not None:
            threading.Thread(target=self._trigger_pairing, daemon=True).start()
        else:
            _LOG.warning("pair_clicked but no trigger_pairing callback set")

    def forget_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if self._trigger_forget is not None:
            threading.Thread(target=self._trigger_forget, daemon=True).start()
        else:
            _LOG.warning("forget_clicked but no trigger_forget callback set")

    def quit_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _LOG.info("tray quit clicked")
        icon.stop()
