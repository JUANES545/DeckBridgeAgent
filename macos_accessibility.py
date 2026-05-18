"""
macOS-only helpers: Accessibility trust (for pynput / synthetic input) vs pairing HTTP (which does not need it).

Pairing and /health work without Accessibility; missing trust usually shows up only on POST /action.

Public API
----------
accessibility_trusted()                → bool | None
request_accessibility_prompt()         → triggers the system "grant access" dialog
open_accessibility_settings()          → opens System Settings to the right pane
prompt_and_wait_for_accessibility()    → blocking: shows Tkinter window, polls until granted
log_accessibility_banner_if_needed()   → console-only banner (legacy)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import subprocess
import sys
import threading
import time

_LOG = logging.getLogger("deckbridge.macos")

# ── Low-level AX API ─────────────────────────────────────────────────────────

def _load_ax() -> ctypes.CDLL | None:
    if sys.platform != "darwin":
        return None
    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        return ctypes.CDLL(lib_path) if lib_path else None
    except Exception:
        return None


def accessibility_trusted() -> bool | None:
    """
    True if this process is trusted for Accessibility (AX API).
    None if the check could not run (non-macOS or missing framework).
    NOTE: intentionally NOT cached so repeated calls reflect live state.
    """
    lib = _load_ax()
    if lib is None:
        return None
    try:
        fn = lib.AXIsProcessTrusted
        fn.argtypes = []
        fn.restype = ctypes.c_bool
        return bool(fn())
    except Exception as e:
        _LOG.debug("accessibility_trusted check failed: %s", e)
        return None


def request_accessibility_prompt() -> None:
    """
    Trigger the macOS system dialog that asks the user to grant Accessibility access.
    Uses AXIsProcessTrustedWithOptions(kAXTrustedCheckOptionPrompt = True).
    This opens System Settings automatically AND shows the lock dialog.
    """
    lib = _load_ax()
    if lib is None:
        return
    try:
        # kAXTrustedCheckOptionPrompt key
        _CF = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))

        # Build CFDictionary with {kAXTrustedCheckOptionPrompt: kCFBooleanTrue}
        # Simpler: call AXIsProcessTrustedWithOptions via objc bridge or just open settings
        fn = lib.AXIsProcessTrustedWithOptions
        fn.restype = ctypes.c_bool
        # We pass NULL which macOS treats as "prompt=false" but still triggers registration.
        # The proper approach is to open settings directly (more reliable cross-version).
        fn(None)
    except Exception as e:
        _LOG.debug("AXIsProcessTrustedWithOptions: %s", e)


def open_accessibility_settings() -> None:
    """Open System Settings → Privacy & Security → Accessibility."""
    try:
        # macOS 13+ (Ventura and later) uses x-apple.systempreferences URLs
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])
    except Exception as e:
        _LOG.debug("open_accessibility_settings: %s", e)


# ── Tkinter permission window ─────────────────────────────────────────────────

def prompt_and_wait_for_accessibility(timeout_s: float = 120.0) -> bool:
    """
    Blocking call (runs its own Tk main loop in the calling thread).

    Shows a native-looking macOS permission window:
      - Icon + title + instructions
      - "Abrir Ajustes del Sistema" button → opens the right pane
      - Status label that updates to "✓ Permiso concedido" when trusted
      - Auto-closes when permission is granted

    Returns True when Accessibility is granted, False if timeout reached.
    """
    if accessibility_trusted():
        return True

    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except Exception as e:
        _LOG.error("tkinter unavailable (%s); skipping permission UI", e)
        # Fall back to just opening settings + waiting in console
        _console_wait_for_accessibility(timeout_s)
        return bool(accessibility_trusted())

    granted = threading.Event()
    root: tk.Tk | None = None

    def _poll_permission(label: tk.Label, btn_ok: tk.Button) -> None:
        """Runs in background thread, polls every second."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(1.0)
            if accessibility_trusted():
                granted.set()
                try:
                    label.config(
                        text="✓ Permiso concedido — iniciando…",
                        fg="#1a9e5c",
                    )
                    btn_ok.config(state="disabled")
                    root.after(1200, root.destroy)  # type: ignore[union-attr]
                except Exception:
                    pass
                return
        # Timeout
        try:
            root.after(0, root.destroy)  # type: ignore[union-attr]
        except Exception:
            pass

    root = tk.Tk()
    root.title("DeckBridge — Permiso requerido")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")

    # Center on screen
    w, h = 500, 340
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # Keep window on top so user sees it
    root.attributes("-topmost", True)

    # ── Icon area ────────────────────────────────────────────────────────────
    top_frame = tk.Frame(root, bg="#1e1e2e", pady=24)
    top_frame.pack(fill="x")

    icon_label = tk.Label(
        top_frame,
        text="⌨",
        font=("SF Pro Display", 48) if sys.platform == "darwin" else ("Helvetica", 48),
        bg="#1e1e2e",
        fg="#a0a8d0",
    )
    icon_label.pack()

    # ── Title ────────────────────────────────────────────────────────────────
    title_label = tk.Label(
        root,
        text="Accesibilidad requerida",
        font=("SF Pro Display", 17, "bold") if sys.platform == "darwin" else ("Helvetica", 17, "bold"),
        bg="#1e1e2e",
        fg="#e0e4ff",
    )
    title_label.pack(pady=(0, 10))

    # ── Body text ────────────────────────────────────────────────────────────
    body = tk.Label(
        root,
        text=(
            "DeckBridge necesita el permiso de Accesibilidad\n"
            "para enviar atajos de teclado al sistema.\n\n"
            "1. Haz clic en \"Abrir Ajustes del Sistema\"\n"
            "2. Activa DeckBridgeMacAgent en la lista\n"
            "3. Esta ventana se cerrará automáticamente"
        ),
        font=("SF Pro Text", 13) if sys.platform == "darwin" else ("Helvetica", 13),
        bg="#1e1e2e",
        fg="#9ba3c9",
        justify="left",
        wraplength=420,
    )
    body.pack(padx=40, pady=(0, 18))

    # ── Status label ─────────────────────────────────────────────────────────
    status_label = tk.Label(
        root,
        text="Esperando permiso…",
        font=("SF Pro Text", 12) if sys.platform == "darwin" else ("Helvetica", 12),
        bg="#1e1e2e",
        fg="#ffb020",
    )
    status_label.pack(pady=(0, 16))

    # ── Buttons ──────────────────────────────────────────────────────────────
    btn_frame = tk.Frame(root, bg="#1e1e2e")
    btn_frame.pack()

    btn_settings = tk.Button(
        btn_frame,
        text="Abrir Ajustes del Sistema",
        font=("SF Pro Text", 13) if sys.platform == "darwin" else ("Helvetica", 13),
        bg="#3d62ff",
        fg="white",
        activebackground="#2a4eee",
        activeforeground="white",
        relief="flat",
        padx=18,
        pady=8,
        cursor="pointinghand",
        command=lambda: (open_accessibility_settings(), request_accessibility_prompt()),
    )
    btn_settings.grid(row=0, column=0, padx=8)

    btn_ok = tk.Button(
        btn_frame,
        text="Ya lo concedí",
        font=("SF Pro Text", 13) if sys.platform == "darwin" else ("Helvetica", 13),
        bg="#2a2a3e",
        fg="#9ba3c9",
        activebackground="#3a3a50",
        activeforeground="white",
        relief="flat",
        padx=18,
        pady=8,
        cursor="pointinghand",
        command=root.destroy,
    )
    btn_ok.grid(row=0, column=1, padx=8)

    # Start polling thread
    poll_thread = threading.Thread(
        target=_poll_permission,
        args=(status_label, btn_ok),
        daemon=True,
    )
    poll_thread.start()

    # Open settings immediately so the user doesn't have to click
    open_accessibility_settings()
    request_accessibility_prompt()

    root.mainloop()
    return bool(accessibility_trusted())


