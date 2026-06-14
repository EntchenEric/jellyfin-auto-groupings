"""Additional tests covering uncovered lines in sync.py (PermissionError, OSError, etc.)."""

from unittest.mock import patch

import pytest

from sync import _maybe_handle_seasonal, _translate_path, run_sync


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


# ---------------------------------------------------------------------------
# _is_in_season edge cases
# ---------------------------------------------------------------------------


def test_is_in_season_missing_inputs() -> None:
    """Missing or non-string inputs return True (graceful degradation)."""
    from sync import _is_in_season

    assert _is_in_season(None, "06-15") is True  # type: ignore[arg-type]
    assert _is_in_season("06-15", None) is True  # type: ignore[arg-type]
    assert _is_in_season(None, None) is True  # type: ignore[arg-type]


def test_is_in_season_malformed_ranges() -> None:
    """Malformed dates return True (graceful degradation)."""
    from sync import _is_in_season

    assert _is_in_season("invalid", "06-15") is True
    assert _is_in_season("06-15", "invalid") is True
    assert _is_in_season("13-01", "06-15") is True
    assert _is_in_season("", "") is True


def test_is_in_season_same_year_window() -> None:
    """Same-year window (Jun-Aug) — current value in range."""
    from datetime import UTC, datetime

    from sync import _is_in_season

    # June 15 should be in season for Jun 1 - Sep 1
    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 6, 15, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _is_in_season("06-01", "09-01") is True


# ---------------------------------------------------------------------------
# Seasonal sync edge cases (covers issues #976-#983)
# ---------------------------------------------------------------------------


def test_is_in_season_single_day_season() -> None:
    """Single-day season (same start/end) never matches (window is [start, end)).
    Covers issue #982."""
    from datetime import UTC, datetime

    from sync import _is_in_season

    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 6, 15, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # Same day — s <= e but window is [s, e), so 06-15 < 06-15 is False
        assert _is_in_season("06-15", "06-15") is False

    # A leap-year single day
    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 2, 29, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _is_in_season("02-29", "02-29") is False


def test_is_in_season_dec_31_to_jan_1_wrap() -> None:
    """Dec 31 to Jan 1 wrap-around: only Dec 31 is in season.
    Covers issue #976."""
    from datetime import UTC, datetime

    from sync import _is_in_season

    # Jan 15 — should NOT be in [Dec 31, Jan 1) because current < end (Jan 1)
    # but wrap-around means current >= s(12-31) OR current < e(01-01)
    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 1, 15, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # current >= 12-31? No. current < 01-01? No (15 > 1).
        assert _is_in_season("12-31", "01-01") is False

    # Dec 31 — should be in season
    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 12, 31, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _is_in_season("12-31", "01-01") is True


def test_is_in_season_mar_1_to_feb_29_cross_leap() -> None:
    """Mar 1 to Feb 29 wrap-around (leap year — Feb 29 valid).
    Covers issue #977."""
    from datetime import UTC, datetime

    from sync import _is_in_season

    # Feb 28 — should be in season (current >= 03-01? No. current < 02-29? In wrap: 28 < 29 = Yes)
    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 2, 28, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _is_in_season("03-01", "02-29") is True


def test_is_in_season_leap_feb_29_as_start() -> None:
    """Feb 29 as start date (leap year).
    Covers issue #977."""
    from datetime import UTC, datetime

    from sync import _is_in_season

    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 2, 29, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _is_in_season("02-29", "03-15") is True  # Inclusive start


def test_is_in_season_invalid_mmdd_feb_31() -> None:
    """Invalid MM-DD like Feb 31 falls back to (0, 0) -> returns True.
    Covers issue #983."""
    from sync import _is_in_season

    # Feb 31 is not a valid date, so _parse_mmdd returns (0,0) -> graceful degradation
    assert _is_in_season("02-31", "06-01") is True
    assert _is_in_season("06-01", "02-31") is True


def test_parse_mmdd_feb_31_invalid() -> None:
    """Feb 31 is not a valid date -> returns (0, 0).
    Covers issue #983."""
    from sync import _parse_mmdd

    assert _parse_mmdd("02-31") == (0, 0)


def test_maybe_handle_seasonal_empty_name(tmp_path) -> None:
    """Out-of-season group with empty name is handled gracefully.
    Covers issue #979."""
    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "",
            str(tmp_path),
            dry_run=False,
        )
    assert result is not None
    assert result["group"] == "(unnamed)"
    assert result["status"] == "out_of_season"


def test_maybe_handle_seasonal_disabled_mid_season(tmp_path) -> None:
    """Group with seasonal_enabled=False returns None regardless.
    Covers issue #980."""
    result = _maybe_handle_seasonal(
        {"seasonal_enabled": False},
        "test-group",
        str(tmp_path),
        dry_run=False,
    )
    assert result is None


def test_maybe_handle_seasonal_dry_run_out_of_season(tmp_path) -> None:
    """Dry-run out-of-season: no directory deletion, returns result.
    Covers issue #981."""
    group_dir = tmp_path / "dry-seasonal"
    group_dir.mkdir()
    (group_dir / "movie.mkv").write_text("data")

    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "dry-seasonal",
            str(tmp_path),
            dry_run=True,
        )
    assert result is not None
    assert result["status"] == "out_of_season"
    assert group_dir.exists()  # Not deleted in dry run


