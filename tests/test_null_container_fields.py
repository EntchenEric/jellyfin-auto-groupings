"""Regression tests for Jellyfin fields that arrive as JSON ``null``.

``dict.get(key, default)`` returns the *default* only when the key is absent.
Jellyfin routinely sends the key with a ``null`` value instead — ``Policy``,
``ProviderIds``, ``Tags``, ``Genres`` — so ``item.get("ProviderIds", {})``
evaluates to ``None`` and the chained ``.get(...)`` raises ``AttributeError``.
Each crash below aborted a whole sync run (or the whole library grouping pass)
instead of skipping the one unusable item, so they are pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jellyfin
import sync
from jellyfin_auto_groupings import JellyfinClient
from jellyfin_groupings import JellyfinClient as LegacyJellyfinClient
from jellyfin_groupings import group_movies_by_genre as legacy_group_movies_by_genre
from jellyfin_groupings import group_movies_by_tag as legacy_group_movies_by_tag


def _json_response(body):
    """Build a fake ``requests`` response whose ``.json()`` returns *body*."""
    response = MagicMock()
    response.json.return_value = body
    response.status_code = 200
    response.text = repr(body)
    response.raise_for_status.return_value = None
    return response


# ---------------------------------------------------------------------------
# ProviderIds: null
# ---------------------------------------------------------------------------


def test_provider_matching_skips_null_provider_ids():
    """An item with ``ProviderIds: null`` must not fail the whole group."""
    items = [
        {"Id": "1", "Name": "Unmatched", "ProviderIds": None},
        {"Id": "2", "Name": "Matched", "ProviderIds": {"Imdb": "tt123"}},
        {"Id": "3", "Name": "No key at all"},
    ]
    with patch.object(sync, "_fetch_full_library", return_value=(items, None, 200)):
        matched, error, status = sync._match_jellyfin_items_by_provider(
            ["tt123"],
            "Imdb",
            "imdb_list_order",
            "imdb_list_order",
            "http://jf",
            "key",
            "Test group",
        )

    assert error is None
    assert status == 200
    assert [item["Id"] for item in matched] == ["2"]


def test_provider_matching_rejects_non_dict_provider_ids():
    """A non-object ``ProviderIds`` value is skipped, not iterated."""
    items = [
        {"Id": "1", "ProviderIds": "tt123"},
        {"Id": "2", "ProviderIds": ["Imdb", "tt123"]},
        {"Id": "3", "ProviderIds": {"Imdb": "tt123"}},
    ]
    with patch.object(sync, "_fetch_full_library", return_value=(items, None, 200)):
        matched, error, _status = sync._match_jellyfin_items_by_provider(
            ["tt123"],
            "Imdb",
            "imdb_list_order",
            "imdb_list_order",
            "http://jf",
            "key",
            "Test group",
        )

    assert error is None
    assert [item["Id"] for item in matched] == ["3"]


# ---------------------------------------------------------------------------
# Policy: null
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: JellyfinClient("http://jf", "key"),
        lambda: LegacyJellyfinClient("http://jf", "key"),
    ],
    ids=["package-client", "legacy-client"],
)
def test_first_admin_user_id_tolerates_null_policy(client_factory):
    """A user with ``Policy: null`` is skipped instead of raising."""
    client = client_factory()
    users = [
        {"Id": "incomplete", "Policy": None},
        {"Id": "admin", "Policy": {"IsAdministrator": True}},
    ]
    with patch.object(client, "get_users", return_value=users):
        assert client.get_first_admin_user_id() == "admin"


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: JellyfinClient("http://jf", "key"),
        lambda: LegacyJellyfinClient("http://jf", "key"),
    ],
    ids=["package-client", "legacy-client"],
)
def test_first_admin_user_id_falls_back_to_first_user_with_null_policy(client_factory):
    """With no admins the first usable user is returned, ``null`` policy or not."""
    client = client_factory()
    users = [{"Id": "user1", "Policy": None}, {"Id": "user2", "Policy": {}}]
    with patch.object(client, "get_users", return_value=users):
        assert client.get_first_admin_user_id() == "user1"


# ---------------------------------------------------------------------------
# Tags / Genres: null and non-string entries (legacy module)
# ---------------------------------------------------------------------------


def test_legacy_group_movies_by_tag_skips_null_tags():
    movies = [
        {"Id": "1", "Tags": None},
        {"Id": "2", "Tags": ["Group:MCU", None, 42]},
        {"Id": "3", "Tags": ["Group:MCU"]},
    ]
    assert legacy_group_movies_by_tag(movies) == {"MCU": ["2", "3"]}


def test_legacy_group_movies_by_genre_skips_null_genres():
    movies = [
        {"Id": "1", "Genres": None},
        {"Id": "2", "Genres": ["Action", None, 7]},
        {"Id": "3", "Genres": ["Action"]},
    ]
    assert legacy_group_movies_by_genre(movies, min_count=2) == {"Action": ["2", "3"]}


# ---------------------------------------------------------------------------
# Jellyfin JSON bodies that are not the expected container type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [[1, 2, 3], None, "text", 42])
def test_fetch_jellyfin_items_rejects_non_object_body(body):
    """A non-object body becomes a Jellyfin error, not an ``AttributeError``."""
    with (
        patch("jellyfin.network.get", return_value=_json_response(body)),
        pytest.raises(RuntimeError, match="Expected a JSON object"),
    ):
        jellyfin.fetch_jellyfin_items("http://jf", "key")


def test_fetch_jellyfin_items_returns_items_list():
    body = {"Items": [{"Id": "1", "Name": "A"}]}
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        assert jellyfin.fetch_jellyfin_items("http://jf", "key") == body["Items"]


@pytest.mark.parametrize("body", [None, {"Name": "not a list"}, "text"])
def test_get_libraries_rejects_non_array_body(body):
    with (
        patch("jellyfin.network.get", return_value=_json_response(body)),
        pytest.raises(RuntimeError, match="Expected a JSON array"),
    ):
        jellyfin.get_libraries("http://jf", "key")


def test_get_libraries_skips_non_object_entries():
    body = [{"Name": "Movies"}, None, "junk", {"Name": "Shows"}]
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        assert jellyfin.get_libraries("http://jf", "key") == ["Movies", "Shows"]


def test_get_users_rejects_non_array_body():
    with (
        patch("jellyfin.network.get", return_value=_json_response(None)),
        pytest.raises(RuntimeError, match="Expected a JSON array"),
    ):
        jellyfin.get_users("http://jf", "key")


def test_get_users_skips_non_object_entries():
    body = [{"Id": "u1"}, None, 42]
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        assert jellyfin.get_users("http://jf", "key") == [{"Id": "u1"}]
