import pytest
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
    assert kwargs['params']['api_key'] == "key"
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
    
    ids = fetch_anilist_list("username")
    assert ids == [12345]
