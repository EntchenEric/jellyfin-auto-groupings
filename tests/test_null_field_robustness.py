"""Regression tests for ``null``/malformed metadata coming from Jellyfin.

Jellyfin serialises empty tag and genre lists as ``null`` and leaves
``PremiereDate`` unset for undated items. Every grouping helper must tolerate
that instead of raising, because one malformed item would otherwise abort a
whole library sync.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jellyfin_auto_groupings import JellyfinClient
from jellyfin_auto_groupings.client import (
    get_movies_by_query,
    group_movies_by_genre,
    group_movies_by_tag,
    process_groupings,
)
from jellyfin_auto_groupings.rules import (
    group_by_decade,
    group_by_genre,
    group_by_studio,
    group_by_tag,
    parse_grouping_rules,
)


def test_get_movies_by_query_tolerates_null_and_non_string_tags():
    items = [
        {"Id": "1", "Name": "Sci-Fi Movie", "Tags": None},
        {"Id": "2", "Name": "Other", "Tags": [None, 42]},
        {"Id": "3", "Name": "Tagged", "Tags": ["Classic"]},
    ]
    assert get_movies_by_query(items, "sci-fi") == [items[0]]
    # A null tag list must not match a required tag.
    assert get_movies_by_query(items, "movie", tags=["classic"]) == []
    assert get_movies_by_query(items, "tagged", tags=["classic"]) == [items[2]]
    assert get_movies_by_query(items, "other") == [items[1]]


def test_group_movies_by_tag_skips_null_and_non_string_tags():
    items = [
        {"Id": "1", "Name": "A", "Tags": None},
        {"Id": "2", "Name": "B", "Tags": [None, 7, ""]},
        {"Id": "3", "Name": "C", "Tags": ["Hero"]},
        {"Id": "4", "Name": "D", "Tags": ["Hero"]},
    ]
    groups = group_movies_by_tag(items, min_group_size=2)
    assert groups == {"Hero": [items[2], items[3]]}


def test_group_movies_by_genre_skips_null_and_non_string_genres():
    items = [
        {"Id": "1", "Name": "A", "Genres": None},
        {"Id": "2", "Name": "B", "Genres": [None, 7]},
        {"Id": "3", "Name": "C", "Genres": ["Action"]},
        {"Id": "4", "Name": "D", "Genres": ["Action"]},
    ]
    groups = group_movies_by_genre(items, min_group_size=2)
    assert groups == {"Action": [items[2], items[3]]}


def test_rules_grouping_helpers_tolerate_null_lists():
    items = [
        {"Id": "1", "Name": "A", "Tags": None, "Genres": None, "Studios": None},
        {"Id": "2", "Name": "B", "Tags": [None], "Genres": [None], "Studios": [None]},
        {"Id": "3", "Name": "C", "Tags": ["t"], "Genres": ["g"], "Studios": ["s"]},
        {"Id": "4", "Name": "D", "Tags": ["t"], "Genres": ["g"], "Studios": ["s"]},
    ]
    assert group_by_tag(items, min_items=2) == {"t": [items[2], items[3]]}
    assert group_by_genre(items, min_items=2) == {"g": [items[2], items[3]]}
    assert group_by_studio(items, min_items=2) == {"s": [items[2], items[3]]}


def test_group_by_studio_ignores_empty_and_non_string_names():
    items = [
        {"Id": "1", "Studios": [{"Name": ""}, {"Name": None}, {}]},
        {"Id": "2", "Studios": [{"Name": "Pixar"}]},
        {"Id": "3", "Studios": [{"Name": "Pixar"}]},
    ]
    assert group_by_studio(items, min_items=2) == {"Pixar": [items[1], items[2]]}


def test_parse_grouping_rules_rejects_non_dict_collections():
    assert parse_grouping_rules({"collections": None}) == {}
    assert parse_grouping_rules({"collections": ["a"]}) == {}
    assert parse_grouping_rules({}) == {}


def test_group_by_decade_ignores_boolean_production_year():
    # ``True`` is an ``int`` subclass but is not a release year.
    groups = group_by_decade([{"Id": "1", "ProductionYear": True}])
    assert groups == {}


def test_process_groupings_sorts_items_with_null_premiere_date():
    class Client:
        def get_collections(self):
            return [{"Id": "c1", "Name": "Saga"}]

        def get_collection_items(self, collection_id):
            return [
                {"Id": "m1", "Name": "Undated", "PremiereDate": None},
                {"Id": "m2", "Name": "Newer", "PremiereDate": "2000-01-01"},
            ]

    changes = process_groupings(Client(), dry_run=True)
    assert changes == [("m1", "Undated", "Saga 01"), ("m2", "Newer", "Saga 02")]


def test_sanitize_filename_rejects_names_without_alphanumerics():
    from utils.helpers import sanitize_filename

    assert sanitize_filename("___") == "unnamed"
    assert sanitize_filename("/*?") == "unnamed"
    assert sanitize_filename("...") == "unnamed"


def test_sanitize_filename_replaces_nul_and_control_characters():
    """A NUL byte must never survive into a path.

    ``sanitize_filename`` promises a path segment that is safe on disk, but
    it passed NUL through: every filesystem call on the result raised
    ``ValueError: embedded null byte``, from a name the caller believed was
    already clean.
    """
    from utils.helpers import sanitize_filename

    assert sanitize_filename("a\x00b.mkv") == "a_b.mkv"
    assert sanitize_filename("a\tb.mkv") == "a_b.mkv"
    assert sanitize_filename("a\x7fb") == "a_b"
    assert sanitize_filename("\x00") == "unnamed"


def test_process_groupings_skips_collections_without_id():
    class Client:
        def get_collections(self):
            return [{"Name": "NoId"}, {"Id": "c1", "Name": "Saga"}]

        def get_collection_items(self, collection_id):
            assert collection_id == "c1"
            return [{"Id": "m1", "Name": "A", "PremiereDate": "1999-01-01"}]

    assert process_groupings(Client(), dry_run=True) == [("m1", "A", "Saga 01")]


def test_update_item_sort_name_raises_on_http_error():
    client = JellyfinClient("http://localhost:8096", "key")
    response = requests.Response()
    response.status_code = 404
    with (
        patch.object(client.session, "post", return_value=response) as mock_post,
        pytest.raises(requests.HTTPError),
    ):
        client.update_item_sort_name("missing", "Name 01")
    mock_post.assert_called_once()


def test_group_items_by_pattern_tolerates_non_participating_capture_group():
    """A regex whose alternation leaves a group unset must not abort grouping.

    Patterns like ``^(\\d{4})|(.*)`` return ``None`` for the branch that did
    not match; the unused group used to be ``.strip()``-ed and crashed the
    whole sync with ``AttributeError``.
    """
    from jellyfin_auto_groupings.client import group_items_by_pattern

    items = [{"Id": "1", "Name": "1994"}, {"Id": "2", "Name": "Heat"}]
    groups = group_items_by_pattern(items, r"^(?:(\d{4})|(.*))")
    assert groups == {"1994": [items[0]], "Heat": [items[1]]}


def test_group_items_by_pattern_skips_when_all_capture_groups_unset():
    """A match with only empty optional groups falls back to the full match."""
    from jellyfin_auto_groupings.client import group_items_by_pattern

    items = [{"Id": "1", "Name": "abc"}]
    groups = group_items_by_pattern(items, r"^(?:(\d+))?(\w+)")
    assert groups == {"abc": items}