def test_maybe_handle_seasonal_live_delete_out_of_season(tmp_path) -> None:
    """Live run out-of-season: directory is deleted.
    Covers issue #981."""
    group_dir = tmp_path / "live-seasonal"
    group_dir.mkdir()
    (group_dir / "movie.mkv").write_text("data")

    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "live-seasonal",
            str(tmp_path),
            dry_run=False,
        )
    assert result is not None
    assert result["status"] == "out_of_season"
    assert not group_dir.exists()  # Deleted in live run


def test_maybe_handle_seasonal_no_name_out_of_season(tmp_path) -> None:
    """Out-of-season group with no name key returns (unnamed).
    Covers issue #979."""
    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "",
            str(tmp_path),
            dry_run=False,
        )
    assert result is not None
    assert result["group"] == "(unnamed)"
    assert result["status"] == "out_of_season"


# ---------------------------------------------------------------------------
# _dispatch_list_source edge cases
# ---------------------------------------------------------------------------


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


def test_dispatch_list_source_letterboxd_list() -> None:
    """_dispatch_list_source dispatches letterboxd_list to _fetch_items_for_letterboxd_group."""
    from sync import _dispatch_list_source

    items, error, code = _dispatch_list_source(
        "letterboxd_list",
        "LB-Group",
        "https://letterboxd.com/user/list/my-list",
        "name",
        "http://jf:8096",
        "testkey",
        "",
    )
    # Without a patched fetch_letterboxd_list, it will return error
    # but the dispatch itself should not raise and should reach the handler
    assert error is not None
    assert code != 200
    assert isinstance(items, list)


# ---------------------------------------------------------------------------
# _build_letterboxd_items dedup edge cases
# ---------------------------------------------------------------------------


def test_build_letterboxd_items_list_order_dedup() -> None:
    """letterboxd_list_order skips duplicates when same Jellyfin item matched via both IMDb and TMDb."""
    from sync import _build_letterboxd_items

    # External IDs: two entries that both map to the same Jellyfin item
    external_ids = ["tt999", "123"]
    items_by_imdb = {"tt999": {"Id": "item1", "Name": "Movie A"}}
    items_by_tmdb = {"123": {"Id": "item1", "Name": "Movie A"}}

    result = _build_letterboxd_items(
        external_ids,
        items_by_imdb,
        items_by_tmdb,
    )
    assert len(result) == 1
    assert result[0]["Id"] == "item1"


def test_build_letterboxd_items_priority_order_dedup() -> None:
    """Deduplicates entries regardless of sort request."""
    from sync import _build_letterboxd_items

    external_ids = ["tt999", "123"]
    items_by_imdb = {"tt999": {"Id": "item1", "Name": "Movie A"}}
    items_by_tmdb = {"123": {"Id": "item1", "Name": "Movie A"}}

    result = _build_letterboxd_items(
        external_ids,
        items_by_imdb,
        items_by_tmdb,
    )
    assert len(result) == 1
    assert result[0]["Id"] == "item1"


def test_build_letterboxd_items_unmatched_id_skipped() -> None:
    """An external ID that matches neither IMDb nor TMDb indices is skipped."""
    from sync import _build_letterboxd_items

    # External IDs: one matches, one matches nothing
    external_ids = ["tt999", "unmatched_id_12345"]
    items_by_imdb: dict[str, dict[str, object]] = {
        "tt999": {"Id": "item1", "Name": "Movie A"},
    }
    items_by_tmdb: dict[str, dict[str, object]] = {}

    result = _build_letterboxd_items(
        external_ids,
        items_by_imdb,
        items_by_tmdb,
    )
    assert len(result) == 1
    assert result[0]["Id"] == "item1"


# ---------------------------------------------------------------------------
# parse_complex_query edge cases
# ---------------------------------------------------------------------------


def test_parse_complex_query_bare_not_with_value() -> None:
    """Bare NOT at start produces an AND NOT rule with parsed value."""
    from sync import parse_complex_query

    rules = parse_complex_query("NOT Comedy", "genre")
    assert len(rules) == 1
    assert rules[0]["operator"] == "AND NOT"
    assert rules[0]["type"] == "genre"
    assert rules[0]["value"] == "Comedy"


def test_parse_complex_query_bare_not_with_type() -> None:
    """Bare NOT followed by a typed negation (NOT actor:Tom)."""
    from sync import parse_complex_query

    rules = parse_complex_query("NOT actor:Tom", "genre")
    assert len(rules) == 1
    assert rules[0]["operator"] == "AND NOT"
    assert rules[0]["type"] == "actor"
    assert rules[0]["value"] == "Tom"


def test_parse_complex_query_bare_not_only() -> None:
    """Just 'NOT' with no value is parsed gracefully."""
    from sync import parse_complex_query

    rules = parse_complex_query("NOT", "genre")
    assert len(rules) == 1
    assert rules[0]["operator"] == "AND NOT"
    assert rules[0]["value"] == ""


def test_parse_complex_query_mixed_operators() -> None:
    """Complex query with AND and OR."""
    from sync import parse_complex_query

    rules = parse_complex_query("Action AND NOT Comedy OR Drama", "genre")
    assert len(rules) == 3
    assert rules[0]["operator"] == "AND"
    assert rules[0]["value"] == "Action"
    assert rules[1]["operator"] == "AND NOT"
    assert rules[1]["value"] == "Comedy"
    assert rules[2]["operator"] == "OR"
    assert rules[2]["value"] == "Drama"
