"""Tests for update_checker.py"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import update_checker  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion:
    def test_normal(self):
        assert update_checker._parse_version("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert update_checker._parse_version("v1.2.3") == (1, 2, 3)

    def test_malformed_returns_zero_tuple(self):
        assert update_checker._parse_version("not-a-version") == (0,)

    def test_single_part(self):
        assert update_checker._parse_version("2") == (2,)

    def test_two_parts(self):
        assert update_checker._parse_version("1.4") == (1, 4)

    def test_empty_string(self):
        assert update_checker._parse_version("") == (0,)

    def test_v_prefix_only(self):
        # "v" alone → strip → "" → split → [""] → int("") raises → (0,)
        assert update_checker._parse_version("v") == (0,)


# ---------------------------------------------------------------------------
# Version comparison logic (via _check_once)
# ---------------------------------------------------------------------------

class TestVersionComparison:
    """Exercises the comparison path inside _check_once without I/O side-effects."""

    def _run(self, current: str, latest: str) -> MagicMock:
        """Run _check_once with given versions and return the callback mock."""
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=(latest, "https://example.com")), \
             patch.object(update_checker, "_read_current_version", return_value=current), \
             patch.object(update_checker, "_read_dismissed", return_value=""), \
             tempfile.TemporaryDirectory() as tmp:
            update_checker._STATE_FILE = Path(tmp) / "update_state.json"
            update_checker._update_available = False
            update_checker._check_once(cb)
        return cb

    def test_newer_version_triggers_callback(self):
        cb = self._run("1.0.0", "2.0.0")
        cb.assert_called_once_with("2.0.0", "https://example.com")
        assert update_checker._update_available is True

    def test_patch_bump_triggers_callback(self):
        cb = self._run("1.0.0", "1.0.1")
        cb.assert_called_once()

    def test_minor_bump_triggers_callback(self):
        cb = self._run("1.0.0", "1.1.0")
        cb.assert_called_once()

    def test_equal_versions_no_callback(self):
        cb = self._run("1.0.0", "1.0.0")
        cb.assert_not_called()
        assert update_checker._update_available is False

    def test_older_latest_no_callback(self):
        cb = self._run("2.0.0", "1.9.9")
        cb.assert_not_called()
        assert update_checker._update_available is False


# ---------------------------------------------------------------------------
# _check_once — full behaviour
# ---------------------------------------------------------------------------

class TestCheckOnce:

    def test_update_available_sets_module_state(self):
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=("9.9.9", "https://dl.example.com")), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"), \
             patch.object(update_checker, "_read_dismissed", return_value=""), \
             tempfile.TemporaryDirectory() as tmp:
            update_checker._STATE_FILE = Path(tmp) / "state.json"
            update_checker._update_available = False
            update_checker._latest_version = None
            update_checker._download_url = update_checker._RELEASES_URL
            update_checker._check_once(cb)
        cb.assert_called_once_with("9.9.9", "https://dl.example.com")
        assert update_checker._update_available is True
        assert update_checker._latest_version == "9.9.9"
        assert update_checker._download_url == "https://dl.example.com"

    def test_no_update_when_same_version(self):
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=("1.0.0", "https://example.com")), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"):
            update_checker._update_available = False
            update_checker._check_once(cb)
        cb.assert_not_called()
        assert update_checker._update_available is False

    def test_api_failure_returns_early_no_crash(self):
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=None), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"):
            update_checker._check_once(cb)  # must not raise
        cb.assert_not_called()

    def test_dismissed_version_skips_callback(self):
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=("2.0.0", "https://example.com")), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"), \
             patch.object(update_checker, "_read_dismissed", return_value="2.0.0"):
            update_checker._check_once(cb)
        cb.assert_not_called()

    def test_dismissed_older_version_does_not_block_new_update(self):
        """If user dismissed 1.5.0 but latest is now 2.0.0, callback should fire."""
        cb = MagicMock()
        with patch.object(update_checker, "_fetch_latest", return_value=("2.0.0", "https://example.com")), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"), \
             patch.object(update_checker, "_read_dismissed", return_value="1.5.0"), \
             tempfile.TemporaryDirectory() as tmp:
            update_checker._STATE_FILE = Path(tmp) / "state.json"
            update_checker._update_available = False
            update_checker._check_once(cb)
        cb.assert_called_once_with("2.0.0", "https://example.com")

    def test_callback_exception_does_not_propagate(self):
        """Errors in on_update must be swallowed so the bg thread survives."""
        cb = MagicMock(side_effect=RuntimeError("UI unavailable"))
        with patch.object(update_checker, "_fetch_latest", return_value=("5.0.0", "https://example.com")), \
             patch.object(update_checker, "_read_current_version", return_value="1.0.0"), \
             patch.object(update_checker, "_read_dismissed", return_value=""), \
             tempfile.TemporaryDirectory() as tmp:
            update_checker._STATE_FILE = Path(tmp) / "state.json"
            update_checker._update_available = False
            update_checker._check_once(cb)  # must not raise


# ---------------------------------------------------------------------------
# dismiss_version + _read_dismissed
# ---------------------------------------------------------------------------

class TestDismiss:

    def test_write_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            update_checker._STATE_FILE = Path(tmp) / "update_state.json"
            try:
                update_checker.dismiss_version("1.5.0")
                assert update_checker._read_dismissed() == "1.5.0"
            finally:
                update_checker._STATE_FILE = original

    def test_dismiss_overwrites_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            update_checker._STATE_FILE = Path(tmp) / "update_state.json"
            try:
                update_checker.dismiss_version("1.0.0")
                update_checker.dismiss_version("2.0.0")
                assert update_checker._read_dismissed() == "2.0.0"
            finally:
                update_checker._STATE_FILE = original

    def test_dismiss_preserves_other_keys_in_state_file(self):
        """_write_dismissed should merge into existing JSON, not replace it."""
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            state_path = Path(tmp) / "update_state.json"
            state_path.write_text(json.dumps({"other_key": "some_value"}), encoding="utf-8")
            update_checker._STATE_FILE = state_path
            try:
                update_checker.dismiss_version("3.0.0")
                data = json.loads(state_path.read_text(encoding="utf-8"))
                assert data["dismissed_version"] == "3.0.0"
                assert data["other_key"] == "some_value"
            finally:
                update_checker._STATE_FILE = original

    def test_read_dismissed_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            update_checker._STATE_FILE = Path(tmp) / "nonexistent.json"
            try:
                assert update_checker._read_dismissed() == ""
            finally:
                update_checker._STATE_FILE = original

    def test_read_dismissed_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            state_path = Path(tmp) / "update_state.json"
            state_path.write_text("{not valid json", encoding="utf-8")
            update_checker._STATE_FILE = state_path
            try:
                assert update_checker._read_dismissed() == ""
            finally:
                update_checker._STATE_FILE = original

    def test_read_dismissed_empty_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = update_checker._STATE_FILE
            state_path = Path(tmp) / "update_state.json"
            state_path.write_text(json.dumps({}), encoding="utf-8")
            update_checker._STATE_FILE = state_path
            try:
                assert update_checker._read_dismissed() == ""
            finally:
                update_checker._STATE_FILE = original


# ---------------------------------------------------------------------------
# get_update_state
# ---------------------------------------------------------------------------

class TestGetUpdateState:

    def test_returns_expected_keys(self):
        state = update_checker.get_update_state()
        assert "update_available" in state
        assert "latest_version" in state
        assert "download_url" in state

    def test_no_url_when_no_update(self):
        update_checker._update_available = False
        update_checker._download_url = "https://irrelevant.com"
        state = update_checker.get_update_state()
        assert state["update_available"] is False
        assert state["download_url"] is None

    def test_url_present_when_update_available(self):
        update_checker._update_available = True
        update_checker._download_url = "https://github.com/JUANES545/DeckBridgeAgent/releases/tag/v9.9.9"
        update_checker._latest_version = "9.9.9"
        state = update_checker.get_update_state()
        assert state["update_available"] is True
        assert state["download_url"] == "https://github.com/JUANES545/DeckBridgeAgent/releases/tag/v9.9.9"
        assert state["latest_version"] == "9.9.9"
        # Reset
        update_checker._update_available = False
        update_checker._latest_version = None
        update_checker._download_url = update_checker._RELEASES_URL


# ---------------------------------------------------------------------------
# _read_current_version
# ---------------------------------------------------------------------------

class TestReadCurrentVersion:

    def test_reads_first_version_from_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            changelog = Path(tmp) / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## [1.11.6] - 2026-05-01\n### Added\n- stuff\n",
                encoding="utf-8",
            )
            # Temporarily redirect __file__ via patching Path resolution
            original_file = update_checker.__file__
            with patch.object(update_checker, "__file__", str(Path(tmp) / "update_checker.py")):
                version = update_checker._read_current_version()
            assert version == "1.11.6"

    def test_returns_fallback_on_missing_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Point __file__ to a dir that has no CHANGELOG.md
            with patch.object(update_checker, "__file__", str(Path(tmp) / "update_checker.py")):
                version = update_checker._read_current_version()
            assert version == "0.0.0"

    def test_returns_fallback_on_changelog_without_version_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            changelog = Path(tmp) / "CHANGELOG.md"
            changelog.write_text("# Just a header\nNo version lines here.\n", encoding="utf-8")
            with patch.object(update_checker, "__file__", str(Path(tmp) / "update_checker.py")):
                version = update_checker._read_current_version()
            assert version == "0.0.0"
