"""Regression tests for item-ID integrity when building collections.

Two independent defects produced collections Jellyfin could not create:

* ``JellyfinClient.create_collection`` wrapped a missing response body with
  ``{"Id": str(res)}``, so an empty-body success became ``{"Id": "None"}``.
* The prefix-grouping paths collected ``item.get("Id", "")``, so an item
  without an ``Id`` contributed an empty string and Jellyfin rejected the
  whole ``Ids`` parameter instead of just skipping that item.
"""

from unittest.mock import MagicMock, patch

import pytest

from jellyfin_auto_groupings.client import (
    JellyfinClient,
    create_groupings,
    process_groupings,
)


def _client() -> JellyfinClient:
    return JellyfinClient("http://localhost:8096", "key", user_id="user-1")


def _empty_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = ""
    return resp


def test_create_collection_empty_body_does_not_fabricate_none_id():
    client = _client()
    with patch.object(client.session, "post", return_value=_empty_response()):
        assert client.create_collection("New", ["1"]) == {}


def test_create_collection_plain_text_body_still_reports_id():
    client = _client()
    resp = _empty_response()
    resp.text = "abc123"
    resp.json.side_effect = ValueError("plain text")
    with patch.object(client.session, "post", return_value=resp):
        assert client.create_collection("New", ["1"]) == {"Id": "abc123"}


def test_process_groupings_mode2_skips_items_without_id():
    client = _client()
    items = [
        {"Name": "Toy Story"},
        {"Id": "2", "Name": "Toy Story 2"},
        {"Id": "3", "Name": "Toy Story 3"},
    ]
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(
            client, "create_collection", return_value={"Id": "c-new"}
        ) as mock_create,
    ):
        process_groupings(client, items=items, dry_run=False)
    # The nameless-ID item is dropped; the remaining two form the group.
    mock_create.assert_called_once_with("Toy", ["2", "3"])


def test_process_groupings_mode2_does_not_count_missing_ids():
    """An item without an Id must not inflate the group past the size check."""
    client = _client()
    items = [
        {"Name": "Toy Story"},
        {"Id": "b", "Name": "Toy Story 2"},
    ]
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(client, "create_collection") as mock_create,
    ):
        process_groupings(client, items=items, dry_run=False)
    # Only one usable ID remains, so no collection is created.
    mock_create.assert_not_called()


def test_create_groupings_mode2_skips_items_without_id():
    client = MagicMock()
    client.create_collection.return_value = {"Id": "c1"}
    items = [
        {"Name": "Harry Potter"},
        {"Id": "b", "Name": "Harry Potter 2"},
        {"Id": "c", "Name": "Harry Potter 3"},
    ]
    create_groupings(client, items=items, min_group_size=2)
    client.create_collection.assert_called_once_with("Harry", ["b", "c"])


def test_create_groupings_mode2_empty_ids_returns_no_collections():
    client = MagicMock()
    items = [{"Name": "Harry Potter"}, {"Name": "Harry Potter 2"}]
    assert create_groupings(client, items=items, min_group_size=2) == []
    client.create_collection.assert_not_called()


@pytest.mark.parametrize("bad_id", [None, 0, "", False])
def test_process_groupings_mode2_treats_falsy_ids_as_missing(bad_id):
    client = _client()
    items = [
        {"Id": bad_id, "Name": "Toy Story"},
        {"Id": "2", "Name": "Toy Story 2"},
    ]
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(client, "create_collection") as mock_create,
    ):
        process_groupings(client, items=items, dry_run=False)
    mock_create.assert_not_called()
