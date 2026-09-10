import pytest
from unittest.mock import MagicMock, patch
import requests

from jellyfin_auto_groupings.main import JellyfinAutoGroupings


@pytest.fixture
def client():
    return JellyfinAutoGroupings("http://localhost:8096", "test-api-key", dry_run=True)


def test_init_normalizes_url():
    client = JellyfinAutoGroupings("http://localhost:8096/", "test-api-key")
    assert client.server_url == "http://localhost:8096"
    assert client.headers["X-Emby-Token"] == "test-api-key"


def test_get_headers(client):
    headers = client._get_headers()
    assert headers["X-Emby-Token"] == "test-api-key"
    assert headers["Accept"] == "application/json"


@patch("requests.Session.get")
def test_get_movies(mock_get, client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Items": [
            {"Id": "1", "Name": "Toy Story", "Type": "Movie"},
            {"Id": "2", "Name": "Toy Story 2", "Type": "Movie"},
        ]
    }
    mock_get.return_value = mock_response

    movies = client.get_movies()
    assert len(movies) == 2
    assert movies[0]["Name"] == "Toy Story"
    mock_get.assert_called_once()
    assert "IncludeItemTypes=Movie" in mock_get.call_args[0][0]


@patch("requests.Session.get")
def test_get_movies_http_error(mock_get, client):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.RequestException("API Error")
    mock_get.return_value = mock_response

    with pytest.raises(requests.RequestException):
        client.get_movies()


def test_find_collections_by_name(client):
    movies = [
        {"Id": "1", "Name": "Toy Story 1"},
        {"Id": "2", "Name": "Toy Story 2"},
        {"Id": "3", "Name": "Toy Story 3"},
        {"Id": "4", "Name": "Standalone Movie"},
        {"Id": "5", "Name": "The Matrix"},
        {"Id": "6", "Name": "The Matrix Reloaded"},
    ]

    collections = client.find_collections_by_name(movies, min_size=2)
    assert "Toy Story" in collections
    assert len(collections["Toy Story"]) == 3
    assert "The Matrix" in collections
    assert len(collections["The Matrix"]) == 2
    assert "Standalone Movie" not in collections


def test_find_collections_min_size(client):
    movies = [
        {"Id": "1", "Name": "Avatar"},
        {"Id": "2", "Name": "Avatar: The Way of Water"},
    ]
    collections_min_3 = client.find_collections_by_name(movies, min_size=3)
    assert len(collections_min_3) == 0

    collections_min_2 = client.find_collections_by_name(movies, min_size=2)
    assert len(collections_min_2) == 1


@patch("requests.Session.post")
def test_create_collection_dry_run(mock_post, client):
    # client fixture has dry_run=True
    result = client.create_collection("Test Collection", ["id1", "id2"])
    assert result is True
    mock_post.assert_not_called()


@patch("requests.Session.post")
def test_create_collection_real(mock_post):
    real_client = JellyfinAutoGroupings("http://localhost:8096", "test-api-key", dry_run=False)
    mock_response = MagicMock()
    mock_response.json.return_value = {"Id": "new_col_id"}
    mock_post.return_value = mock_response

    result = real_client.create_collection("Test Collection", ["id1", "id2"])
    assert result is True
    mock_post.assert_called_once()


@patch("requests.Session.post")
def test_create_collection_failure(mock_post):
    real_client = JellyfinAutoGroupings("http://localhost:8096", "test-api-key", dry_run=False)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.RequestException("Failed")
    mock_post.return_value = mock_response

    result = real_client.create_collection("Test Collection", ["id1", "id2"])
    assert result is False


@patch.object(JellyfinAutoGroupings, "get_movies")
@patch.object(JellyfinAutoGroupings, "create_collection")
def test_auto_group_all(mock_create_col, mock_get_movies, client):
    mock_get_movies.return_value = [
        {"Id": "1", "Name": "Shrek 1"},
        {"Id": "2", "Name": "Shrek 2"},
    ]
    mock_create_col.return_value = True

    created = client.auto_group_all(min_size=2)
    assert created == 1
    mock_create_col.assert_called_once_with("Shrek", ["1", "2"])
