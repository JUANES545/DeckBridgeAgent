"""
Per-process session log file for the DeckBridge agent (complements stderr logging).

* **Path:** ``<DECKBRIDGE_STATE_DIR>/logs/deckbridge_{mac|pc|agent}_session_<UTC>_<pid>.log`` (default under ``~/.deckbridge/logs/``).
* **Retention:** on each new process, delete session files older than **72 hours**, then keep at most **5** newest files.
* **Integration:** adds a ``logging.FileHandler`` to the root logger after ``configure_logging()`` (so ``basicConfig(..., force=True)`` does not wipe it).
"""

from __future__ import annotations

import atexit
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOG = logging.getLogger("deckbridge.session")

_session_path: Path | None = None
_file_handler: logging.Handler | None = None


def _session_prefix() -> str:
    if sys.platform == "darwin":
        return "deckbridge_mac_session_"
    if sys.platform == "win32":
        return "deckbridge_pc_session_"
    return "deckbridge_agent_session_"


def _state_dir() -> Path:
    return Path(os.environ.get("DECKBRIDGE_STATE_DIR", str(Path.home() / ".deckbridge"))).expanduser()


def _logs_dir() -> Path:
    d = _state_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def purge_old_session_files() -> None:
    """Drop logs older than 72h, then keep only the 5 newest session files."""
    d = _logs_dir()
    pattern = f"{_session_prefix()}*.log"
    paths = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    now = datetime.now(tz=timezone.utc).timestamp()
    max_age = 72 * 3600
    for p in paths:
        try:
            if now - p.stat().st_mtime > max_age:
                p.unlink(missing_ok=True)
        except OSError:
            pass
    remaining = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in remaining[5:]:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _flush_file_handler() -> None:
    if _file_handler is not None:
        try:
            _file_handler.flush()
        except Exception:
            pass


def start_session_file_log() -> Path | None:
    """
    Append a UTF-8 file handler to the root logger. Call once after ``configure_logging()``.

    Returns the log file path, or None if setup failed (agent still runs on stderr).
    """
    global _session_path, _file_handler
    if _file_handler is not None:
        return _session_path
    try:
        purge_old_session_files()
        stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        pid = os.getpid()
        path = _logs_dir() / f"{_session_prefix()}{stamp}_{pid}.log"
        fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        fh = logging.FileHandler(path, encoding="utf-8", delay=False)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logging.getLogger().addHandler(fh)
        _session_path = path
        _file_handler = fh
        atexit.register(_flush_file_handler)
        _LOG.info(
            "session log started path=%s state_dir=%s",
            path,
            _state_dir(),
        )
        return path
    except Exception as e:
        logging.getLogger("deckbridge.agent").warning("session file log disabled: %s", e)
        return None
