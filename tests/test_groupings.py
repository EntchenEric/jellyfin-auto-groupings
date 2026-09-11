import pytest
from unittest.mock import MagicMock, patch
import requests
from jellyfin_groupings import JellyfinClient, group_movies_by_tag, group_movies_by_genre, main


def test_group_movies_by_tag():
    movies = [
        {"Id": "1", "Tags": ["Group:MCU", "Sci-Fi"]},
        {"Id": "2", "Tags": ["Group:MCU"]},
        {"Id": "3", "Tags": ["Group:Star Wars"]},
        {"Id": "4", "Tags": []},
        {"Tags": ["Group:NoId"]}
    ]
    res = group_movies_by_tag(movies)
    assert res == {
        "MCU": ["1", "2"],
        "Star Wars": ["3"]
    }


def test_group_movies_by_genre():
    movies = [
        {"Id": "1", "Genres": ["Action", "Sci-Fi"]},
        {"Id": "2", "Genres": ["Action"]},
        {"Id": "3", "Genres": ["Comedy"]},
        {"Genres": ["Action"]}
    ]
    res = group_movies_by_genre(movies, min_count=2)
    assert res == {
        "Action": ["1", "2"]
    }
    assert "Sci-Fi" not in res
    assert "Comedy" not in res


def test_jellyfin_client_init():
    client = JellyfinClient("http://localhost:8096/", "testkey", "user123")
    assert client.server_url == "http://localhost:8096"
    assert client.api_key == "testkey"
    assert client.user_id == "user123"
    assert client.session.headers["X-Emby-Token"] == "testkey"


@patch("requests.Session.get")
def test_get_users_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"Id": "u1", "Name": "Admin"}]
    mock_get.return_value = mock_resp

    client = JellyfinClient("http://localhost:8096", "testkey")
    users = client.get_users()
    assert users == [{"Id": "u1", "Name": "Admin"}]


@patch("requests.Session.get")
def test_get_users_failure(mock_get):
    mock_get.side_effect = requests.RequestException("Connection refused")
    client = JellyfinClient("http://localhost:8096", "testkey")
    users = client.get_users()
    assert users == []


@patch("requests.Session.get")
def test_get_movies_explicit_user(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Id": "m1", "Name": "Movie 1"}]}
    mock_get.return_value = mock_resp

    client = JellyfinClient("http://localhost:8096", "testkey", "u1")
    movies = client.get_movies()
    assert len(movies) == 1
    assert movies[0]["Id"] == "m1"


@patch("requests.Session.get")
def test_get_movies_auto_user(mock_get):
    mock_resp_users = MagicMock()
    mock_resp_users.json.return_value = [{"Id": "u1"}]
    mock_resp_movies = MagicMock()
    mock_resp_movies.json.return_value = {"Items": [{"Id": "m1"}]}
    mock_get.side_effect = [mock_resp_users, mock_resp_movies]

    client = JellyfinClient("http://localhost:8096", "testkey")
    movies = client.get_movies()
    assert len(movies) == 1
    assert movies[0]["Id"] == "m1"


@patch("requests.Session.get")
def test_get_movies_no_user_found(mock_get):
    mock_resp_users = MagicMock()
    mock_resp_users.json.return_value = []
    mock_get.return_value = mock_resp_users

    client = JellyfinClient("http://localhost:8096", "testkey")
    movies = client.get_movies()
    assert movies == []


@patch("requests.Session.post")
def test_create_collection_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Id": "c1", "Name": "MCU"}
    mock_post.return_value = mock_resp

    client = JellyfinClient("http://localhost:8096", "testkey")
    res = client.create_collection("MCU", ["1", "2"])
    assert res == {"Id": "c1", "Name": "MCU"}


def test_create_collection_empty_items():
    client = JellyfinClient("http://localhost:8096", "testkey")
    res = client.create_collection("Empty", [])
    assert res is None


@patch.dict("os.environ", {}, clear=True)
def test_main_missing_api_key():
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


@patch("jellyfin_groupings.JellyfinClient.create_collection")
@patch("jellyfin_groupings.JellyfinClient.get_movies")
@patch.dict("os.environ", {"JELLYFIN_API_KEY": "testkey"})
def test_main_success(mock_get_movies, mock_create_coll):
    mock_get_movies.return_value = [
        {"Id": "1", "Tags": ["Group:MCU"]}
    ]
    main()
    mock_create_coll.assert_called_once_with("MCU", ["1"])
