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


def test_get_decade_groups_robustness():
    from jellyfin_auto_groupings.client import get_decade_groups

    # Test string years (would crash before fix with TypeError)
    items = [
        {"Id": "1", "ProductionYear": "1994", "Name": "Test 1"},
        {"Id": "2", "ProductionYear": "2003", "Name": "Test 2"},
        {"Id": "3", "ProductionYear": "1987", "Name": "Test 3"},
        {"Id": "4", "ProductionYear": "2015", "Name": "Test 4"},
    ]
    result = get_decade_groups(items)
    assert "1990s Movies" in result
    assert "2000s Movies" in result
    assert "1980s Movies" in result
    assert "2010s Movies" in result

    # Test mixed int and string years
    items2 = [
        {"Id": "a", "ProductionYear": 1995, "Name": "Int year"},
        {"Id": "b", "ProductionYear": "2005", "Name": "String year"},
    ]
    result2 = get_decade_groups(items2)
    assert "1990s Movies" in result2
    assert "2000s Movies" in result2

    # Test invalid years are ignored
    items3 = [
        {"Id": "x", "ProductionYear": 0, "Name": "Year zero"},
        {"Id": "y", "ProductionYear": -5, "Name": "Negative year"},
        {"Id": "z", "ProductionYear": "", "Name": "Empty string year"},
        {"Id": "w", "ProductionYear": "invalid", "Name": "Non-numeric string"},
    ]
    result3 = get_decade_groups(items3)
    assert result3 == {}

    # Test years outside valid range are ignored
    items4 = [
        {"Id": "old", "ProductionYear": 1700, "Name": "Too old"},
        {"Id": "future", "ProductionYear": 2500, "Name": "Too far future"},
    ]
    result4 = get_decade_groups(items4)
    assert result4 == {}

    # Test fallback to PremiereDate
    items5 = [
        {"Id": "p1", "PremiereDate": "1999-05-21T00:00:00Z", "Name": "PremiereDate fallback"},
        {"Id": "p2", "PremiereDate": "2007-12-03", "Name": "PremiereDate only"},
    ]
    result5 = get_decade_groups(items5)
    assert "1990s Movies" in result5
    assert "2000s Movies" in result5


def test_get_year_groups_robustness():
    from jellyfin_auto_groupings.client import get_year_groups

    # Test string years
    items = [
        {"Id": "1", "ProductionYear": "1994", "Name": "Test 1"},
        {"Id": "2", "ProductionYear": "2003", "Name": "Test 2"},
        {"Id": "3", "ProductionYear": "1987", "Name": "Test 3"},
        {"Id": "4", "ProductionYear": "2015", "Name": "Test 4"},
    ]
    result = get_year_groups(items)
    assert "Best of 1994" in result
    assert "Best of 2003" in result
    assert "Best of 1987" in result
    assert "Best of 2015" in result

    # Test mixed int and string years
    items2 = [
        {"Id": "a", "ProductionYear": 1995, "Name": "Int year"},
        {"Id": "b", "ProductionYear": "2005", "Name": "String year"},
    ]
    result2 = get_year_groups(items2)
    assert "Best of 1995" in result2
    assert "Best of 2005" in result2

    # Test invalid years are ignored
    items3 = [
        {"Id": "x", "ProductionYear": 0, "Name": "Year zero"},
        {"Id": "y", "ProductionYear": -5, "Name": "Negative year"},
        {"Id": "z", "ProductionYear": "", "Name": "Empty string year"},
        {"Id": "w", "ProductionYear": "invalid", "Name": "Non-numeric string"},
    ]
    result3 = get_year_groups(items3)
    assert result3 == {}

    # Test years outside valid range are ignored
    items4 = [
        {"Id": "old", "ProductionYear": 1700, "Name": "Too old"},
        {"Id": "future", "ProductionYear": 2500, "Name": "Too far future"},
    ]
    result4 = get_year_groups(items4)
    assert result4 == {}

    # Test fallback to PremiereDate
    items5 = [
        {"Id": "p1", "PremiereDate": "1999-05-21T00:00:00Z", "Name": "PremiereDate fallback"},
        {"Id": "p2", "PremiereDate": "2007-12-03", "Name": "PremiereDate only"},
    ]
    result5 = get_year_groups(items5)
    assert "Best of 1999" in result5
    assert "Best of 2007" in result5
