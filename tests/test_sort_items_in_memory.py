"""In-memory sorting of external-list items must not depend on response shape.

``_sort_items_in_memory`` orders items that came from an external list (IMDb,
Trakt, ...) because Jellyfin cannot sort those server-side.  The item dicts
come straight from a Jellyfin API response, so the same field may be a float,
a numeric string, ``None``, or absent.  Three defects are pinned here:

* ``sort_order="Random"`` resolved to ``SORT_MAP["Random"]`` and then sorted on
  an item field called ``Random``, which no item has — every item took the
  "missing" branch and the input order came back unchanged. The UI offers
  "Random" as a sort option, so it silently did nothing.
* ``sorted()`` on mixed values raised ``TypeError: '<' not supported between
  instances of 'float' and 'str'``, aborting the whole group when one title had
  a rating and another had the same rating as a string.
* the second key of ``"ProductionYear,SortName"`` was dropped, so ties fell
  back to Jellyfin's page order instead of name order.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync import _sort_items_in_memory


def _names(items):
    return [item["Name"] for item in items]


# ---------------------------------------------------------------------------
# Unknown / no-op sort orders
# ---------------------------------------------------------------------------


def test_unknown_sort_order_returns_items_unchanged():
    items = [{"Name": "b"}, {"Name": "a"}]
    assert _sort_items_in_memory(items, "NotASortOrder") is items


# ---------------------------------------------------------------------------
# Random
# ---------------------------------------------------------------------------


def test_random_returns_every_item_exactly_once():
    items = [{"Name": f"M{i}"} for i in range(40)]

    result = _sort_items_in_memory(items, "Random")

    assert len(result) == len(items)
    assert sorted(_names(result)) == sorted(_names(items))
    assert result is not items


def test_random_does_not_mutate_the_input_list():
    items = [{"Name": f"M{i}"} for i in range(40)]
    original = list(items)

    _sort_items_in_memory(items, "Random")

    assert items == original


def test_random_actually_reorders_a_large_list():
    """A 60-item shuffle landing in the original order is ~1 in 60!."""
    items = [{"Name": f"M{i}"} for i in range(60)]

    assert _names(_sort_items_in_memory(items, "Random")) != _names(items)


# ---------------------------------------------------------------------------
# Mixed value types
# ---------------------------------------------------------------------------


def test_mixed_numeric_types_do_not_raise():
    items = [
        {"Name": "float", "CommunityRating": 8.1},
        {"Name": "string", "CommunityRating": "7.5"},
        {"Name": "missing", "CommunityRating": None},
    ]

    result = _sort_items_in_memory(items, "CommunityRating")

    assert _names(result) == ["float", "string", "missing"]


def test_numeric_strings_sort_numerically_not_lexically():
    items = [
        {"Name": "nine", "CommunityRating": 9.0},
        {"Name": "ten-str", "CommunityRating": "10.0"},
    ]

    assert _names(_sort_items_in_memory(items, "CommunityRating")) == [
        "ten-str",
        "nine",
    ]


def test_year_values_mixing_int_float_and_string_agree():
    items = [
        {"Name": "new", "ProductionYear": "2010.0"},
        {"Name": "old", "ProductionYear": 1999},
        {"Name": "mid", "ProductionYear": 2005.0},
    ]

    asc = _sort_items_in_memory(items, "ProductionYearAsc")
    desc = _sort_items_in_memory(items, "ProductionYear")

    assert _names(asc) == ["old", "mid", "new"]
    assert _names(desc) == ["new", "mid", "old"]


def test_booleans_are_not_treated_as_numbers():
    """``bool`` is an ``int`` subclass, so a stray ``True`` would sort as 1."""
    items = [
        {"Name": "flag", "CommunityRating": True},
        {"Name": "text", "CommunityRating": "unrated"},
        {"Name": "rated", "CommunityRating": 5.0},
    ]

    result = _sort_items_in_memory(items, "CommunityRating")

    # Numeric rating first, then the non-numeric group (flag before text).
    assert _names(result)[0] == "rated"
    assert set(_names(result)[1:]) == {"flag", "text"}


def test_empty_string_is_treated_as_missing():
    items = [
        {"Name": "blank", "SortName": "   "},
        {"Name": "real", "SortName": "Zulu"},
    ]

    assert _names(_sort_items_in_memory(items, "SortName")) == ["real", "blank"]


# ---------------------------------------------------------------------------
# Direction handling and the "missing last" rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["CommunityRating", "SortName", "ProductionYear"])
def test_items_missing_the_field_sort_last_in_both_directions(order):
    items = [
        {"Name": "missing"},
        {
            "Name": "present",
            "CommunityRating": 5,
            "SortName": "Name",
            "ProductionYear": 2000,
        },
    ]

    assert _names(_sort_items_in_memory(items, order))[1] == "missing"


# ---------------------------------------------------------------------------
# Case-insensitive text ordering
# ---------------------------------------------------------------------------


def test_text_sort_is_case_insensitive():
    items = [
        {"Name": "z", "SortName": "Zebra"},
        {"Name": "a", "SortName": "apple"},
        {"Name": "b", "SortName": "Banana"},
    ]

    assert _names(_sort_items_in_memory(items, "SortName")) == ["a", "b", "z"]


# ---------------------------------------------------------------------------
# Secondary sort key
# ---------------------------------------------------------------------------


def test_secondary_sort_name_breaks_year_ties():
    items = [
        {"Name": "bravo", "ProductionYear": 2001, "SortName": "Bravo"},
        {"Name": "alpha", "ProductionYear": 2001, "SortName": "Alpha"},
        {"Name": "charlie", "ProductionYear": 2010, "SortName": "Charlie"},
    ]

    result = _sort_items_in_memory(items, "ProductionYearAsc")

    # Year ascending, then name ascending inside a year.
    assert _names(result) == ["alpha", "bravo", "charlie"]


def test_secondary_key_is_ascending_even_when_primary_is_descending():
    items = [
        {"Name": "bravo", "ProductionYear": 2001, "SortName": "Bravo"},
        {"Name": "alpha", "ProductionYear": 2001, "SortName": "Alpha"},
        {"Name": "charlie", "ProductionYear": 2010, "SortName": "Charlie"},
    ]

    result = _sort_items_in_memory(items, "ProductionYear")

    # Newest year first, but names still ascending within 2001.
    assert _names(result) == ["charlie", "alpha", "bravo"]


def test_sort_does_not_mutate_input_order():
    items = [{"SortName": "B"}, {"SortName": "A"}]

    _sort_items_in_memory(items, "SortName")

    assert [item["SortName"] for item in items] == ["B", "A"]
