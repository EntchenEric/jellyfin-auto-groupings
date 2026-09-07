import pytest
from unittest.mock import patch, MagicMock
import os

from jellyfin_auto_groupings.config import Config, load_config
from jellyfin_auto_groupings.api import JellyfinAPI
from jellyfin_auto_groupings.main import main


def test_config_load_from_env():
    with patch.dict(os.environ, {
        "JELLYFIN_URL": "http://localhost:8096",
        "JELLYFIN_API_KEY": "testkey123",
        "DRY_RUN": "true"
    }):
        cfg = load_config()
        assert cfg.server_url == "http://localhost:8096"
        assert cfg.api_key == "testkey123"
        assert cfg.dry_run is True


def test_config_missing_required():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="JELLYFIN_URL and JELLYFIN_API_KEY must be set"):
            load_config()


def test_jellyfin_api_headers():
    api = JellyfinAPI("http://localhost:8096", "testkey123")
    headers = api._get_headers()
    assert "X-Emby-Token" in headers
    assert headers["X-Emby-Token"] == "testkey123"


@patch("requests.get")
def test_get_collections(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "Collection 1", "Id": "c1"}]}
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    api = JellyfinAPI("http://localhost:8096", "testkey123")
    items = api.get_collections()
    assert len(items) == 1
    assert items[0]["Name"] == "Collection 1"


@patch("jellyfin_auto_groupings.main.load_config")
@patch("jellyfin_auto_groupings.main.JellyfinAPI")
@patch("jellyfin_auto_groupings.main.auto_group_collections")
def test_main_execution(mock_auto_group, mock_api_cls, mock_load_config):
    mock_cfg = MagicMock(server_url="http://localhost:8096", api_key="key", dry_run=False)
    mock_load_config.return_value = mock_cfg
    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api
    mock_auto_group.return_value = {"grouped": 2}

    result = main()
    assert result == {"grouped": 2}
    mock_auto_group.assert_called_once_with(mock_api, dry_run=False)
