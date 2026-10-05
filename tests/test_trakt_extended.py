import pytest
from unittest.mock import MagicMock, patch
import requests

import trakt
from trakt import (
    fetch_trakt_list,
    _parse_trakt_list_url,
    _build_trakt_headers,
    _fetch_trakt_page,
    _extract_imdb_ids_from_page,
)


def test_parse_trakt_list_url_valid():
    url = "[https://trakt.tv/users/john_doe/lists/favorite-movies](https://trakt.tv/users/john_doe/lists/favorite-movies)"
    username, slug = _parse_trakt_list_url(url)
    assert username == "john_doe"
    assert slug == "favorite-movies"

    shorthand = "john_doe/favorite-movies"
    username, slug = _parse_trakt_list_url(shorthand)
    assert username == "john_doe"
    assert slug == "favorite-movies"


def test_parse_trakt_list_url_invalid():
    with pytest.raises(ValueError, match="Invalid Trakt list URL"):
        _parse_trakt_list_url("invalid-url-without-slashes")


def test_build_trakt_headers():
    headers = _build_trakt_headers("my_client_id")
    assert headers["trakt-api-key"] == "my_client_id"
    assert headers["trakt-api-version"] == "2"
    assert headers["Content-Type"] == "application/json"


@patch("trakt.network.get")
def test_fetch_trakt_page_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"type": "movie", "movie": {"ids": {"imdb": "tt1234567"}}}]
    mock_resp.headers = {"X-Pagination-Page-Count": "3"}
    mock_get.return_value = mock_resp

    items, total_pages = _fetch_trakt_page("user", "slug", 1, {})
    assert len(items) == 1
    assert total_pages == 3


@patch("trakt.network.get")
def test_fetch_trakt_page_request_exception(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Connection error")
    with pytest.raises(RuntimeError, match="Failed to fetch Trakt list page"):
        _fetch_trakt_page("user", "slug", 1, {})


@patch("trakt.network.get")
def test_fetch_trakt_page_invalid_json(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.side_effect = ValueError("Invalid JSON")
    mock_get.return_value = mock_resp
    with pytest.raises(RuntimeError, match="Invalid JSON response from Trakt API"):
        _fetch_trakt_page("user", "slug", 1, {})


@patch("trakt.network.get")
def test_fetch_trakt_page_not_a_list(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": "not found"}
    mock_resp.headers = {}
    mock_get.return_value = mock_resp
    with pytest.raises(TypeError, match="Unexpected Trakt API response shape"):
        _fetch_trakt_page("user", "slug", 1, {})


def test_extract_imdb_ids_from_page():
    resp_json = [
        "malformed_string",
        {"type": "movie", "movie": "not_a_dict"},
        {"type": "show", "show": {"ids": "not_a_dict"}},
        {"type": "movie", "movie": {"ids": {"imdb": "tt1111111"}}},
        {"type": "movie", "movie": {"ids": {"imdb": "tt1111111"}}},  # Duplicate
        {"type": "show", "show": {"ids": {"imdb": "tt2222222"}}},
    ]
    ids = []
    seen = set()
    _extract_imdb_ids_from_page(resp_json, ids, seen)
    assert ids == ["tt1111111", "tt2222222"]


def test_fetch_trakt_list_missing_client_id():
    with pytest.raises(ValueError, match="A Trakt API Client ID"):
        fetch_trakt_list("user/list", "")


@patch("trakt._fetch_trakt_page")
def test_fetch_trakt_list_pagination(mock_fetch_page):
    page1_items = [
        {"type": "movie", "movie": {"ids": {"imdb": "tt0000001"}}},
    ]
    page2_items = [
        {"type": "show", "show": {"ids": {"imdb": "tt0000002"}}},
    ]
    mock_fetch_page.side_effect = [
        (page1_items, 2),
        (page2_items, 2),
    ]

    result = fetch_trakt_list("user/list", "valid_client_id")
    assert result == ["tt0000001", "tt0000002"]
    assert mock_fetch_page.call_count == 2
