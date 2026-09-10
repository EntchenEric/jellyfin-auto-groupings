import pytest
from unittest.mock import MagicMock, patch
from jellyfin_auto_groupings.jellyfin_api import JellyfinClient
from jellyfin_auto_groupings.cli import main

def test_jellyfin_client_headers():
    client = JellyfinClient("http://localhost:8096", "test-api-key")
    assert client.headers["X-Emby-Token"] == "test-api-key"
    assert client.base_url == "http://localhost:8096"

@patch("requests.get")
def test_jellyfin_client_get_movies(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "Movie 1", "Id": "123"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = JellyfinClient("http://localhost:8096", "test-api-key")
    movies = client.get_movies()
    assert len(movies) == 1
    assert movies[0]["Name"] == "Movie 1"

@patch("requests.post")
def test_jellyfin_client_create_collection(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Id": "coll-1"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    client = JellyfinClient("http://localhost:8096", "test-api-key")
    res = client.create_collection("Test Collection", ["123", "456"])
    assert res == {"Id": "coll-1"}

@patch("jellyfin_auto_groupings.cli.group_movies")
@patch("jellyfin_auto_groupings.cli.JellyfinClient")
def test_cli_main(mock_client_cls, mock_group_movies, monkeypatch):
    test_args = ["cli.py", "--url", "http://localhost:8096", "--api-key", "testkey", "--dry-run"]
    monkeypatch.setattr("sys.argv", test_args)
    mock_group_movies.return_value = {"Collection A": [{"Name": "Movie 1"}, {"Name": "Movie 2"}]}

    main()
    mock_client_cls.assert_called_once_with("http://localhost:8096", "testkey")
    mock_group_movies.assert_called_once()
