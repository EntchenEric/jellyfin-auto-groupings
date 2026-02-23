import pytest
import requests
from unittest.mock import patch, MagicMock
from letterboxd import fetch_letterboxd_list
from mal import fetch_mal_list
from trakt import fetch_trakt_list
from anilist import fetch_anilist_list
from tmdb import fetch_tmdb_list


@patch('requests.Session.get')
def test_fetch_letterboxd_list(mock_get):
    # Mock main list page
    mock_list_resp = MagicMock()
    mock_list_resp.status_code = 200
    mock_list_resp.text = 'data-film-slug="the-godfather"'
    
    # Mock film detail page
    mock_film_resp = MagicMock()
    mock_film_resp.status_code = 200
    mock_film_resp.text = 'href="https://www.imdb.com/title/tt0068646/"'
    
    mock_get.side_effect = [mock_list_resp, mock_film_resp]
    
    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == ["tt0068646"]

@patch('requests.Session.get')
def test_fetch_letterboxd_list_tmdb(mock_get):
    # Test TMDb ID extraction and pagination stop
    mock_list_resp = MagicMock()
    mock_list_resp.status_code = 200
    mock_list_resp.text = 'data-film-slug="film1" class="next"' 
    
    mock_film_resp = MagicMock()
    mock_film_resp.status_code = 200
    mock_film_resp.text = 'data-tmdb-id="500"'
    
    # Page 2
    mock_list_page2 = MagicMock()
    mock_list_page2.status_code = 200
    mock_list_page2.text = 'data-film-slug="film2"' # No "next" class
    
    mock_film2_resp = MagicMock()
    mock_film2_resp.status_code = 200
    mock_film2_resp.text = 'href="https://www.themoviedb.org/movie/600"'

    mock_get.side_effect = [mock_list_resp, mock_film_resp, mock_list_page2, mock_film2_resp]
    
    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == ["500", "600"]

def test_fetch_letterboxd_invalid_url():
    with pytest.raises(ValueError, match="Invalid Letterboxd URL"):
        fetch_letterboxd_list("https://not-lb-domain.com")

@patch('requests.Session.get')
def test_fetch_letterboxd_http_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("HTTP Error")
    mock_get.return_value = mock_resp
    with pytest.raises(RuntimeError, match="Failed to fetch Letterboxd"):
        fetch_letterboxd_list("https://letterboxd.com/user/list/list")

@patch('requests.get')
def test_fetch_mal_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"node": {"id": 123}}],
        "paging": {}
    }
    mock_get.return_value = mock_resp
    
    ids = fetch_mal_list("user", "client_id", "watching")
    assert ids == [123]
    # Verify status normalization
    args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "watching"

@patch('requests.get')
def test_fetch_mal_pagination(mock_get):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {
        "data": [{"node": {"id": 1}}],
        "paging": {"next": "url_to_page_2"}
    }
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {
        "data": [{"node": {"id": 2}}],
        "paging": {}
    }
    mock_get.side_effect = [resp1, resp2]
    ids = fetch_mal_list("user", "cid")
    assert ids == [1, 2]

@patch('requests.get')
def test_fetch_trakt_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"type": "movie", "movie": {"ids": {"imdb": "tt123"}}}
    ]
    mock_resp.headers = {"X-Pagination-Page-Count": "1"}
    mock_get.return_value = mock_resp
    
    ids = fetch_trakt_list("username/list", "client_id")
    assert ids == ["tt123"]

@patch('requests.post')
def test_fetch_anilist_list(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {
                        "entries": [{"mediaId": 101}, {"mediaId": 102}]
                    }
                ]
            }
        }
    }
    mock_post.return_value = mock_resp
    
    ids = fetch_anilist_list("user", "completed")
    assert ids == [101, 102]
    # Verify status mapping
    args, kwargs = mock_post.call_args
    assert kwargs['json']['variables']['status'] == "COMPLETED"

@patch('requests.post')
def test_fetch_anilist_all(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"MediaListCollection": {"lists": []}}}
    mock_post.return_value = mock_resp
    fetch_anilist_list("user", "all")
    args, kwargs = mock_post.call_args
    assert 'status' not in kwargs['json']['variables']

@patch('requests.get')
def test_fetch_tmdb_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{"id": 10}, {"id": 20}],
        "total_pages": 1
    }
    mock_get.return_value = mock_resp
    ids = fetch_tmdb_list("123", "key")
    assert ids == ["10", "20"]

def test_fetch_tmdb_invalid_args():
    with pytest.raises(ValueError, match="API Key is required"):
        fetch_tmdb_list("123", "")
    with pytest.raises(ValueError, match="List ID is required"):
        fetch_tmdb_list("", "key")

@patch('requests.get')
def test_fetch_tmdb_url_parsing(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [], "total_pages": 1}
    mock_get.return_value = mock_resp
    fetch_tmdb_list("https://www.themoviedb.org/list/999?foo=bar", "key")
    args, kwargs = mock_get.call_args
    assert "list/999" in args[0]

@patch('requests.get')
def test_fetch_mal_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("Unauthorized")
    mock_get.return_value = mock_resp
    with pytest.raises(requests.exceptions.HTTPError):
        fetch_mal_list("u", "c")

@patch('requests.get')
def test_fetch_trakt_pagination(mock_get):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = [{"type": "movie", "movie": {"ids": {"imdb": "tt1"}}}]
    resp1.headers = {"X-Pagination-Page-Count": "2"}
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = [{"type": "movie", "movie": {"ids": {"imdb": "tt2"}}}]
    resp2.headers = {"X-Pagination-Page-Count": "2"}
    mock_get.side_effect = [resp1, resp2]
    ids = fetch_trakt_list("u/l", "c")
    assert ids == ["tt1", "tt2"]

@patch('requests.post')
def test_fetch_anilist_empty_data(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"errors": [{"message": "Too bad"}]}
    mock_post.return_value = mock_resp
    ids = fetch_anilist_list("u")
    assert ids == []
