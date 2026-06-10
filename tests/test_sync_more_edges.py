"""Additional edge-case tests for sync.py uncovered lines.

Covers:
- _parse_mmdd with leading-zero months/days
- _parse_mmdd with negative numbers
- _parse_mmdd with extra dashes
- _maybe_handle_seasonal with non-dry-run directory deletion (OSError)
- _maybe_handle_seasonal returns None when seasonal_enabled is false
- clear_library_cache
- _filter_by_watch_state with edge cases
- run_cleanup_broken_symlinks OSError on unlink
- run_sync with empty group_names list
- run_sync with invalid group entries (non-dict)
"""

from unittest.mock import patch

from sync import (
    _filter_by_watch_state,
    _maybe_handle_seasonal,
    _parse_mmdd,
    run_cleanup_broken_symlinks,
    run_sync,
)

# ---------------------------------------------------------------------------
# _parse_mmdd additional edge cases
# ---------------------------------------------------------------------------


def test_parse_mmdd_leading_zeros() -> None:
    """Leading zeros are valid (already covered by valid tests)."""
    assert _parse_mmdd("01-01") == (1, 1)
    assert _parse_mmdd("00-00") == (0, 0)  # month 0 is invalid


def test_parse_mmdd_negative_numbers() -> None:
    """Negative month or day returns (0, 0)."""
    assert _parse_mmdd("-1-15") == (0, 0)
    assert _parse_mmdd("01--1") == (0, 0)


def test_parse_mmdd_extra_dash() -> None:
    """Extra dashes in the middle result in unparseable int -> (0, 0)."""
    # "06-15-extra" splits to ["06", "15-extra"] -> int("15-extra") raises ValueError
    assert _parse_mmdd("06-15-extra") == (0, 0)


def test_parse_mmdd_whitespace_around() -> None:
    """Whitespace around the value is stripped."""
    assert _parse_mmdd("  06-15  ") == (6, 15)


def test_parse_mmdd_feb_29_leap_usable() -> None:
    """Feb 29 is valid (uses year 2000 which is leap)."""
    assert _parse_mmdd("02-29") == (2, 29)


def test_parse_mmdd_feb_30_invalid() -> None:
    """Feb 30 is always invalid."""
    assert _parse_mmdd("02-30") == (0, 0)


# ---------------------------------------------------------------------------
# _maybe_handle_seasonal edge cases
# ---------------------------------------------------------------------------


def test_maybe_handle_seasonal_not_seasonal() -> None:
    """Returns None when seasonal_enabled is False."""
    result = _maybe_handle_seasonal(
        {"seasonal_enabled": False},
        "test-group",
        "/tmp/target",
        False,
    )
    assert result is None


def test_maybe_handle_seasonal_out_of_season_non_dry_run(tmp_path) -> None:
    """Out-of-season group has its directory deleted in non-dry-run mode."""
    group_dir = tmp_path / "test-group"
    group_dir.mkdir()
    (group_dir / "dummy.txt").write_text("hello")

    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "test-group",
            str(tmp_path),
            dry_run=False,
        )
    assert result is not None
    assert result.get("status") == "out_of_season"
    # Directory should have been deleted
    assert not group_dir.exists()


def test_maybe_handle_seasonal_out_of_season_dry_run(tmp_path) -> None:
    """Out-of-season group returns result without deleting directory in dry-run."""
    group_dir = tmp_path / "test-group-dry"
    group_dir.mkdir()
    (group_dir / "dummy.txt").write_text("hello")

    with patch("sync._is_in_season", return_value=False):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "test-group-dry",
            str(tmp_path),
            dry_run=True,
        )
    assert result is not None
    assert result.get("status") == "out_of_season"
    # Directory should still exist (dry run)
    assert group_dir.exists()


def test_maybe_handle_seasonal_in_season(tmp_path) -> None:
    """In-season group returns None (proceed normally)."""
    with patch("sync._is_in_season", return_value=True):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "12-31",
            },
            "test-group",
            str(tmp_path),
            dry_run=False,
        )
    assert result is None


def test_maybe_handle_seasonal_out_of_season_oserror(tmp_path) -> None:
    """OSError during directory deletion does not crash."""
    group_dir = tmp_path / "test-group-oserror"
    group_dir.mkdir()

    with (
        patch("sync._is_in_season", return_value=False),
        patch("sync.shutil.rmtree", side_effect=OSError("Permission denied")),
    ):
        result = _maybe_handle_seasonal(
            {
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            },
            "test-group-oserror",
            str(tmp_path),
            dry_run=False,
        )
    # Should still return a result gracefully
    assert result is not None
    assert result.get("status") == "out_of_season"


# ---------------------------------------------------------------------------
# clear_library_cache
# ---------------------------------------------------------------------------


