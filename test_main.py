import pytest
from unittest.mock import MagicMock, patch
import requests
from main import JellyfinGroupings

def test_init_defaults(monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://localhost:8096/")
    monkeypatch.setenv("JELLYFIN_API_KEY", "test_key")
    jg = JellyfinGroupings()
    assert jg.server_url == "http://localhost:8096"
    assert jg.api_key == "test_key"

def test_missing_api_key():
    jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="")
    with pytest.raises(ValueError, match="API key is missing"):
        jg.get_collections()

def test_missing_server_url():
    jg = JellyfinGroupings(server_url="", api_key="test_key")
    with pytest.raises(ValueError, match="Server URL is missing"):
        jg.get_collections()

@patch("requests.Session.get")
def test_get_collections_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "Marvel Collection", "Id": "123"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="secret")
    collections = jg.get_collections()
    assert len(collections) == 1
    assert collections[0]["Name"] == "Marvel Collection"
    mock_get.assert_called_once_with(
        "http://localhost:8096/Items?IncludeItemTypes=BoxSet&Recursive=true",
        headers={"X-Emby-Token": "secret", "Content-Type": "application/json"},
        timeout=10
    )

@patch("requests.Session.get")
def test_get_collections_failure(mock_get):
    mock_get.side_effect = requests.RequestException("Connection refused")
    jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="secret")
    with pytest.raises(requests.RequestException):
        jg.get_collections()

@patch.object(JellyfinGroupings, "get_collections")
def test_auto_group_success(mock_get_cols):
    mock_get_cols.return_value = [{"Name": "Collection 1"}]
    jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="secret")
    res = jg.auto_group()
    assert res["status"] == "success"
    assert res["collections_count"] == 1

@patch.object(JellyfinGroupings, "get_collections")
def test_auto_group_error(mock_get_cols):
    mock_get_cols.side_effect = Exception("API error")
    jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="secret")
    res = jg.auto_group()
    assert res["status"] == "error"
    assert res["message"] == "API error"
