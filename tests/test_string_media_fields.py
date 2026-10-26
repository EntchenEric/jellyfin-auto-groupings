"""Bare-string ``Tags``/``Genres``/``Studios`` must count as one value.

Jellyfin normally serialises these fields as arrays, but a hand-edited
``config.json``, a proxy, or an older server can put a bare string there.
Iterating that string yields one character at a time, so ``"action"`` used to
become six groups named ``a``, ``c``, ``t``, ``i``, ``o``, ``n`` — and a studio
rule could never match at all.
"""

import pytest

from jellyfin_auto_groupings.client import (
    get_movies_by_query,
    group_movies_by_genre,
    group_movies_by_tag,
)
from jellyfin_auto_groupings.rules import (
    group_by_genre,
    group_by_studio,
    group_by_tag,
)
from sync import _match_condition
from utils.helpers import parse_media_tags, string_list, studio_names

# ---------------------------------------------------------------------------
# string_list
# ---------------------------------------------------------------------------


def test_string_list_treats_bare_string_as_one_value():
    assert string_list("action") == ["action"]


def test_string_list_keeps_sequence_order_and_drops_non_strings():
    assert string_list(["b", 1, None, "a"]) == ["b", "a"]


@pytest.mark.parametrize("value", [None, 0, 5, 1.5, True, {"a": 1}, b"x"])
def test_string_list_rejects_unusable_shapes(value):
    assert string_list(value) == []


@pytest.mark.parametrize("value", [("a", "b"), ["a", "b"], {"a"}, frozenset({"a"})])
def test_string_list_accepts_any_sequence_container(value):
    assert "a" in string_list(value)


def test_parse_media_tags_treats_bare_string_as_one_tag():
    assert parse_media_tags("Action") == ["Action"]


@pytest.mark.parametrize("value", [None, 5, {"a": 1}])
def test_parse_media_tags_tolerates_unusable_input(value):
    assert parse_media_tags(value) == []


# ---------------------------------------------------------------------------
# Bare string must not fan out into one group per character
# ---------------------------------------------------------------------------


def test_group_movies_by_tag_does_not_split_bare_string():
    movies = [
        {"Id": "1", "Tags": "action"},
        {"Id": "2", "Tags": "action"},
    ]
    assert group_movies_by_tag(movies, min_group_size=1) == {"action": movies}


def test_group_movies_by_genre_does_not_split_bare_string():
    movies = [
        {"Id": "1", "Genres": "Action"},
        {"Id": "2", "Genres": "Action"},
    ]
    assert group_movies_by_genre(movies, min_group_size=1) == {"Action": movies}


def test_rules_group_by_tag_does_not_split_bare_string():
    items = [{"Name": "a", "Tags": "action"}]
    assert group_by_tag(items, min_items=1) == {"action": items}


def test_rules_group_by_genre_does_not_split_bare_string():
    items = [{"Name": "a", "Genres": "Action"}]
    assert group_by_genre(items, min_items=1) == {"Action": items}


def test_all_letter_groups_are_gone():
    """The regression produced single-letter group keys; none may survive."""
    items = [{"Name": "a", "Tags": "action", "Genres": "Action"}]
    keys = set(group_by_tag(items, min_items=1)) | set(
        group_by_genre(items, min_items=1)
    )
    assert keys == {"action", "Action"}


# ---------------------------------------------------------------------------
# Studios: bare string and single object
# ---------------------------------------------------------------------------


def test_group_by_studio_accepts_bare_string():
    items = [{"Name": "a", "Studios": "Marvel"}]
    assert group_by_studio(items, min_items=1) == {"Marvel": items}


def test_group_by_studio_accepts_single_object():
    items = [{"Name": "a", "Studios": {"Name": "Marvel"}}]
    assert group_by_studio(items, min_items=1) == {"Marvel": items}


def test_group_by_studio_accepts_list_of_objects():
    items = [{"Name": "a", "Studios": [{"Name": "Marvel"}, {"Name": "Pixar"}]}]
    grouped = group_by_studio(items, min_items=1)
    assert set(grouped) == {"Marvel", "Pixar"}


@pytest.mark.parametrize("value", [None, [], {}, 5, [None], [{"Name": None}]])
def test_group_by_studio_ignores_unusable_studios(value):
    assert group_by_studio([{"Name": "a", "Studios": value}], min_items=1) == {}


def test_studio_names_helper_matches_group_by_studio():
    item = {"Studios": ["Marvel", {"Name": "Pixar"}, None, {"Name": ""}]}
    assert studio_names(item["Studios"]) == ["Marvel", "Pixar"]


def test_studio_names_helper_accepts_bare_string():
    assert studio_names("Marvel") == ["Marvel"]


# ---------------------------------------------------------------------------
# Rule matching in sync.py uses the same normalisation
# ---------------------------------------------------------------------------


def test_match_condition_matches_bare_string_fields():
    item = {"Name": "x", "Tags": "action", "Genres": "Action", "Studios": "Marvel"}
    assert _match_condition(item, "tag", "action")
    assert _match_condition(item, "genre", "action")
    assert _match_condition(item, "studio", "marvel")


def test_match_condition_rejects_single_letters():
    """A per-character match would accept "a" for the tag "action"."""
    item = {"Name": "x", "Tags": "action", "Genres": "Action", "Studios": "Marvel"}
    assert not _match_condition(item, "tag", "a")
    assert not _match_condition(item, "genre", "a")
    assert not _match_condition(item, "studio", "a")


def test_match_condition_handles_null_and_non_string_entries():
    item = {"Tags": None, "Genres": [None, 5], "Studios": None}
    assert not _match_condition(item, "tag", "action")
    assert not _match_condition(item, "genre", "action")
    assert not _match_condition(item, "studio", "marvel")


def test_get_movies_by_query_matches_bare_string_tag():
    items = [{"Name": "Heat", "Tags": "heist"}]
    assert get_movies_by_query(items, "heat", tags=["heist"]) == items
