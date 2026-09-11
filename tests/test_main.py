import pytest
from unittest.mock import MagicMock, patch
from jellyfin_groupings.main import JellyfinGroupings, main

def test_jellyfin_groupings_init():
    jg = JellyfinGroupings("http://localhost:8096", "test-api-key")
    assert jg.url == "http://localhost:8096"
    assert jg.api_key == "test-api-key"
    assert jg.headers["X-Emby-Token"] == "test-api-key"
    assert jg.headers["Content-Type"] == "application/json"

def test_jellyfin_groupings_init_strip_slash():
    jg = JellyfinGroupings("http://localhost:8096/", "test-api-key")
    assert jg.url == "http://localhost:8096"

@patch("requests.get")
def test_get_collections(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Id": "col1", "Name": "Collection 1"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    jg = JellyfinGroupings("http://localhost:8096", "test-api-key")
    collections = jg.get_collections()

    assert len(collections) == 1
    assert collections[0]["Name"] == "Collection 1"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Collections",
        headers=jg.headers,
        params={"IncludeItemTypes": "BoxSet", "Recursive": True}
    )

@patch("requests.get")
def test_get_movies(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Id": "mov1", "Name": "Movie 1"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    jg = JellyfinGroupings("http://localhost:8096", "test-api-key")
    movies = jg.get_movies()

    assert len(movies) == 1
    assert movies[0]["Name"] == "Movie 1"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Items",
        headers=jg.headers,
        params={"IncludeItemTypes": "Movie", "Recursive": True, "Fields": "ProviderIds"}
    )

@patch("requests.post")
def test_create_collection(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Id": "new_col_id", "Name": "New Collection"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    jg = JellyfinGroupings("http://localhost:8096", "test-api-key")
    result = jg.create_collection("New Collection", ["mov1", "mov2"])

    assert result["Id"] == "new_col_id"
    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections",
        headers=jg.headers,
        params={"Name": "New Collection", "Ids": "mov1,mov2"}
    )

@patch("requests.post")
def test_add_to_collection(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    jg = JellyfinGroupings("http://localhost:8096", "test-api-key")
    jg.add_to_collection("col1", ["mov3"])

    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections/col1/Items",
        headers=jg.headers,
        params={"Ids": "mov3"}
    )

@patch.dict("os.environ", {"JELLYFIN_URL": "http://localhost:8096", "JELLYFIN_API_KEY": "test-key"})
@patch("jellyfin_groupings.main.JellyfinGroupings.get_collections")
@patch("jellyfin_groupings.main.JellyfinGroupings.get_movies")
def test_main_success(mock_get_movies, mock_get_collections):
    mock_get_collections.return_value = []
    mock_get_movies.return_value = []

    with patch("builtins.print") as mock_print:
        main()
        mock_print.assert_any_call("Found 0 existing collections.")
        mock_print.assert_any_call("Found 0 movies.")

@patch.dict("os.environ", {}, clear=True)
def test_main_missing_api_key():
    with patch("builtins.print") as mock_print:
        main()
        mock_print.assert_called_once_with("Error: JELLYFIN_API_KEY environment variable is required.")
