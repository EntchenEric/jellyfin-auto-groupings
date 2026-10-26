"""Regression tests for documented helper contracts.

These helpers are documented as tolerating unusable input, and three of them
did not:

* ``chunk_list([], 0)`` returned ``[[]]`` — one empty chunk instead of none,
  so "nothing to do" looked like one work item.
* ``group_by_key`` used the raw field value as a dictionary key, so an item
  whose field holds a list (Jellyfin's ``Genres``, ``Tags``, ``Studios``) raised
  ``TypeError: unhashable type: 'list'`` and aborted the whole grouping pass.
* ``format_release_date`` matched its patterns from the very start of the raw
  value, so a padded date fell through to the raw-input fallback and was
  returned with its whitespace intact.
"""

from __future__ import annotations

import pytest

from utils.formatting import format_release_date
from utils.helpers import chunk_list, group_by_key


def test_chunk_list_returns_no_chunks_for_empty_input_at_any_size():
    assert chunk_list([], 2) == []
    # A non-positive size means "one chunk", but an empty list is still empty.
    assert chunk_list([], 0) == []
    assert chunk_list([], -1) == []


def test_chunk_list_still_wraps_a_non_empty_list_for_a_non_positive_size():
    assert chunk_list([1, 2], 0) == [[1, 2]]
    assert chunk_list([1, 2], -1) == [[1, 2]]


def test_group_by_key_skips_unhashable_field_values():
    """A list-valued field must not abort the grouping pass."""
    items = [
        {"Name": "A", "Genres": ["Action", "Drama"]},
        {"Name": "B", "Genres": "Comedy"},
        {"Name": "C"},
    ]

    grouped = group_by_key(items, "Genres")

    assert grouped == {"Comedy": [items[1]]}


def test_group_by_key_keeps_hashable_values_in_first_seen_order():
    items = [
        {"Name": "A", "Genre": "Action"},
        {"Name": "B", "Genre": "Comedy"},
        {"Name": "C", "Genre": "Action"},
    ]

    grouped = group_by_key(items, "Genre")

    assert list(grouped) == ["Action", "Comedy"]
    assert [entry["Name"] for entry in grouped["Action"]] == ["A", "C"]


def test_group_by_key_ignores_null_values():
    assert group_by_key([{"Genre": None}], "Genre") == {}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  2023-05-12  ", "2023-05-12"),
        (" 2023-05-12T14:30:00Z", "2023-05-12"),
        ("\t2023-05\n", "2023-05"),
        (" 2023 ", "2023"),
        ("   ", ""),
    ],
)
def test_format_release_date_strips_surrounding_whitespace(value, expected):
    assert format_release_date(value) == expected


def test_format_release_date_still_returns_unmatched_text_as_is():
    assert format_release_date("invalid-date") == "invalid-date"
