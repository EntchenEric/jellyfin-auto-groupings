"""Unit tests for mal.py (MyAnimeList client)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
import requests

from mal import _normalize_mal_status, fetch_mal_list


def test_normalize_mal_status_valid():
    assert _normalize_mal_status(None) is None
    assert _normalize_mal_status("") is None
    assert _normalize_mal_status("all") is None
    assert _normalize_mal_status("current") == "watching"
    assert _normalize_mal_status("planning") == "plan_to_watch"
    assert _normalize_mal_status("paused") == "on_hold"
    assert _normalize_mal_status("watching") == "watching"
    assert _normalize_mal_status("COMPLETED") == "completed"
    assert _normalize_mal_status("on-hold") == "on_hold"


def test_normalize_mal_status_invalid():
    with pytest.raises(ValueError, match="Unknown MAL status"):
        _normalize_mal_status("invalid_status_value")


def test_fetch_mal_list_missing_client_id():
    with pytest.raises(ValueError, match="MyAnimeList Client ID is required."):
        fetch_mal_list(username="testuser", client_id="")


@patch("network.get")
def test_fetch_mal_list_success(mock_get):
    mock_response_1 = MagicMock()
    mock_response_1.raise_for_status.return_value = None
    mock_response_1.json.return_value = {
        "data": [
            {"node": {"id": 101, "title": "Anime One"}},
            {"node": {"id": 102, "title": "Anime Two"}},
        ],
        "paging": {"next": "[https://api.myanimelist.net/v2/users/testuser/animelist?offset=2](https://api.myanimelist.net/v2/users/testuser/animelist?offset=2)"},
    }

    mock_response_2 = MagicMock()
    mock_response_2.raise_for_status.return_value = None
    mock_response_2.json.return_value = {
        "data": [
            {"node": {"id": 103, "title": "Anime Three"}},
        ],
        "paging": {},
    }

    mock_get.side_effect = [mock_response_1, mock_response_2]

    ids = fetch_mal_list(username="testuser", client_id="dummy_client_id", status="watching")

    assert ids == [101, 102, 103]
    assert mock_get.call_count == 2


@patch("network.get")
def test_fetch_mal_list_network_error(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Connection error")
    with pytest.raises(RuntimeError, match="Failed to fetch MAL list for user 'testuser'"):
        fetch_mal_list(username="testuser", client_id="dummy_client_id")


@patch("network.get")
def test_fetch_mal_list_invalid_json(mock_get):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_get.return_value = mock_response

    with pytest.raises(RuntimeError, match="Invalid JSON response from MAL API for user 'testuser'"):
        fetch_mal_list(username="testuser", client_id="dummy_client_id")
