"""Tests for TMDb API client (fetch_tmdb_list, get_tmdb_recommendations)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from tmdb import fetch_tmdb_list, get_tmdb_recommendations


def test_fetch_tmdb_list_missing_args() -> None:
    with pytest.raises(ValueError, match="A TMDb API Key is required"):
        fetch_tmdb_list("123", "")
    with pytest.raises(ValueError, match="A TMDb List ID is required"):
        fetch_tmdb_list("", "api_key")


@patch("network.get")
def test_fetch_tmdb_list_success(mock_get) -> None:
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        "items": [{"id": 101}, {"id": 102}],
        "total_pages": 2,
    }
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        "items": [{"id": 103}],
        "total_pages": 2,
    }
    mock_get.side_effect = [mock_resp_1, mock_resp_2]

    ids = fetch_tmdb_list("123", "test_key")
    assert ids == ["101", "102", "103"]
    assert mock_get.call_count == 2


@patch("network.get")
def test_fetch_tmdb_list_url_parsing(mock_get) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{"id": 101}],
        "total_pages": 1,
    }
    mock_get.return_value = mock_resp

    ids = fetch_tmdb_list(
        "https://www.themoviedb.org/list/456?language=en-US",
        "test_key",
    )
    assert ids == ["101"]
    args, _kwargs = mock_get.call_args
    assert "/list/456" in args[0]


@patch("network.get")
def test_fetch_tmdb_list_failure(mock_get) -> None:
    mock_get.side_effect = requests.exceptions.RequestException("Network Error")
    with pytest.raises(RuntimeError, match="Failed to fetch TMDb list page 1"):
        fetch_tmdb_list("123", "test_key")


def test_get_tmdb_recommendations_missing_key() -> None:
    with pytest.raises(ValueError, match="A TMDb API Key is required"):
        get_tmdb_recommendations([("101", "movie")], "")


@patch("network.get")
def test_get_tmdb_recommendations_success(mock_get) -> None:
    mock_resp_movie = MagicMock()
    mock_resp_movie.status_code = 200
    mock_resp_movie.json.return_value = {
        "results": [{"id": 201}, {"id": 202}],
    }

    mock_resp_tv = MagicMock()
    mock_resp_tv.status_code = 200
    mock_resp_tv.json.return_value = {
        "results": [{"id": 202}, {"id": 203}],
    }

    mock_get.side_effect = [mock_resp_movie, mock_resp_tv]

    # "movie" returns 201, 202
    # "tv" returns 202, 203
    # 202 gets score from both, so it should be the highest
    recs = get_tmdb_recommendations([("101", "movie"), ("102", "tv")], "test_key")

    # 201 score: 1.0/1 = 1.0
    # 202 score: 1.0/2 + 1.0/1 = 1.5
    # 203 score: 1.0/2 = 0.5
    assert recs == ["202", "201", "203"]


@patch("network.get")
def test_get_tmdb_recommendations_failure_skipped(mock_get) -> None:
    mock_resp_movie = MagicMock()
    mock_resp_movie.status_code = 200
    mock_resp_movie.json.return_value = {
        "results": [{"id": 201}],
    }

    mock_get.side_effect = [
        requests.exceptions.RequestException("Error"),
        mock_resp_movie,
    ]

    recs = get_tmdb_recommendations(
        [("error_id", "movie"), ("101", "movie")],
        "test_key",
    )
    assert recs == ["201"]


@patch("tmdb.time.sleep")
@patch("network.get")
def test_get_tmdb_recommendations_rate_limit_retry_after(
    mock_get, mock_sleep,
) -> None:
    """429 response with Retry-After header sleeps the specified duration."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "3"}

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = {
        "results": [{"id": 301}],
    }

    mock_get.side_effect = [mock_resp_429, mock_resp_ok]

    recs = get_tmdb_recommendations(
        [("101", "movie"), ("102", "movie")],
        "test_key",
    )
    mock_sleep.assert_called_once_with(3)
    assert recs == ["301"]


@patch("tmdb.time.sleep")
@patch("network.get")
def test_get_tmdb_recommendations_rate_limit_no_header(
    mock_get, mock_sleep,
) -> None:
    """429 without Retry-After header falls back to 1s sleep."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {}

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = {
        "results": [{"id": 302}],
    }

    mock_get.side_effect = [mock_resp_429, mock_resp_ok]

    recs = get_tmdb_recommendations(
        [("101", "movie"), ("102", "movie")],
        "test_key",
    )
    mock_sleep.assert_called_once_with(1)
    assert recs == ["302"]


@patch("tmdb.time.sleep")
@patch("network.get")
def test_get_tmdb_recommendations_rate_limit_non_numeric_header(
    mock_get, mock_sleep,
) -> None:
    """429 with non-numeric Retry-After falls back to 1s sleep."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "not-a-number"}

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = {
        "results": [{"id": 303}],
    }

    mock_get.side_effect = [mock_resp_429, mock_resp_ok]

    recs = get_tmdb_recommendations(
        [("101", "movie"), ("102", "movie")],
        "test_key",
    )
    mock_sleep.assert_called_once_with(1)
    assert recs == ["303"]
