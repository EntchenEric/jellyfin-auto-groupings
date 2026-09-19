import pytest
import requests
from unittest.mock import MagicMock
from jellyfin_auto_groupings.client import JellyfinClient, JellyfinAPIError
from jellyfin_auto_groupings.grouper import CollectionGrouper
from jellyfin_auto_groupings.cli import main


def test_client_empty_item_ids():
    client = JellyfinClient("http://localhost:8096", "test-token")
    assert client.create_collection("Test", []) == {}
    assert client.add_to_collection("col1", []) == {}
    assert client.remove_from_collection("col1", []) == {}


def test_client_api_error_handling(mocker):
    mock_get = mocker.patch("requests.Session.get")
    mock_get.return_value.raise_for_status.side_effect = Exception("Connection refused")
    
    client = JellyfinClient("http://localhost:8096", "test-token")
    with pytest.raises(JellyfinAPIError, match="API request GET /Items failed"):
        client.get_items()


def test_cli_error_exit(mocker, capsys):
    mocker.patch("jellyfin_auto_groupings.cli.JellyfinClient", side_effect=JellyfinAPIError("Auth failed"))
    with pytest.raises(SystemExit) as exc_info:
        main(["--server", "http://localhost:8096", "--api-key", "invalid"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: Auth failed" in captured.err


def test_update_item_sort_name_raises_on_failure(mocker):
    mock_post = mocker.patch("requests.Session.post")
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
    client = JellyfinClient("http://localhost:8096", "test-token")
    with pytest.raises(requests.exceptions.ConnectionError, match="Connection failed"):
        client.update_item_sort_name("item1", "Sorted Name")
