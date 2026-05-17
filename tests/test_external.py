from unittest.mock import MagicMock, patch

import pytest
import requests

from anilist import fetch_anilist_list
from letterboxd import (
    _extract_ids_from_list_page,
    _fetch_id_for_slug,
    _fetch_ids_for_slugs,
    fetch_letterboxd_list,
)
from mal import fetch_mal_list
from tmdb import fetch_tmdb_list
from trakt import fetch_trakt_list


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
    mock_list_page2.text = 'data-film-slug="film2"'  # No "next" class

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
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("HTTP Error")
    mock_get.return_value = mock_resp
    with pytest.raises(RuntimeError, match="Failed to fetch Letterboxd"):
        fetch_letterboxd_list("https://letterboxd.com/user/list/list")


@patch('requests.get')
def test_fetch_mal_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"node": {"id": 123}}],
        "paging": {},
    }
    mock_get.return_value = mock_resp

    ids = fetch_mal_list("user", "client_id", "watching")
    assert ids == [123]
    # Verify status normalization
    _args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "watching"


@patch('requests.get')
def test_fetch_mal_pagination(mock_get):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {
        "data": [{"node": {"id": 1}}],
        "paging": {"next": "url_to_page_2"},
    }
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {
        "data": [{"node": {"id": 2}}],
        "paging": {},
    }
    mock_get.side_effect = [resp1, resp2]
    ids = fetch_mal_list("user", "cid")
    assert ids == [1, 2]


@patch('requests.get')
def test_fetch_trakt_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"type": "movie", "movie": {"ids": {"imdb": "tt123"}}},
    ]
    mock_resp.headers = {"X-Pagination-Page-Count": "1"}
    mock_get.return_value = mock_resp

    ids = fetch_trakt_list("username/list", "client_id")
    assert ids == ["tt123"]


@patch('requests.post')
def test_fetch_anilist_all(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"MediaListCollection": {"lists": []}}}
    mock_post.return_value = mock_resp
    fetch_anilist_list("user", "all")
    _args, kwargs = mock_post.call_args
    assert 'status' not in kwargs['json']['variables']


def test_fetch_tmdb_invalid_args():
    with pytest.raises(ValueError, match=r"A TMDb API Key is required to fetch TMDb lists\."):
        fetch_tmdb_list("123", "")
    with pytest.raises(ValueError, match=r"A TMDb List ID is required\."):
        fetch_tmdb_list("", "key")


@patch('requests.get')
def test_fetch_tmdb_url_parsing(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [], "total_pages": 1}
    mock_get.return_value = mock_resp
    fetch_tmdb_list("https://www.themoviedb.org/list/999?foo=bar", "key")
    args, _kwargs = mock_get.call_args
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


# ---------------------------------------------------------------------------
# letterboxd.py edge cases
# ---------------------------------------------------------------------------


def test_extract_ids_tmdb_from_list_page():
    html = 'data-film-slug="film1" data-tmdb-id="123"'
    result = _extract_ids_from_list_page(html)
    assert result == {"film1": "123"}


def test_extract_ids_imdb_from_list_page():
    html = 'data-film-slug="film1" href="https://www.imdb.com/title/tt456/"'
    result = _extract_ids_from_list_page(html)
    assert result == {"film1": "tt456"}


def test_extract_ids_themoviedb_from_list_page():
    html = 'data-film-slug="film1" href="https://www.themoviedb.org/movie/789"'
    result = _extract_ids_from_list_page(html)
    assert result == {"film1": "789"}


def test_extract_ids_priority_tmdb_over_imdb():
    # If both tmdb and imdb present, tmdb should win (matches first)
    html = (
        'data-film-slug="film1" data-tmdb-id="111" '
        'href="https://www.imdb.com/title/tt222/"'
    )
    result = _extract_ids_from_list_page(html)
    assert result == {"film1": "111"}


