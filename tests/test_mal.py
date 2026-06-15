"""Tests for MAL fetcher — covering uncovered lines (JSON decode error)."""

from unittest.mock import MagicMock, patch

import pytest

from mal import fetch_mal_list


@patch("mal.network.get")
def test_fetch_mal_json_decode_error(mock_get) -> None:
    """When the MAL API returns non-JSON (e.g. HTML error page),
    fetch_mal_list should raise RuntimeError with a clear message.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Simulate non-JSON response (e.g. HTML error page)
    mock_resp.json.side_effect = ValueError("Invalid JSON")
    # Use monkey-patch to make response.json() raise ValueError
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Invalid JSON response from MAL API"):
        fetch_mal_list("test_user", "test_client_id", status="completed")


@patch("mal.network.get")
def test_fetch_mal_normal_request(mock_get) -> None:
    """Normal request should succeed."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"node": {"id": 1}}, {"node": {"id": 2}}],
        "paging": {},
    }
    mock_get.return_value = mock_resp

    ids = fetch_mal_list("test_user", "test_client_id", status="completed")
    assert ids == [1, 2]


@patch("mal.network.get")
def test_fetch_mal_empty_client_id(mock_get) -> None:
    """Empty client_id should raise ValueError."""
    with pytest.raises(ValueError, match="MyAnimeList Client ID is required"):
        fetch_mal_list("test_user", "")


@patch("mal.network.get")
def test_fetch_mal_invalid_status(mock_get) -> None:
    """Invalid status should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown MAL status"):
        fetch_mal_list("test_user", "client_id", status="invalid_status")


@patch("mal.network.get")
def test_fetch_mal_all_status(mock_get) -> None:
    """'all' status should fetch without status parameter."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"node": {"id": 3}}],
        "paging": {},
    }
    mock_get.return_value = mock_resp

    ids = fetch_mal_list("test_user", "client_id", status="all")
    assert ids == [3]
    _, kwargs = mock_get.call_args
    assert "status" not in kwargs.get("params", {})
