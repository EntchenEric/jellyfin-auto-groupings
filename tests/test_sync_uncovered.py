"""Additional tests covering uncovered lines in sync.py (PermissionError, OSError, etc.)."""

from unittest.mock import patch

import pytest

from sync import _translate_path, run_sync


def test_translate_path_empty_root() -> None:
    """_translate_path returns original path when jellyfin_root/host_root are empty."""
    result = _translate_path("/media/movie.mkv", "", "/host")
    assert result == "/media/movie.mkv"
    result = _translate_path("/media/movie.mkv", "/media", "")
    assert result == "/media/movie.mkv"


def test_translate_path_not_relative() -> None:
    """_translate_path returns original path when not relative to jellyfin_root."""
    result = _translate_path("/other/movie.mkv", "/media", "/host")
    assert result == "/other/movie.mkv"


def test_run_sync_permission_error(tmp_path) -> None:
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


def test_run_sync_permission_error_dry_run_skips(tmp_path) -> None:
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


def test_run_sync_no_url_or_api_key() -> None:
    """run_sync raises ValueError when url, api_key, or target_path not set."""
    with pytest.raises(
        ValueError,
        match="Server settings or target path not configured",
    ):
        run_sync({"jellyfin_url": "", "api_key": "", "target_path": ""})


# ---------------------------------------------------------------------------
# _parse_mmdd edge cases
# ---------------------------------------------------------------------------


def test_parse_mmdd_non_string_value() -> None:
    """Non-string input returns (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd(None) == (0, 0)  # type: ignore[arg-type]


def test_parse_mmdd_empty_string() -> None:
    """Empty or whitespace-only strings return (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd("") == (0, 0)
    assert _parse_mmdd("   ") == (0, 0)


def test_parse_mmdd_no_dash() -> None:
    """Missing dash separator returns (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd("1231") == (0, 0)
    assert _parse_mmdd("nodash") == (0, 0)


def test_parse_mmdd_valid() -> None:
    """Valid MM-DD returns parsed tuple."""
    from sync import _parse_mmdd

    assert _parse_mmdd("06-15") == (6, 15)
    assert _parse_mmdd("01-01") == (1, 1)
    assert _parse_mmdd("12-31") == (12, 31)


def test_parse_mmdd_invalid_month() -> None:
    """Invalid month returns (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd("13-01") == (0, 0)
    assert _parse_mmdd("00-15") == (0, 0)


def test_parse_mmdd_invalid_day() -> None:
    """Invalid day for month returns (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd("02-30") == (0, 0)
    assert _parse_mmdd("04-31") == (0, 0)


def test_parse_mmdd_non_numeric() -> None:
    """Non-numeric month/day returns (0, 0)."""
    from sync import _parse_mmdd

    assert _parse_mmdd("ab-cd") == (0, 0)
    assert _parse_mmdd("01-XX") == (0, 0)


def test_dispatch_list_source_unknown_type() -> None:
    """_dispatch_list_source returns ( [], error_msg, 400 ) for unknown source_type."""
    from sync import _dispatch_list_source

    items, error, code = _dispatch_list_source(
        "nonexistent_source",
        "test-group",
        "val",
        "name",
        "http://jf:8096",
        "key",
        "",
    )
    assert items == []
    assert error is not None
    assert "Unknown source type" in error
    assert code == 400
