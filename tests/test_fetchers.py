import pytest
import requests
from unittest.mock import patch, MagicMock
from imdb import fetch_imdb_list
from tmdb import fetch_tmdb_list
from anilist import fetch_anilist_list
from jellyfin import fetch_jellyfin_items


@patch('jellyfin.requests.get')
def test_fetch_jellyfin_items(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Items": [{"Name": "M1"}]}
    mock_get.return_value = mock_resp
    items = fetch_jellyfin_items("http://jf", "key", {"Type": "Movie"})
    assert items == [{"Name": "M1"}]
    # Verify params
    _args, kwargs = mock_get.call_args
    assert kwargs['headers']['X-Emby-Token'] == "key"
    assert kwargs['params']['Type'] == "Movie"


@patch('imdb.requests.get')
def test_fetch_imdb_list(mock_get):
    mock_response = MagicMock()
    mock_response.text = '<html><div class="lister-item-header"><a href="/title/tt1234567/"></a></div></html>'
    mock_get.return_value = mock_response
    ids = fetch_imdb_list("ls12345")
    assert ids == ["tt1234567"]


@patch('tmdb.requests.get')
def test_fetch_tmdb_list(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "items": [
            {"media_type": "movie", "id": 101},
            {"media_type": "tv", "id": 202}
        ],
        "total_pages": 1
    }
    mock_get.return_value = mock_response
    ids = fetch_tmdb_list("123", "api_key")
    assert ids == ["101", "202"]


@patch('anilist.requests.post')
def test_fetch_anilist_list(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {"entries": [{"mediaId": 12345}]}
                ]
            }
        }
    }
    mock_post.return_value = mock_response
    ids = fetch_anilist_list("username", "completed")
    assert ids == [12345]
    _args, kwargs = mock_post.call_args
    assert kwargs['json']['variables']['status'] == "COMPLETED"


# ---------------------------------------------------------------------------
# imdb.py edge cases
# ---------------------------------------------------------------------------

from imdb import fetch_imdb_list


def test_fetch_imdb_invalid_id():
    with pytest.raises(ValueError, match="Invalid IMDb list ID"):
        fetch_imdb_list("not-a-valid-id")


@patch('imdb.requests.get')
def test_fetch_imdb_http_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("Server Error")
    mock_get.return_value = mock_resp
    with pytest.raises(RuntimeError, match="Failed to fetch IMDb"):
        fetch_imdb_list("ls12345")


@patch('imdb.requests.get')
def test_fetch_imdb_pagination(mock_get):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.text = (
        '<html><div class="lister-item-header">'
        '<a href="/title/tt111/"></a></div>'
        '<a class="next-page">Next</a></html>'
    )
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.text = (
        '<html><div class="lister-item-header">'
        '<a href="/title/tt222/"></a></div></html>'
    )
    mock_get.side_effect = [resp1, resp2]
    ids = fetch_imdb_list("ls12345")
    assert ids == ["tt111", "tt222"]


# ---------------------------------------------------------------------------
# anilist.py edge cases
# ---------------------------------------------------------------------------

from anilist import fetch_anilist_list


@patch('anilist.requests.post')
def test_fetch_anilist_empty_collection(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"MediaListCollection": None}}
    mock_post.return_value = mock_resp
    ids = fetch_anilist_list("user")
    assert ids == []