def _console_wait_for_accessibility(timeout_s: float = 120.0) -> None:
    """Fallback: console-only polling when Tkinter is unavailable."""
    open_accessibility_settings()
    print(
        "\n[DeckBridge] Se necesita el permiso de Accesibilidad.\n"
        "System Settings → Privacy & Security → Accessibility → activa DeckBridgeMacAgent.\n"
        "Esperando…",
        flush=True,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(2.0)
        if accessibility_trusted():
            print("[DeckBridge] ✓ Permiso de Accesibilidad concedido.", flush=True)
            return
    print("[DeckBridge] Tiempo agotado esperando Accesibilidad. Los atajos de teclado no funcionarán.", flush=True)


# ── Legacy banner (kept for server.py backward compat) ───────────────────────

def log_accessibility_banner_if_needed() -> None:
    """One stderr banner at startup when Accessibility is not yet granted."""
    trusted = accessibility_trusted()
    if trusted is True:
        _LOG.info("macOS Accessibility: trusted (OK for keyboard simulation)")
        return
    if trusted is None:
        return
    _LOG.warning(
        "macOS Accessibility: NOT trusted yet — pairing and /health still work; "
        "deck actions need System Settings → Privacy & Security → Accessibility "
        "(add Terminal, your IDE, or the built DeckBridgeMacAgent binary). "
        "Also enable Input Monitoring if macOS asks."
    )
    try:
        sys.stderr.write(
            "[deckbridge] macOS: concede «Accesibilidad» al programa que ejecuta el agente "
            "para que Copy/Paste y atajos lleguen al sistema. El QR/pairing no depende de esto.\n"
        )
    except OSError:
        pass