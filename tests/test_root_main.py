import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as root_main


def test_root_jellyfin_groupings_init():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096/", api_key="test-key", timeout=15)
    assert client.server_url == "http://localhost:8096"
    assert client.api_key == "test-key"
    assert client.timeout == 15
    headers = client._get_headers()
    assert headers["X-Emby-Token"] == "test-key"
    assert headers["Content-Type"] == "application/json"


def test_root_jellyfin_groupings_missing_api_key():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="")
    with pytest.raises(ValueError, match="API key is missing."):
        client._get_headers()


def test_root_jellyfin_groupings_missing_server_url():
    client = root_main.JellyfinGroupings(server_url="", api_key="key")
    with pytest.raises(ValueError, match="Server URL is missing."):
        client.get_collections()
    with pytest.raises(ValueError, match="Server URL is missing."):
        client.get_movies()
    with pytest.raises(ValueError, match="Server URL is missing."):
        client.create_collection("Test")
    with pytest.raises(ValueError, match="Server URL is missing."):
        client.add_to_collection("col1", ["item1"])


def test_root_jellyfin_groupings_get_collections():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Id": "col1", "Name": "Test Collection"}]}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        cols = client.get_collections()
        assert len(cols) == 1
        assert cols[0]["Name"] == "Test Collection"
        mock_get.assert_called_once_with(
            "http://localhost:8096/Items?IncludeItemTypes=BoxSet&Recursive=true",
            headers=client._get_headers(),
            timeout=10,
        )


def test_root_jellyfin_groupings_get_movies():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Id": "mov1", "Name": "Movie 1", "CollectionName": "Set"}]}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        movies = client.get_movies()
        assert len(movies) == 1
        assert movies[0]["Id"] == "mov1"
        mock_get.assert_called_once_with(
            "http://localhost:8096/Items?IncludeItemTypes=Movie&Recursive=true",
            headers=client._get_headers(),
            timeout=10,
        )


def test_root_jellyfin_groupings_create_collection():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Id": "new_col"}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "post", return_value=mock_resp) as mock_post:
        res = client.create_collection("Action Set")
        assert res["Id"] == "new_col"
        mock_post.assert_called_once_with(
            "http://localhost:8096/Collections?Name=Action Set",
            headers=client._get_headers(),
            timeout=10,
        )


def test_root_jellyfin_groupings_add_to_collection():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "post", return_value=mock_resp) as mock_post:
        client.add_to_collection("col1", ["item1", "item2"])
        mock_post.assert_called_once_with(
            "http://localhost:8096/Collections/col1/Items?Ids=item1,item2",
            headers=client._get_headers(),
            timeout=10,
        )


def test_root_jellyfin_groupings_add_to_collection_empty():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    with patch.object(client.session, "post") as mock_post:
        client.add_to_collection("col1", [])
        mock_post.assert_not_called()


def test_root_jellyfin_groupings_auto_group():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    with patch.object(client, "get_collections", return_value=[{"Id": "c1"}]):
        res = client.auto_group()
        assert res["status"] == "success"
        assert res["collections_count"] == 1

    with patch.object(client, "get_collections", side_effect=Exception("Network fail")):
        res = client.auto_group()
        assert res["status"] == "error"


def test_root_jellyfin_groupings_group_movies_by_collection():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    movies = [
        {"Id": "m1", "CollectionName": "Existing Set"},
        {"Id": "m2", "CollectionName": "New Set"},
        {"Id": "m3"},
    ]
    existing_cols = [{"Id": "c1", "Name": "Existing Set"}]

    with patch.object(client, "get_movies", return_value=movies), \
         patch.object(client, "get_collections", return_value=existing_cols), \
         patch.object(client, "create_collection", return_value={"Id": "c2"}) as mock_create, \
         patch.object(client, "add_to_collection") as mock_add:
        res = client.group_movies_by_collection()
        assert res["status"] == "success"
        assert res["collections_created"] == 1
        assert res["grouped_collections"] == 2
        mock_create.assert_called_once_with("New Set")
        assert mock_add.call_count == 2


def test_root_jellyfin_groupings_group_movies_by_collection_error():
    client = root_main.JellyfinGroupings(server_url="http://localhost:8096", api_key="key")
    with patch.object(client, "get_movies", side_effect=requests.RequestException("Fail")):
        res = client.group_movies_by_collection()
        assert res["status"] == "error"
