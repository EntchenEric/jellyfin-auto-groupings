from unittest.mock import MagicMock, patch

import pytest

from jellyfin_auto_groupings.api import JellyfinAPI
from jellyfin_auto_groupings.config import load_config
from jellyfin_auto_groupings.grouper import CollectionGrouper
from src.jellyfin_auto_groupings.groupings import (
    create_groupings,
    group_by_genre,
    group_by_studio,
    group_by_tag,
    parse_grouping_rules,
    process_groupings,
)


def test_load_config_success(monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://localhost:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "test-key")
    monkeypatch.setenv("DRY_RUN", "true")
    cfg = load_config()
    assert cfg.server_url == "http://localhost:8096"
    assert cfg.api_key == "test-key"
    assert cfg.dry_run is True


def test_load_config_missing_env(monkeypatch):
    monkeypatch.delenv("JELLYFIN_URL", raising=False)
    monkeypatch.delenv("JELLYFIN_API_KEY", raising=False)
    with pytest.raises(ValueError, match="JELLYFIN_URL and JELLYFIN_API_KEY must be set"):
        load_config()


@patch("requests.get")
def test_jellyfin_api_get_collections(mock_get):
    api = JellyfinAPI("http://localhost:8096/", "api-key-123")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Id": "col-1", "Name": "Marvel"}]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    cols = api.get_collections()
    assert len(cols) == 1
    assert cols[0]["Name"] == "Marvel"


@patch("requests.get")
def test_jellyfin_api_get_collection_items(mock_get):
    api = JellyfinAPI("http://localhost:8096", "api-key-123")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [{"Id": "m1", "Name": "Iron Man"}]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    items = api.get_collection_items("col-1")
    assert len(items) == 1
    assert items[0]["Name"] == "Iron Man"


def test_collection_grouper():
    grouper = CollectionGrouper(pattern=r"^(.*?):\s*")
    items = [
        {"Name": "Star Wars: Episode IV"},
        {"Name": "Star Wars: Episode V"},
        {"Name": "Standalone Movie"},
    ]
    grouped = grouper.group(items)
    assert "Star Wars" in grouped
    assert len(grouped["Star Wars"]) == 2


def test_src_groupings_functions():
    items = [
        {"Name": "Iron Man", "Overview": "MCU movie", "ProductionYear": 2008, "Tags": ["action"], "Genres": ["Action"], "Studios": [{"Name": "Marvel Studios"}]},
        {"Name": "Thor", "Overview": "MCU hero", "ProductionYear": 2011, "Tags": ["action"], "Genres": ["Action"], "Studios": ["Marvel Studios"]},
    ]
    res = create_groupings(items)
    assert "Marvel Cinematic Universe" in res
    assert "2000s Movies" in res
    assert "2010s Movies" in res

    tags = group_by_tag(items, min_items=2)
    assert "action" in tags

    genres = group_by_genre(items, min_items=2)
    assert "Action" in genres

    studios = group_by_studio(items, min_items=2)
    assert "Marvel Studios" in studios

    assert process_groupings(None, {}) == {}
    assert parse_grouping_rules("not a dict") == {}
    assert parse_grouping_rules({"collections": {"a": 1}}) == {"a": 1}