def test_clear_library_cache() -> None:
    """clear_library_cache clears the internal library cache dict."""
    from sync import _LIBRARY_CACHE, clear_library_cache

    _LIBRARY_CACHE[("http://jf:8096", "key")] = [{"Id": "1"}]
    assert len(_LIBRARY_CACHE) == 1
    clear_library_cache()
    assert len(_LIBRARY_CACHE) == 0


# ---------------------------------------------------------------------------
# _filter_by_watch_state edge cases
# ---------------------------------------------------------------------------


def test_filter_by_watch_state_unwatched_empty_userdata() -> None:
    """Items with missing or empty UserData are treated as unwatched."""
    items: list = [
        {"Id": "1"},  # no UserData
        {"Id": "2", "UserData": None},  # None UserData
        {"Id": "3", "UserData": {}},  # empty UserData
        {"Id": "4", "UserData": {"Played": False}},  # explicit unplayed
    ]
    filtered = _filter_by_watch_state(items, "unwatched")
    assert len(filtered) == 4  # all are effectively unwatched


def test_filter_by_watch_state_watched_explicit() -> None:
    """Only items with Played=True are returned."""
    items: list = [
        {"Id": "1", "UserData": {"Played": True}},
        {"Id": "2", "UserData": {"Played": False}},
        {"Id": "3"},  # no UserData
    ]
    filtered = _filter_by_watch_state(items, "watched")
    assert len(filtered) == 1
    assert filtered[0]["Id"] == "1"


def test_filter_by_watch_state_no_filter() -> None:
    """Empty watch_state returns all items unchanged."""
    items: list = [{"Id": "1"}, {"Id": "2", "UserData": {"Played": True}}]
    filtered = _filter_by_watch_state(items, "")
    assert len(filtered) == 2
    assert filtered == items


# ---------------------------------------------------------------------------
# run_cleanup_broken_symlinks OSError edge case
# ---------------------------------------------------------------------------


def test_cleanup_broken_symlinks_oserror_on_unlink(tmp_path) -> None:
    """OSError during symlink unlink is handled gracefully."""
    target_base = tmp_path / "target"
    target_base.mkdir()
    broken_link = target_base / "broken.txt"
    broken_link.symlink_to(tmp_path / "nonexistent.txt")

    with patch("pathlib.Path.unlink", side_effect=OSError("Permission denied")):
        deleted_count = run_cleanup_broken_symlinks(
            {"target_path": str(target_base)},
        )
    # Should not crash, and the error should be logged
    assert deleted_count == 0


# ---------------------------------------------------------------------------
# run_sync edge cases
# ---------------------------------------------------------------------------


def test_run_sync_empty_group_names(tmp_path) -> None:
    """run_sync with empty group_names list returns no results."""
    config = {
        "jellyfin_url": "http://jf:8096",
        "api_key": "key",
        "target_path": str(tmp_path / "target"),
        "groups": [
            {"name": "G1", "source_type": "genre", "source_value": "Action"},
        ],
    }
    with (
        patch("sync.Path.mkdir"),
        patch("sync._process_group") as mock_process,
    ):
        results = run_sync(config, dry_run=True, group_names=[])
    assert len(results) == 0
    mock_process.assert_not_called()


def test_run_sync_skips_non_dict_group(tmp_path) -> None:
    """run_sync skips non-dict group entries gracefully."""
    config = {
        "jellyfin_url": "http://jf:8096",
        "api_key": "key",
        "target_path": str(tmp_path / "target"),
        "groups": [
            None,
            "not-a-dict",
            42,
            {"name": "G1", "source_type": "genre", "source_value": "Action"},
        ],
    }
    with (
        patch("sync.Path.mkdir"),
        patch("sync._process_group", return_value={"group": "G1", "links": 0}),
    ):
        results = run_sync(config, dry_run=True)
    assert len(results) == 1
    assert results[0]["group"] == "G1"


def test_run_sync_group_name_filter(tmp_path) -> None:
    """run_sync with group_names filters correctly."""
    config = {
        "jellyfin_url": "http://jf:8096",
        "api_key": "key",
        "target_path": str(tmp_path / "target"),
        "groups": [
            {"name": "Alpha", "source_type": "genre", "source_value": "Action"},
            {"name": "Beta", "source_type": "genre", "source_value": "Comedy"},
        ],
    }
    with (
        patch("sync.Path.mkdir"),
        patch("sync._process_group", return_value={"group": "mock", "links": 0}),
    ):
        results = run_sync(config, dry_run=True, group_names=["Alpha"])
    assert len(results) == 1
    assert results[0]["group"] == "mock"


# ---------------------------------------------------------------------------
# _process_group edge cases (direct)
# ---------------------------------------------------------------------------


def test_process_group_empty_name() -> None:
    """_process_group returns error for empty group name."""
    from sync import _process_group

    result = _process_group(
        {"name": ""},
        "/tmp/target",
        "http://jf:8096",
        "key",
        "",
        "",
        "",
        "",
        "",
    )
    assert result.get("error") is not None
    assert "Empty group name" in result["error"]
    assert result["links"] == 0