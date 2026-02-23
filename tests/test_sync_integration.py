import pytest
from unittest.mock import patch, MagicMock
from sync import run_sync

@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.shutil.rmtree')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
def test_run_sync_basic(mock_fetch, mock_symlink, mock_rmtree, mock_exists, mock_makedirs):
    """Test run_sync with a simple genre-based group."""
    config = {
        "jellyfin_url": "http://localhost:8096",
        "api_key": "test_key",
        "target_path": "/host/target",
        "media_path_in_jellyfin": "/jf",
        "media_path_on_host": "/host",
        "groups": [
            {
                "name": "Action Movies",
                "source_type": "genre",
                "source_value": "Action",
                "sort_order": "SortName"
            }
        ]
    }
    
    # Mock items returned by Jellyfin
    mock_fetch.return_value = [
        {
            "Name": "Action Film 1",
            "Path": "/jf/movies/Action Film 1/file.mkv",
            "Id": "item1"
        }
    ]
    mock_exists.return_value = True
    
    results = run_sync(config)
    
    assert len(results) == 1
    assert results[0]["group"] == "Action Movies"
    assert results[0]["links"] == 1
    
    # Verify symlink was called with correctly translated path
    # and numbered name
    mock_symlink.assert_called_once()
    src, dst = mock_symlink.call_args[0]
    assert src == "/host/movies/Action Film 1/file.mkv"
    assert "0001 - file.mkv" in dst

@patch('sync.os.path.exists')
@patch('sync.fetch_jellyfin_items')
@patch('sync._fetch_items_for_imdb_group')
def test_run_sync_imdb(mock_imdb_fetch, mock_jf_fetch, mock_exists):
    """Test run_sync with an IMDb-list group."""
    mock_exists.return_value = True
    config = {
        "jellyfin_url": "http://localhost:8096",
        "api_key": "test_key",
        "target_path": "/host/target",
        "groups": [
            {
                "name": "IMDb List",
                "source_type": "imdb_list",
                "source_value": "ls12345",
                "sort_order": "imdb_list_order"
            }
        ]
    }
    
    mock_imdb_fetch.return_value = ([{"Name": "M", "Path": "/p", "Id": "i"}], None, 200)
    
    # Dry run to avoid filesystem mocks
    results = run_sync(config, dry_run=True)
    
    assert results[0]["links"] == 1
    mock_imdb_fetch.assert_called_once()
