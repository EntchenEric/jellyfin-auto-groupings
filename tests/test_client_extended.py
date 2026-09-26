from unittest.mock import patch

import requests

from jellyfin_groupings import JellyfinClient, group_movies_by_genre


def test_jellyfin_client_methods_success_and_failures():
    client = JellyfinClient("http://localhost:8096/", "test-key", "user-1")
    assert client.server_url == "http://localhost:8096"

    with patch.object(client.session, "get") as mock_get:
        # get_users success
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"Id": "u1", "Policy": {"IsAdministrator": False}},
            {"Id": "u2", "Policy": {"IsAdministrator": True}},
        ]
        users = client.get_users()
        assert len(users) == 2
        assert client.get_first_admin_user_id() == "u2"

        # get_users request failure
        mock_get.side_effect = requests.RequestException("connection error")
        assert client.get_users() == []
        assert client.get_first_admin_user_id() is None

    with patch.object(client.session, "get") as mock_get:
        # get_collections success and exception
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Items": [{"Id": "c1", "Name": "Collection 1"}]
        }
        assert len(client.get_collections()) == 1
        mock_get.side_effect = requests.RequestException()
        assert client.get_collections() == []

    with patch.object(client.session, "get") as mock_get:
        # get_collection_items success and exception
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "Items": [{"Id": "m1", "Name": "Movie 1"}]
        }
        assert len(client.get_collection_items("c1")) == 1
        mock_get.side_effect = requests.RequestException()
        assert client.get_collection_items("c1") == []

    with patch.object(client.session, "get") as mock_get:
        # get_movies exception path
        mock_get.side_effect = requests.RequestException()
        assert client.get_movies() == []

    with patch.object(client.session, "post") as mock_post:
        # create_collection empty item_ids
        assert client.create_collection("Test", []) is None
        # create_collection request exception
        mock_post.side_effect = requests.RequestException()
        assert client.create_collection("Test", ["item1"]) is None


def test_group_movies_by_genre():
    movies = [
        {"Id": "m1", "Genres": ["Action", "Sci-Fi"]},
        {"Id": "m2", "Genres": ["Action"]},
        {"Id": "m3"},
    ]
    grouped = group_movies_by_genre(movies, min_count=2)
    assert "Action" in grouped
    assert len(grouped["Action"]) == 2
    assert "Sci-Fi" not in grouped
