"""Extended unit tests for tmdb.py to increase test coverage and edge-case handling."""
from unittest.mock import MagicMock, patch

import pytest
import requests

import tmdb


def test_tmdb_normalize_list_id():
    assert tmdb._normalize_tmdb_list_id("  12345  ") == "12345"
    assert tmdb._normalize_tmdb_list_id("[https://www.themoviedb.org/list/8204231](https://www.themoviedb.org/list/8204231)") == "8204231"
    assert tmdb._normalize_tmdb_list_id("[http://themoviedb.org/list/8204231/](http://themoviedb.org/list/8204231/)") == "8204231"


def test_tmdb_fetch_page_http_error():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_resp
        with pytest.raises(RuntimeError, match="Failed to fetch TMDb list page 1"):
            tmdb._fetch_tmdb_page("123", "fake_key", 1)


def test_tmdb_fetch_list_multi_page_and_dedup():
    with patch("tmdb._fetch_tmdb_page") as mock_fetch:
        mock_fetch.side_effect = [
            {"items": [{"id": 101}, {"id": 102}], "total_pages": 2},
            {"items": [{"id": 102}, {"id": 103}], "total_pages": 2},
        ]
        ids = tmdb.fetch_tmdb_list("12345", "fake_api_key")
        assert ids == ["101", "102", "103"]
        assert mock_fetch.call_count == 2


def test_tmdb_recommendations_value_error():
    with pytest.raises(ValueError, match="TMDb API Key is required"):
        tmdb.get_tmdb_recommendations([("101", "movie")], "")


def test_tmdb_recommendations_rate_limit_retry():
    with patch("tmdb.network.get") as mock_get, patch("time.sleep") as mock_sleep:
        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 429
        rate_limit_resp.headers = {"Retry-After": "1"}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "results": [{"id": 501}, {"id": 502}]
        }

        mock_get.side_effect = [rate_limit_resp, ok_resp]

        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == ["501", "502"]
        assert mock_sleep.called


def test_tmdb_recommendations_other_status_code():
    with patch("tmdb.network.get") as mock_get:
        err_resp = MagicMock()
        err_resp.status_code = 500
        mock_get.return_value = err_resp

        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == []


def test_tmdb_recommendations_exception_handling():
    with patch("tmdb.network.get") as mock_get:
        mock_get.side_effect = requests.exceptions.RequestException("Connection reset")

        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == []
