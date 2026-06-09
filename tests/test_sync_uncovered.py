"""Additional tests covering uncovered lines in sync.py (PermissionError, OSError, etc.)."""

from unittest.mock import patch

import pytest

from sync import _translate_path, run_sync


def test_translate_path_empty_root():
    """_translate_path returns original path when jellyfin_root/host_root are empty."""
    result = _translate_path("/media/movie.mkv", "", "/host")
    assert result == "/media/movie.mkv"
    result = _translate_path("/media/movie.mkv", "/media", "")
    assert result == "/media/movie.mkv"


def test_translate_path_not_relative():
    """_translate_path returns original path when not relative to jellyfin_root."""
    result = _translate_path("/other/movie.mkv", "/media", "/host")
    assert result == "/other/movie.mkv"


def test_run_sync_permission_error(tmp_path):
    """run_sync raises ValueError when target directory cannot be created due to permission."""
    config = {
        "jellyfin_url": "http://jf:8096",
        "api_key": "testkey",
        "target_path": str(tmp_path / "subdir"),
        "groups": [],
    }
    with patch("sync.Path.mkdir") as mock_mkdir:
        mock_mkdir.side_effect = PermissionError("Permission denied")
        with pytest.raises(ValueError, match="permission denied"):
            run_sync(config, dry_run=False)


def test_run_sync_permission_error_dry_run_skips(tmp_path):
    """dry_run=True skips directory creation, so PermissionError is not raised."""
    config = {
        "jellyfin_url": "http://jf:8096",
        "api_key": "testkey",
        "target_path": str(tmp_path / "subdir"),
        "groups": [],
    }
    with patch("sync.Path.mkdir") as mock_mkdir:
        mock_mkdir.side_effect = PermissionError("Permission denied")
        results = run_sync(config, dry_run=True)
        assert isinstance(results, list)
        assert len(results) == 0
        mock_mkdir.assert_not_called()


def test_run_sync_no_url_or_api_key():
    """run_sync raises ValueError when url, api_key, or target_path not set."""
    with pytest.raises(ValueError, match="Server settings or target path not configured"):
        run_sync({"jellyfin_url": "", "api_key": "", "target_path": ""})