import pytest
from unittest.mock import MagicMock, patch
import requests
from jellyfin_auto_groupings import JellyfinClient, group_items_by_pattern, sync_groupings


@pytest.fixture
def mock_client():
    return JellyfinClient(server_url="http://localhost:8096", api_key="testkey", user_id="user123")


def test_client_init(mock_client):
    assert mock_client.server_url == "http://localhost:8096"
    assert mock_client.api_key == "testkey"
    assert mock_client.user_id == "user123"
    assert mock_client.headers["X-Emby-Token"] == "testkey"


@patch("requests.get")
def test_get_users(mock_get, mock_client):
    mock_get.return_value.json.return_value = [{"Id": "u1", "Name": "Admin"}]
    mock_get.return_value.raise_for_status = MagicMock()
    users = mock_client.get_users()
    assert len(users) == 1
    assert users[0]["Name"] == "Admin"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Users",
        headers=mock_client.headers,
        params=None,
        timeout=30,
    )


@patch("requests.get")
def test_get_first_admin_user_id(mock_get, mock_client):
    mock_get.return_value.json.return_value = [
        {"Id": "u1", "Name": "User", "Policy": {"IsAdministrator": False}},
        {"Id": "u2", "Name": "Admin", "Policy": {"IsAdministrator": True}},
    ]
    mock_get.return_value.raise_for_status = MagicMock()
    admin_id = mock_client.get_first_admin_user_id()
    assert admin_id == "u2"


@patch("requests.get")
def test_get_first_admin_user_id_fallback(mock_get, mock_client):
    mock_get.return_value.json.return_value = [
        {"Id": "u1", "Name": "User", "Policy": {"IsAdministrator": False}},
    ]
    mock_get.return_value.raise_for_status = MagicMock()
    admin_id = mock_client.get_first_admin_user_id()
    assert admin_id == "u1"


@patch("requests.get")
def test_get_first_admin_user_id_empty_raises(mock_get, mock_client):
    mock_get.return_value.json.return_value = []
    mock_get.return_value.raise_for_status = MagicMock()
    with pytest.raises(RuntimeError, match="No users found"):
        mock_client.get_first_admin_user_id()


@patch("requests.get")
def test_get_all_items(mock_get, mock_client):
    mock_get.return_value.json.return_value = {"Items": [{"Id": "1", "Name": "Item 1"}]}
    mock_get.return_value.raise_for_status = MagicMock()
    items = mock_client.get_all_items(item_types=["Movie"], parent_id="p1")
    assert len(items) == 1
    assert items[0]["Name"] == "Item 1"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Users/user123/Items",
        headers=mock_client.headers,
        params={
            "Recursive": "true",
            "Fields": "Genres,Tags,CollectionFolder,ProviderIds",
            "IncludeItemTypes": "Movie",
            "ParentId": "p1",
        },
        timeout=30,
    )


@patch("requests.post")
def test_create_collection(mock_post, mock_client):
    mock_post.return_value.text = '{"Id": "col1"}'
    mock_post.return_value.json.return_value = {"Id": "col1"}
    mock_post.return_value.raise_for_status = MagicMock()
    res = mock_client.create_collection("Marvel", ["1", "2"])
    assert res == {"Id": "col1"}
    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections",
        headers=mock_client.headers,
        params={"Name": "Marvel", "Ids": "1,2"},
        json=None,
        timeout=30,
    )


@patch("requests.post")
def test_add_to_collection(mock_post, mock_client):
    mock_post.return_value.text = ""
    mock_post.return_value.raise_for_status = MagicMock()
    mock_client.add_to_collection("col1", ["1", "2"])
    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections/col1/Items",
        headers=mock_client.headers,
        params={"Ids": "1,2"},
        json=None,
        timeout=30,
    )


@patch("requests.delete")
def test_remove_from_collection(mock_delete, mock_client):
    mock_delete.return_value.raise_for_status = MagicMock()
    mock_client.remove_from_collection("col1", ["1", "2"])
    mock_delete.assert_called_once_with(
        "http://localhost:8096/Collections/col1/Items",
        headers=mock_client.headers,
        params={"Ids": "1,2"},
        timeout=30,
    )


def test_group_items_by_pattern_regex_groups():
    items = [
        {"Id": "1", "Name": "Star Wars: Episode IV - A New Hope"},
        {"Id": "2", "Name": "Star Wars: Episode V - The Empire Strikes Back"},
        {"Id": "3", "Name": "Star Trek: The Motion Picture"},
    ]
    pattern = r"^(Star [^:]+):"
    groups = group_items_by_pattern(items, pattern)
    assert "Star Wars" in groups
    assert "Star Trek" in groups
    assert len(groups["Star Wars"]) == 2
    assert len(groups["Star Trek"]) == 1


def test_group_items_by_pattern_list_attribute():
    items = [
        {"Id": "1", "Name": "Movie 1", "Genres": ["Action", "Adventure"]},
        {"Id": "2", "Name": "Movie 2", "Genres": ["Comedy"]},
    ]
    pattern = r"^(Act.*)"
    groups = group_items_by_pattern(items, pattern, attribute="Genres")
    assert "Action" in groups
    assert len(groups["Action"]) == 1


def test_group_items_by_pattern_no_match():
    items = [{"Id": "1", "Name": "Movie 1"}]
    groups = group_items_by_pattern(items, r"NonExistentPattern")
    assert groups == {}


@patch.object(JellyfinClient, "get_all_items")
@patch.object(JellyfinClient, "create_collection")
@patch.object(JellyfinClient, "add_to_collection")
def test_sync_groupings_dry_run(mock_add, mock_create, mock_get_items, mock_client):
    mock_get_items.return_value = [{"Id": "col1", "Name": "Star Wars"}]
    groups = {
        "Star Wars": [{"Id": "1"}, {"Id": "2"}],
        "Star Trek": [{"Id": "3"}],
    }
    summary = sync_groupings(mock_client, groups, dry_run=True, min_items=1)
    assert "Star Wars" in summary
    assert "Star Trek" in summary
    mock_create.assert_not_called()
    mock_add.assert_not_called()


@patch.object(JellyfinClient, "get_all_items")
@patch.object(JellyfinClient, "create_collection")
@patch.object(JellyfinClient, "add_to_collection")
def test_sync_groupings_live(mock_add, mock_create, mock_get_items, mock_client):
    mock_get_items.return_value = [{"Id": "col1", "Name": "Star Wars"}]
    groups = {
        "Star Wars": [{"Id": "1"}, {"Id": "2"}],
        "Star Trek": [{"Id": "3"}],
    }
    summary = sync_groupings(mock_client, groups, dry_run=False, min_items=1)
    assert "Star Wars" in summary
    assert "Star Trek" in summary
    mock_add.assert_called_once_with("col1", ["1", "2"])
    mock_create.assert_called_once_with("Star Trek", ["3"])


@patch.object(JellyfinClient, "get_all_items")
def test_sync_groupings_min_items(mock_get_items, mock_client):
    mock_get_items.return_value = []
    groups = {
        "Star Wars": [{"Id": "1"}, {"Id": "2"}],
        "Star Trek": [{"Id": "3"}],
    }
    summary = sync_groupings(mock_client, groups, dry_run=True, min_items=2)
    assert "Star Wars" in summary
    assert "Star Trek" not in summary
