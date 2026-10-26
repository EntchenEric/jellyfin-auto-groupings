"""Regression tests for title-year parsing and collection sort keys.

Both helpers are fed by loosely typed Jellyfin payloads and by hand-written
titles, so the cases below are the ones that used to raise or silently corrupt
a name rather than the happy path alone.
"""

from __future__ import annotations

import pytest

from jellyfin_groupings import process_groupings
from utils.helpers import extract_year_from_title


class _SortKeyClient:
    """Minimal client stub returning one collection with the given items."""

    def __init__(self, items, collection_name="Star Wars"):
        self._items = items
        self._collection_name = collection_name

    def get_collections(self):
        return [{"Name": self._collection_name, "Id": "coll-1"}]

    def get_collection_items(self, _collection_id):
        return self._items


# ---------------------------------------------------------------------------
# extract_year_from_title
# ---------------------------------------------------------------------------


def test_extracts_year_when_bracket_touches_the_title():
    # ``"Movie[2023]"`` (no space before the bracket) has no separator for the
    # old pattern, so it was returned unchanged with no year.
    assert extract_year_from_title("Movie[2023]") == ("Movie", 2023)


def test_strips_padding_before_matching():
    # The patterns are anchored at the end of the value, so trailing padding
    # defeated every branch and the spaces came back in the title.
    assert extract_year_from_title("  Movie (2023)  ") == ("Movie", 2023)
    assert extract_year_from_title("\tThe Matrix 1999\n") == ("The Matrix", 1999)


def test_trims_whitespace_when_no_year_is_present():
    assert extract_year_from_title("  Avengers  ") == ("Avengers", None)


def test_does_not_split_a_five_digit_number():
    # Used to return ("Movie 1", 2345): the last four digits matched as a year
    # and the digit before them stayed behind in the title.
    assert extract_year_from_title("Movie 12345") == ("Movie 12345", None)


def test_rejects_out_of_range_years():
    assert extract_year_from_title("Movie 1234") == ("Movie 1234", None)
    assert extract_year_from_title("Movie 999") == ("Movie 999", None)


def test_accepts_the_years_already_used_by_decade_grouping():
    # group_by_decade keeps 1800-2100; a title year outside that range would
    # produce a split title but never a decade group.
    assert extract_year_from_title("Blade Runner 2049") == ("Blade Runner", 2049)
    assert extract_year_from_title("Movie 1800") == ("Movie", 1800)
    assert extract_year_from_title("Movie 2100") == ("Movie", 2100)


def test_title_that_is_only_a_year_keeps_its_text():
    # "1917" is the film's whole name; stripping the year left an empty name.
    assert extract_year_from_title("1917") == ("1917", None)
    assert extract_year_from_title("2023") == ("2023", None)


def test_unclosed_bracket_leaves_no_stray_punctuation():
    assert extract_year_from_title("Movie (2023") == ("Movie", 2023)


def test_a_period_that_ends_the_name_is_preserved():
    # Trimming every trailing punctuation character turned "Dr. (2023)" into
    # "Dr"; the period belongs to the name, not to the year separator.
    assert extract_year_from_title("Dr. (2023)") == ("Dr.", 2023)
    assert extract_year_from_title("Mr. Nobody 2009") == ("Mr. Nobody", 2009)


def test_separator_punctuation_is_trimmed():
    assert extract_year_from_title("Movie.2023") == ("Movie", 2023)
    assert extract_year_from_title("Movie-2023") == ("Movie", 2023)
    assert extract_year_from_title("Movie: 2023") == ("Movie", 2023)
    assert extract_year_from_title("Movie - 2023") == ("Movie", 2023)


def test_year_in_the_middle_is_left_alone():
    assert extract_year_from_title("Movie (2023) Extended") == (
        "Movie (2023) Extended",
        None,
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
def test_blank_titles_are_empty(blank):
    assert extract_year_from_title(blank) == ("", None)


# ---------------------------------------------------------------------------
# jellyfin_groupings.process_groupings sort key
# ---------------------------------------------------------------------------


def test_mixed_premiere_date_types_do_not_break_sorting():
    # A collection holding both a numeric year and an ISO string raised
    # ``TypeError: '<' not supported between instances of 'str' and 'int'``,
    # which aborted the entire pass.
    client = _SortKeyClient(
        [
            {"Id": "b", "PremiereDate": "2003-01-01"},
            {"Id": "a", "PremiereDate": 2004},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["b", "a"]


def test_numeric_premiere_date_sorts_chronologically():
    client = _SortKeyClient(
        [
            {"Id": "new", "PremiereDate": "2015-06-01"},
            {"Id": "old", "PremiereDate": 2001},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["old", "new"]


def test_items_without_a_name_do_not_raise():
    # ``item.get("Name", "").lower()`` raised AttributeError for a null Name.
    client = _SortKeyClient([{"Id": "a", "Name": None}, {"Id": "b"}])
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["a", "b"]
    assert all(name == "Unknown" for _, name, _ in changes)


def test_collection_with_null_name_falls_back_to_a_label():
    client = _SortKeyClient([{"Id": "a", "Name": "Movie"}], collection_name=None)
    changes = process_groupings(client, dry_run=True)
    assert changes == [("a", "Movie", "Collection 01")]


def test_unparseable_premiere_date_falls_back_to_the_title():
    # ``items_from_body`` accepts any item dict, so a placeholder string can
    # reach the sort key. Ranking it as a date pushed it ahead of undated items
    # and shifted every later sort name in the collection.
    client = _SortKeyClient(
        [
            {"Id": "garbage", "PremiereDate": "not-a-date", "Name": "zzz"},
            {"Id": "named", "Name": "aaa"},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["named", "garbage"]


def test_out_of_range_numeric_premiere_date_is_not_a_date():
    client = _SortKeyClient(
        [
            {"Id": "bogus", "PremiereDate": 99999, "Name": "zzz"},
            {"Id": "named", "Name": "aaa"},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["named", "bogus"]


def test_real_dates_still_outrank_titles():
    client = _SortKeyClient(
        [
            {"Id": "named", "Name": "aaa"},
            {"Id": "dated", "PremiereDate": "1999-05-01", "Name": "zzz"},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [item_id for item_id, _, _ in changes] == ["dated", "named"]