@patch('requests.Session.get')
def test_fetch_id_for_slug_request_exception(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Network down")
    result = _fetch_id_for_slug("some-film")
    assert result is None


@patch('requests.Session.get')
def test_letterboxd_404_on_page_two(mock_get):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.text = 'data-film-slug="film1" class="next"'

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.text = 'href="https://www.imdb.com/title/tt1234567/"'

    resp3 = MagicMock()
    resp3.status_code = 404

    mock_get.side_effect = [resp1, resp2, resp3]

    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == ["tt1234567"]


@patch('requests.Session.get')
def test_letterboxd_fallback_slug_regex(mock_get):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<a href="/film/the-godfather/">Film</a>'
    mock_get.return_value = resp

    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == []


@patch('requests.Session.get')
def test_letterboxd_no_slugs(mock_get):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<html><body>No films here</body></html>'
    mock_get.return_value = resp

    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == []


@patch('letterboxd._fetch_id_for_slug')
@patch('requests.Session.get')
def test_letterboxd_threadpool_exception(mock_get, mock_fetch_slug):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = 'data-film-slug="film1"'
    mock_get.return_value = resp

    mock_fetch_slug.side_effect = RuntimeError("Unexpected")

    ids = fetch_letterboxd_list("https://letterboxd.com/user/list/my-list")
    assert ids == []


def test_fetch_ids_for_slugs_empty():
    """Cover letterboxd.py:80 — early return when slugs list is empty."""
    assert _fetch_ids_for_slugs([]) == {}


# ---------------------------------------------------------------------------
# mal.py edge cases
# ---------------------------------------------------------------------------

def test_fetch_mal_no_client_id():
    with pytest.raises(ValueError, match="MyAnimeList Client ID is required"):
        fetch_mal_list("user", "")


@patch('requests.get')
def test_fetch_mal_status_current(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [], "paging": {}}
    mock_get.return_value = mock_resp

    fetch_mal_list("user", "cid", "current")
    _args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "watching"


@patch('requests.get')
def test_fetch_mal_status_planning(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [], "paging": {}}
    mock_get.return_value = mock_resp

    fetch_mal_list("user", "cid", "planning")
    _args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "plan_to_watch"


@patch('requests.get')
def test_fetch_mal_status_paused(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [], "paging": {}}
    mock_get.return_value = mock_resp

    fetch_mal_list("user", "cid", "paused")
    _args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "on_hold"


@patch('requests.get')
def test_fetch_mal_status_all(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [], "paging": {}}
    mock_get.return_value = mock_resp

    fetch_mal_list("user", "cid", "all")
    _args, kwargs = mock_get.call_args
    assert 'status' not in kwargs['params']


@patch('requests.get')
def test_fetch_mal_status_unknown(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [], "paging": {}}
    mock_get.return_value = mock_resp

    fetch_mal_list("user", "cid", "custom_status")
    _args, kwargs = mock_get.call_args
    assert kwargs['params']['status'] == "custom_status"


# ---------------------------------------------------------------------------
# trakt.py edge cases
# ---------------------------------------------------------------------------

def test_fetch_trakt_no_client_id():
    with pytest.raises(ValueError, match="Trakt API Client ID"):
        fetch_trakt_list("user/list", "")


@patch('requests.get')
def test_fetch_trakt_full_url(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"type": "movie", "movie": {"ids": {"imdb": "tt111"}}},
    ]
    mock_resp.headers = {"X-Pagination-Page-Count": "1"}
    mock_get.return_value = mock_resp

    ids = fetch_trakt_list("https://trakt.tv/users/jane/lists/my-list", "client_id")
    assert ids == ["tt111"]


def test_fetch_trakt_invalid_url():
    with pytest.raises(ValueError, match="Invalid Trakt list URL"):
        fetch_trakt_list("not-a-valid-url", "client_id")


@patch('requests.get')
def test_fetch_trakt_http_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("Server Error")
    mock_get.return_value = mock_resp
    with pytest.raises(RuntimeError, match="Failed to fetch Trakt"):
        fetch_trakt_list("user/list", "client_id")


@patch('requests.get')
def test_fetch_trakt_empty_items(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_resp.headers = {"X-Pagination-Page-Count": "1"}
    mock_get.return_value = mock_resp

    ids = fetch_trakt_list("user/list", "client_id")
    assert ids == []


@patch('requests.get')
def test_fetch_trakt_bad_pagination_header(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"type": "movie", "movie": {"ids": {"imdb": "tt222"}}},
    ]
    mock_resp.headers = {"X-Pagination-Page-Count": "not_a_number"}
    mock_get.return_value = mock_resp

    ids = fetch_trakt_list("user/list", "client_id")
    assert ids == ["tt222"]
