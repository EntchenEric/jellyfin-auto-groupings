"""
Unit tests for jellyfin_auto_groupings.api module.
"""

from unittest.mock import MagicMock, patch

import pytest

from jellyfin_auto_groupings.api import JellyfinAPI


@pytest.fixture
def api_client():
    return JellyfinAPI(server_url="http://localhost:8096/", api_key="testkey123", timeout=10)


def test_init_headers(api_client):
    assert api_client.server_url == "http://localhost:8096"
    headers = api_client._get_headers()
    assert headers["X-Emby-Token"] == "testkey123"
    assert headers["Content-Type"] == "application/json"


@patch("requests.get")
def test_get_collections_success(mock_get, api_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Name": "Marvel Collection", "Id": "col1"}]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    collections = api_client.get_collections()
    assert len(collections) == 1
    assert collections[0]["Name"] == "Marvel Collection"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Items",
        headers=api_client._get_headers(),
        params={"IncludeItemTypes": "BoxSet", "Recursive": "true"},
        timeout=10,
    )


@patch("requests.get")
def test_get_collection_items_success(mock_get, api_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Name": "Iron Man", "Id": "item1"}]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    items = api_client.get_collection_items("col1")
    assert len(items) == 1
    assert items[0]["Name"] == "Iron Man"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Items",
        headers=api_client._get_headers(),
        params={"ParentId": "col1", "Recursive": "true"},
        timeout=10,
    )
