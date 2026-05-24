"""
DeckBridge update checker — polls GitHub Releases API in a background daemon thread.

Checks on startup (after a 30 s delay) and every 24 h thereafter.
Never blocks the main thread. On finding a newer release, calls the registered callback
so the platform UI can surface the notification.

Dismissed versions are persisted in ~/.deckbridge/update_state.json so the user
is not nagged again for the same release.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

_LOG = logging.getLogger("deckbridge.update")

_REPO = "JUANES545/DeckBridgeAgent"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_RELEASES_URL = f"https://github.com/{_REPO}/releases/latest"
_STATE_FILE = Path.home() / ".deckbridge" / "update_state.json"
_CHECK_DELAY_S = 30        # wait after startup before first check
_CHECK_INTERVAL_S = 86_400  # 24 h between subsequent checks

# Module-level state — read by /api/status without locks (written only from bg thread)
_latest_version: Optional[str] = None
_update_available: bool = False
_download_url: str = _RELEASES_URL


def _parse_version(v: str) -> tuple[int, ...]:
    """'1.2.3' or 'v1.2.3' -> (1, 2, 3). Returns (0,) on any error."""
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def _read_current_version() -> str:
    """Read version from CHANGELOG.md — handles source, onefile, and onedir PyInstaller bundles."""
    import sys as _sys
    candidates = []
    meipass = getattr(_sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "CHANGELOG.md")
    candidates.append(Path(_sys.executable).resolve().parent / "CHANGELOG.md")
    candidates.append(Path(__file__).resolve().parent / "CHANGELOG.md")
    for changelog in candidates:
        try:
            with changelog.open(encoding="utf-8") as f:
                for line in f:
                    if line.startswith("## ["):
                        return line[4:line.index("]")].strip()
        except Exception:
            continue
    return "0.0.0"


def _read_dismissed() -> str:
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        return str(data.get("dismissed_version", "")).strip()
    except Exception:
        return ""


def _write_dismissed(version: str) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        try:
            existing = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        existing["dismissed_version"] = version
        _STATE_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as e:
        _LOG.debug("update: could not write dismissed state: %s", e)


def _fetch_latest() -> Optional[tuple[str, str]]:
    """Returns (version_str, html_url) or None on any error."""
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DeckBridgeAgent/update-checker",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name", "")).strip()
        url = str(data.get("html_url", _RELEASES_URL)).strip() or _RELEASES_URL
        if not tag:
            return None
        return tag.lstrip("v"), url
    except Exception as e:
        _LOG.debug("update: fetch failed (%s)", type(e).__name__)
        return None


def _check_once(on_update: Callable[[str, str], None]) -> None:
    global _latest_version, _update_available, _download_url

    current = _read_current_version()
    result = _fetch_latest()
    if result is None:
        return

    latest, url = result
    _latest_version = latest
    _download_url = url

    if _parse_version(latest) <= _parse_version(current):
        _LOG.info("update: up to date (current=%s latest=%s)", current, latest)
        _update_available = False
        return

    dismissed = _read_dismissed()
    if dismissed and _parse_version(dismissed) >= _parse_version(latest):
        _LOG.info("update: v%s available but user already dismissed it", latest)
        return

    _LOG.info("update: new version available %s -> %s url=%s", current, latest, url)
    _update_available = True
    try:
        on_update(latest, url)
    except Exception as e:
        _LOG.warning("update: on_update callback error: %s", e)


def start_update_checker(on_update: Callable[[str, str], None]) -> None:
    """
    Start background update-check loop in a daemon thread.
    on_update(version, download_url) is called when a newer release is found.
    It will NOT be called again for the same version if dismissed.
    """
    def _loop() -> None:
        time.sleep(_CHECK_DELAY_S)
        while True:
            _check_once(on_update)
            time.sleep(_CHECK_INTERVAL_S)

    t = threading.Thread(target=_loop, name="deckbridge-update", daemon=True)
    t.start()
    _LOG.info(
        "update: checker started (delay=%ds, interval=%dh repo=%s)",
        _CHECK_DELAY_S, _CHECK_INTERVAL_S // 3600, _REPO,
    )


def dismiss_version(version: str) -> None:
    """Persist dismissal so the notification won't reappear for this version."""
    _write_dismissed(version)
    _LOG.info("update: dismissed v%s", version)


def get_update_state() -> dict:
    """Snapshot for inclusion in /api/status."""
    return {
        "update_available": _update_available,
        "latest_version": _latest_version,
        "download_url": _download_url if _update_available else None,
    }
