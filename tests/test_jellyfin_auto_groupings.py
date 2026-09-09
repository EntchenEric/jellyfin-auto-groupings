import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jellyfin_auto_groupings import (
    JellyfinClient,
    group_items_by_pattern,
    sync_groupings,
)


def test_jellyfin_client_initialization():
    client = JellyfinClient("http://localhost:8096/", "testkey", user_id="user123")
    assert client.server_url == "http://localhost:8096"
    assert client.headers["X-Emby-Token"] == "testkey"
    assert client.user_id == "user123"


def test_jellyfin_client_get_users():
    client = JellyfinClient("http://localhost:8096", "testkey")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [{"Id": "u1", "Policy": {"IsAdministrator": True}}]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        users = client.get_users()
        assert len(users) == 1
        assert users[0]["Id"] == "u1"
        mock_get.assert_called_once_with(
            "http://localhost:8096/Users",
            headers=client.headers,
            params=None,
            timeout=30,
        )


def test_jellyfin_client_get_first_admin_user_id():
    client = JellyfinClient("http://localhost:8096", "testkey")
    mock_users = [
        {"Id": "user1", "Policy": {"IsAdministrator": False}},
        {"Id": "admin1", "Policy": {"IsAdministrator": True}},
    ]
    with patch.object(client, "get_users", return_value=mock_users):
        assert client.get_first_admin_user_id() == "admin1"

    mock_non_admin = [{"Id": "user1", "Policy": {"IsAdministrator": False}}]
    with patch.object(client, "get_users", return_value=mock_non_admin):
        assert client.get_first_admin_user_id() == "user1"

    with patch.object(client, "get_users", return_value=[]):
        with pytest.raises(RuntimeError, match="No users found"):
            client.get_first_admin_user_id()


def test_jellyfin_client_get_all_items():
    client = JellyfinClient("http://localhost:8096", "testkey", user_id="user123")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Items": [{"Id": "item1", "Name": "Movie 1"}]}

    with patch("requests.get", return_value=mock_resp):
        items = client.get_all_items(item_types=["Movie"], parent_id="folder1")
        assert len(items) == 1
        assert items[0]["Id"] == "item1"


def test_jellyfin_client_post_non_json_text_and_empty():
    client = JellyfinClient("http://localhost:8096", "testkey")

    # Test non-JSON plain text response
    mock_post_text = MagicMock()
    mock_post_text.raise_for_status.return_value = None
    mock_post_text.text = "OK"
    mock_post_text.json.side_effect = ValueError("Not JSON")
    with patch("requests.post", return_value=mock_post_text):
        res = client._post("/test")
        assert res == "OK"

    # Test empty text response returning None
    mock_post_empty = MagicMock()
    mock_post_empty.raise_for_status.return_value = None
    mock_post_empty.text = ""
    with patch("requests.post", return_value=mock_post_empty):
        res = client._post("/test")
        assert res is None


def test_jellyfin_client_create_add_remove_collection():
    client = JellyfinClient("http://localhost:8096", "testkey")

    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status.return_value = None
    mock_post_resp.text = '{"Id": "col1"}'
    mock_post_resp.json.return_value = {"Id": "col1"}

    with patch("requests.post", return_value=mock_post_resp) as mock_post:
        coll = client.create_collection("Test Collection", ["1", "2"])
        assert coll == {"Id": "col1"}

        client.add_to_collection("col1", ["3"])
        assert mock_post.call_count == 2

    mock_del_resp = MagicMock()
    mock_del_resp.raise_for_status.return_value = None
    with patch("requests.delete", return_value=mock_del_resp) as mock_del:
        client.remove_from_collection("col1", ["1"])
        assert mock_del.call_count == 1


def test_group_items_by_pattern():
    items = [
        {"Id": "1", "Name": "Toy Story (1995)"},
        {"Id": "2", "Name": "Toy Story 2 (1999)"},
        {"Id": "3", "Name": "Toy Story 3 (2010)"},
        {"Id": "4", "Name": "Standalone Movie"},
        {"Id": "5", "Genres": ["Action", "Adventure"]},
        {"Id": "6", "Name": 12345},  # Non-string attribute test
        {"Id": "7", "Name": "Matrix"},
    ]
    pattern = r"^(Toy Story)"
    groups = group_items_by_pattern(items, pattern)
    assert "Toy Story" in groups
    assert len(groups["Toy Story"]) == 3
    assert "Standalone Movie" not in groups

    # Test regex without capture group (full match)
    full_match_groups = group_items_by_pattern(items, r"Matrix")
    assert "Matrix" in full_match_groups
    assert len(full_match_groups["Matrix"]) == 1

    # Test attribute matching with list
    genre_groups = group_items_by_pattern(items, r"^(Action)", attribute="Genres")
    assert "Action" in genre_groups
    assert len(genre_groups["Action"]) == 1


def test_sync_groupings_dry_run_and_real():
    mock_client = MagicMock()
    mock_client.get_all_items.return_value = [{"Id": "col_existing", "Name": "Existing Coll"}]
    groups = {
        "Existing Coll": [{"Id": "1"}, {"Id": "2"}],
        "New Coll": [{"Id": "3"}, {"Id": "4"}],
        "Small Coll": [{"Id": "5"}],
    }

    # Test dry run and min_items filter
    summary = sync_groupings(mock_client, groups, dry_run=True, min_items=2)
    assert "Existing Coll" in summary
    assert "New Coll" in summary
    assert "Small Coll" not in summary
    assert not mock_client.add_to_collection.called
    assert not mock_client.create_collection.called

    # Test non dry-run execution
    sync_groupings(mock_client, groups, dry_run=False, min_items=2)
    mock_client.add_to_collection.assert_called_once_with("col_existing", ["1", "2"])
    mock_client.create_collection.assert_called_once_with("New Coll", ["3", "4"])
