from unittest.mock import MagicMock, patch

from jellyfin_auto_groupings.cli import main
from jellyfin_auto_groupings.client import JellyfinClient


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

    # Pass user_id to skip admin lookup during get_movies
    client = JellyfinClient("http://localhost:8096", "test-api-key", user_id="admin")
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


@patch("jellyfin_auto_groupings.cli.sync_groupings")
@patch("jellyfin_auto_groupings.cli.JellyfinClient")
def test_cli_main_uses_pattern_argument(mock_client_cls, mock_sync, monkeypatch):
    """The --pattern argument must be forwarded to grouping (regression test)."""
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Name": "Series 1 Episode 1", "Id": "1"},
        {"Name": "Series 1 Episode 2", "Id": "2"},
        {"Name": "Series 2 Episode 1", "Id": "3"},
    ]
    mock_client_cls.return_value = client
    test_args = [
        "cli.py",
        "--url",
        "http://localhost:8096",
        "--api-key",
        "testkey",
        "--dry-run",
        "--pattern",
        r"^(Series \d)",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    main()

    groups_arg = mock_sync.call_args[0][1]
    assert "Series 1" in groups_arg
    assert "Series 2" in groups_arg
    assert len(groups_arg) == 2
