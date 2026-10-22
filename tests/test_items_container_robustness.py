"""Regression tests for the Jellyfin ``Items`` container shape.

``body.get("Items", [])`` looks defensive but is not: the default applies
only when the key is *absent*.  Jellyfin sends ``"Items": null`` for an empty
result set, and a proxy or an error page served with status 200 can put a
string or an object where the array belongs.  Every caller of these helpers
annotates its return as ``list[dict[str, Any]]``, so a leaked ``None`` used
to surface as ``TypeError`` from the caller's first ``len()`` or iteration,
and ``null`` placeholders inside the array surfaced as ``AttributeError``
from ``item.get(...)`` — both far from the request that produced them.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auto_group
import jellyfin
import main as root_main
from jellyfin_auto_groupings import JellyfinClient
from jellyfin_auto_groupings.api import JellyfinAPI
from jellyfin_groupings import JellyfinClient as LegacyJellyfinClient
from jellyfin_groupings.main import JellyfinGroupings as LegacyGroupings
from utils.helpers import items_from_body


def _json_response(body):
    """Build a fake ``requests`` response whose ``.json()`` returns *body*."""
    response = MagicMock()
    response.json.return_value = body
    response.status_code = 200
    response.text = repr(body)
    response.raise_for_status.return_value = None
    return response


# ---------------------------------------------------------------------------
# utils.helpers.items_from_body — the shared coercion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [None, [], "text", 42])
def test_items_from_body_rejects_non_object_body(body):
    assert items_from_body(body) == []


@pytest.mark.parametrize("body", [{}, {"Items": None}, {"Items": "junk"}])
def test_items_from_body_treats_missing_or_unusable_items_as_empty(body):
    assert items_from_body(body) == []


def test_items_from_body_keeps_only_object_entries():
    body = {"Items": [{"Id": "1"}, None, "junk", 7, {"Id": "2"}]}
    assert items_from_body(body) == [{"Id": "1"}, {"Id": "2"}]


# ---------------------------------------------------------------------------
# jellyfin.fetch_jellyfin_items / get_user_recent_items
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("items", [None])
def test_fetch_jellyfin_items_returns_empty_list_for_null_items(items):
    """``"Items": null`` is an empty result, not a leaked ``None``."""
    with patch("jellyfin.network.get", return_value=_json_response({"Items": items})):
        result = jellyfin.fetch_jellyfin_items("http://jf", "key")
    assert result == []
    # The contract is ``list``; ``len`` is what a caller does first.
    assert len(result) == 0


def test_fetch_jellyfin_items_returns_empty_list_when_items_key_absent():
    with patch("jellyfin.network.get", return_value=_json_response({})):
        assert jellyfin.fetch_jellyfin_items("http://jf", "key") == []


def test_fetch_jellyfin_items_drops_non_object_entries():
    body = {"Items": [{"Id": "1"}, None, "junk"]}
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        assert jellyfin.fetch_jellyfin_items("http://jf", "key") == [{"Id": "1"}]


@pytest.mark.parametrize("items", ["not-a-list", {"Id": "1"}, 42])
def test_fetch_jellyfin_items_rejects_non_list_items(items):
    with (
        patch("jellyfin.network.get", return_value=_json_response({"Items": items})),
        pytest.raises(RuntimeError, match="Expected 'Items' to be a JSON array"),
    ):
        jellyfin.fetch_jellyfin_items("http://jf", "key")


def test_fetch_jellyfin_items_output_survives_item_type_filter():
    """The downstream consumer that crashed on a ``null`` entry now works."""
    import sync

    body = {"Items": [{"Id": "1", "Type": "Movie"}, None, {"Id": "2"}]}
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        items = jellyfin.fetch_jellyfin_items("http://jf", "key")
    assert sync._filter_by_item_type(items, "movies") == [{"Id": "1", "Type": "Movie"}]


def test_get_user_recent_items_returns_empty_list_for_null_items():
    with patch("jellyfin.network.get", return_value=_json_response({"Items": None})):
        assert jellyfin.get_user_recent_items("http://jf", "key", "u1") == []


def test_paginated_walk_stops_quietly_on_null_items(caplog):
    """A ``null`` page ends the walk without a malformed-body warning."""
    import logging

    import jellyfin as jf

    with (
        patch("jellyfin.network.get", return_value=_json_response({"Items": None})),
        caplog.at_level(logging.WARNING, logger="jellyfin"),
    ):
        pages = list(jf._paginate_jellyfin("http://jf", "key", "Items"))

    assert pages == []
    assert "not a list" not in caplog.text


def test_paginated_walk_drops_non_object_entries():
    body = {"Items": [{"Id": "a"}, None, "junk"], "TotalRecordCount": 3}
    with patch("jellyfin.network.get", return_value=_json_response(body)):
        pages = list(jellyfin._paginate_jellyfin("http://jf", "key", "Items"))
    assert pages == [[{"Id": "a"}]]


# ---------------------------------------------------------------------------
# Package client
# ---------------------------------------------------------------------------


def _client_response(client, body):
    client.session.get = MagicMock(return_value=_json_response(body))


@pytest.mark.parametrize("items", [None, "junk", {"Id": "1"}, 42])
def test_client_get_all_items_returns_empty_list_for_unusable_items(items):
    client = JellyfinClient("http://jf", "key", user_id="u1")
    _client_response(client, {"Items": items})
    assert client.get_all_items(item_types=["Movie"]) == []


def test_client_get_all_items_drops_non_object_entries():
    client = JellyfinClient("http://jf", "key", user_id="u1")
    _client_response(client, {"Items": [{"Id": "1"}, None, "junk"]})
    assert client.get_all_items(item_types=["Movie"]) == [{"Id": "1"}]


def test_client_get_all_items_returns_empty_list_for_non_object_body():
    client = JellyfinClient("http://jf", "key", user_id="u1")
    _client_response(client, None)
    assert client.get_all_items(item_types=["Movie"]) == []


def test_client_get_items_returns_empty_list_for_null_items():
    client = JellyfinClient("http://jf", "key", user_id="u1")
    _client_response(client, {"Items": None})
    assert client.get_items() == []


@pytest.mark.parametrize("body", [None, {"Id": "u1"}, "junk"])
def test_client_get_users_returns_empty_list_for_non_array_body(body):
    client = JellyfinClient("http://jf", "key")
    _client_response(client, body)
    assert client.get_users() == []


def test_client_get_users_drops_non_object_entries():
    client = JellyfinClient("http://jf", "key")
    _client_response(client, [{"Id": "u1"}, None, "junk"])
    assert client.get_users() == [{"Id": "u1"}]


def test_client_admin_lookup_does_not_crash_on_null_users_body():
    client = JellyfinClient("http://jf", "key")
    _client_response(client, None)
    with pytest.raises(RuntimeError, match="No users found"):
        client.get_first_admin_user_id()


# ---------------------------------------------------------------------------
# Standalone api module
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    return JellyfinAPI("http://jf/", "key", timeout=5)


@pytest.mark.parametrize("items", [None, "junk", {"Id": "c1"}])
def test_api_get_collections_returns_empty_list_for_unusable_items(api_client, items):
    body = {"Items": items}
    with patch("requests.get", return_value=_json_response(body)):
        assert api_client.get_collections() == []


def test_api_get_collections_drops_non_object_entries(api_client):
    body = {"Items": [{"Id": "c1"}, None, "junk"]}
    with patch("requests.get", return_value=_json_response(body)):
        assert api_client.get_collections() == [{"Id": "c1"}]


def test_api_get_collection_items_returns_empty_list_for_null_items(api_client):
    with patch("requests.get", return_value=_json_response({"Items": None})):
        assert api_client.get_collection_items("c1") == []


# ---------------------------------------------------------------------------
# Legacy clients
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("items", [None, "junk", {"Id": "1"}])
def test_legacy_client_get_movies_returns_empty_list_for_unusable_items(items):
    client = LegacyJellyfinClient("http://jf", "key", user_id="u1")
    with patch.object(
        client.session, "get", return_value=_json_response({"Items": items})
    ):
        assert client.get_movies() == []


def test_legacy_client_get_collections_drops_non_object_entries():
    client = LegacyJellyfinClient("http://jf", "key")
    body = {"Items": [{"Id": "c1"}, None, "junk"]}
    with patch.object(client.session, "get", return_value=_json_response(body)):
        assert client.get_collections() == [{"Id": "c1"}]


@pytest.mark.parametrize("body", [None, {"Id": "u1"}, "junk"])
def test_legacy_client_get_users_returns_empty_list_for_non_array_body(body):
    client = LegacyJellyfinClient("http://jf", "key")
    with patch.object(client.session, "get", return_value=_json_response(body)):
        assert client.get_users() == []


def test_legacy_groupings_get_collections_returns_empty_list_for_null_items():
    client = LegacyGroupings("http://jf", "key")
    with patch(
        "jellyfin_groupings.main.requests.get",
        return_value=_json_response({"Items": None}),
    ):
        assert client.get_collections() == []


def test_root_main_get_collections_returns_empty_list_for_null_items():
    client = root_main.JellyfinGroupings("http://jf", "key")
    with patch.object(
        client.session, "get", return_value=_json_response({"Items": None})
    ):
        assert client.get_collections() == []


# ---------------------------------------------------------------------------
# auto_group.py helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("items", [None, "junk"])
def test_auto_group_get_libraries_returns_empty_list_for_unusable_items(items):
    with patch(
        "auto_group.requests.get", return_value=_json_response({"Items": items})
    ):
        assert auto_group.get_libraries("http://jf", "key") == []


def test_auto_group_get_library_items_drops_non_object_entries():
    body = {"Items": [{"Id": "1", "Name": "A"}, None, "junk"]}
    with patch("auto_group.requests.get", return_value=_json_response(body)):
        assert auto_group.get_library_items("http://jf", "key", "lib-1") == [
            {"Id": "1", "Name": "A"}
        ]
