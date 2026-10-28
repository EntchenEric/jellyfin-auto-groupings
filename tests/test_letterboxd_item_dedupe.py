"""Regression tests for Letterboxd list de-duplication.

:func:`sync._build_letterboxd_items` deduplicated matches with
``match["Id"]``. That subscript assumed every Jellyfin item carries an ``Id``,
while the rest of the sync reads it as ``.get("Id")`` and skips unusable
values. Jellyfin omits ``Id`` on some entries, and a proxy or an older server
can answer without it, so a Letterboxd group whose matched title had no ``Id``
raised ``KeyError`` from the helper.

The exception escaped :func:`sync._process_group`, which only converts its own
error tuples into a per-group ``{"error": ...}`` result, so the whole
``run_sync()`` call aborted: every group after the broken one was never
synced, and the route answered 500 instead of the partial results the UI knows
how to render.

The dedupe has to keep working in the same pass — the same title reached
through both the IMDb and the TMDb index must still be emitted once.
"""

from __future__ import annotations

from typing import Any

import sync


def _imdb_index(imdb_id: str, item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {imdb_id.lower(): item}


def test_matched_item_without_id_does_not_raise():
    """A match with no ``Id`` used to abort the whole sync run."""
    item = {"Name": "No Id Movie", "Path": "/media/No Id Movie.mkv"}

    result = sync._build_letterboxd_items(
        ["tt1111111"], _imdb_index("tt1111111", item), {}
    )

    assert result == [item]


def test_item_without_id_is_not_silently_dropped():
    """It is linkable from ``Path``, so keeping it is the useful behaviour."""
    item = {"Name": "No Id Movie"}
    result = sync._build_letterboxd_items(
        ["tt1111111", "tt2222222"],
        {**_imdb_index("tt1111111", item), **_imdb_index("tt2222222", item)},
        {},
    )

    assert result == [item]


def test_null_id_is_handled_like_a_missing_one():
    item = {"Name": "Null Id", "Id": None}

    result = sync._build_letterboxd_items(
        ["tt1111111"], _imdb_index("tt1111111", item), {}
    )

    assert result == [item]


def test_same_item_via_imdb_and_tmdb_indexes_is_deduplicated():
    """Both indexes can point at one title; it must be emitted once."""
    item = {"Id": "abc123", "Name": "Shared"}

    result = sync._build_letterboxd_items(
        ["tt1111111", "4242"],
        _imdb_index("tt1111111", item),
        {"4242": item},
    )

    assert result == [item]


def test_deduplication_without_ids_uses_identity():
    """Two id-less entries that are the same object must still collapse."""
    item = {"Name": "Shared No Id"}

    result = sync._build_letterboxd_items(
        ["tt1111111", "4242"],
        _imdb_index("tt1111111", item),
        {"4242": item},
    )

    assert result == [item]


def test_distinct_idless_items_are_both_kept():
    """Object identity must not merge two genuinely different titles."""
    first = {"Name": "First"}
    second = {"Name": "Second"}

    result = sync._build_letterboxd_items(
        ["tt1111111", "tt2222222"],
        {**_imdb_index("tt1111111", first), **_imdb_index("tt2222222", second)},
        {},
    )

    assert result == [first, second]


def test_external_list_order_is_preserved():
    first = {"Id": "1", "Name": "First"}
    second = {"Id": "2", "Name": "Second"}

    result = sync._build_letterboxd_items(
        ["tt2222222", "tt1111111"],
        {**_imdb_index("tt1111111", first), **_imdb_index("tt2222222", second)},
        {},
    )

    assert result == [second, first]


def test_unmatched_external_ids_are_skipped():
    item = {"Id": "1", "Name": "Only"}

    result = sync._build_letterboxd_items(
        ["tt9999999", "tt1111111"],
        _imdb_index("tt1111111", item),
        {},
    )

    assert result == [item]


def test_numeric_ids_are_looked_up_in_the_tmdb_index():
    """A non-``tt`` id belongs to TMDb, so it must not match an IMDb entry."""
    item = {"Id": "1", "Name": "Only"}

    result = sync._build_letterboxd_items(
        ["1111111"],
        _imdb_index("tt1111111", item),
        {"1111111": item},
    )

    assert result == [item]
