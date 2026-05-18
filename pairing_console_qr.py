"""
Print a scannable QR to the terminal (no Tk). Fallback when the GUI popup is unavailable (SSH, PyInstaller, broken tk).
"""

from __future__ import annotations

import logging
import sys

_LOG = logging.getLogger("deckbridge.console_qr")


def print_pairing_qr_to_stdout(deeplink: str) -> bool:
    """
    Renders [deeplink] as a QR code using ASCII blocks (UTF-8).
    Returns True if something was printed.
    """
    if not deeplink or not deeplink.strip():
        return False
    try:
        import qrcode  # type: ignore[import-untyped]
    except ImportError:
        _LOG.warning("qrcode not installed; cannot print console QR")
        return False
    try:
        qr = qrcode.QRCode(version=None, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(deeplink)
        qr.make(fit=True)
        sys.stdout.write("\n── Scan this QR from DeckBridge (Connect → scan) ──\n")
        qr.print_ascii(tty=sys.stdout.isatty(), invert=True)
        sys.stdout.write("── (ASCII QR — GUI QR is sharper if the window opened) ──\n\n")
        sys.stdout.flush()
        _LOG.info("console QR printed deeplink_len=%s", len(deeplink))
        return True
    except Exception as e:
        _LOG.warning("console QR failed: %s", e)
        return False
