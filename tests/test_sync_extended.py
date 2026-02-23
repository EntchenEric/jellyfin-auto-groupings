import pytest
import os
from unittest.mock import patch, MagicMock
from sync import run_sync, preview_group

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
@patch('sync.fetch_tmdb_list')
def test_run_sync_tmdb(mock_tmdb, mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "tmdb_api_key": "tmdb_key",
        "groups": [
            {
                "name": "TMDB List",
                "source_type": "tmdb_list",
                "source_value": "123",
                "sort_order": "tmdb_list_order"
            }
        ]
    }
    mock_tmdb.return_value = ["101"]
    mock_jf_fetch.return_value = [
        {"Name": "M1", "Path": "/p1", "ProviderIds": {"Tmdb": "101"}}
    ]
    _mock_exists.return_value = True # Host path exists
    
    results = run_sync(config)
    assert len(results) > 0
    assert results[0]["links"] == 1
    _mock_symlink.assert_called_once()

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
@patch('sync.fetch_anilist_list')
def test_run_sync_anilist(mock_anilist, mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": [
            {
                "name": "AniList",
                "source_type": "anilist_list",
                "source_value": "user/completed",
                "sort_order": "anilist_list_order"
            }
        ]
    }
    mock_anilist.return_value = [12345]
    mock_jf_fetch.return_value = [
        {"Name": "A1", "Path": "/p1", "ProviderIds": {"AniList": "12345"}}
    ]
    _mock_exists.return_value = True
    
    results = run_sync(config)
    assert results[0]["links"] == 1

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.path.isdir')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
@patch('sync.fetch_trakt_list')
def test_run_sync_trakt(mock_trakt, mock_jf_fetch, _mock_symlink, _mock_isdir, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "trakt_client_id": "trakt_id",
        "groups": [
            {
                "name": "Trakt",
                "source_type": "trakt_list",
                "source_value": "user/list",
                "sort_order": "trakt_list_order"
            }
        ]
    }
    mock_trakt.return_value = ["tt123"]
    mock_jf_fetch.return_value = [
        {"Name": "T1", "Path": "/p1", "ProviderIds": {"Imdb": "tt123"}}
    ]
    _mock_exists.return_value = True
    _mock_isdir.return_value = True
    
    results = run_sync(config)
    assert results[0]["links"] == 1

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
@patch('sync.fetch_mal_list')
def test_run_sync_mal(mock_mal, mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "mal_client_id": "mal_id",
        "groups": [
            {
                "name": "MAL",
                "source_type": "mal_list",
                "source_value": "user",
                "sort_order": "mal_list_order"
            }
        ]
    }
    mock_mal.return_value = [54321]
    mock_jf_fetch.return_value = [
        {"Name": "M1", "Path": "/p1", "ProviderIds": {"Mal": "54321"}}
    ]
    _mock_exists.return_value = True
    
    results = run_sync(config)
    assert results[0]["links"] == 1

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
@patch('sync.fetch_letterboxd_list')
def test_run_sync_letterboxd(mock_lb, mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": [
            {
                "name": "LB",
                "source_type": "letterboxd_list",
                "source_value": "https://letterboxd.com/user/list/my-list",
                "sort_order": "letterboxd_list_order"
            }
        ]
    }
    mock_lb.return_value = ["tt111"]
    mock_jf_fetch.return_value = [
        {"Name": "L1", "Path": "/p1", "ProviderIds": {"Imdb": "tt111"}}
    ]
    _mock_exists.return_value = True
    
    results = run_sync(config)
    assert results[0]["links"] == 1

def test_run_sync_invalid_group():
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": ["not_a_dict"]
    }
    # Should skip the string and continue
    with patch('sync.os.path.exists', return_value=True):
         results = run_sync(config)
    assert results == []

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
def test_run_sync_complex(mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": [
            {
                "name": "Complex",
                "source_type": "complex",
                "rules": [{"operator": "AND", "type": "genre", "value": "Action"}]
            }
        ]
    }
    mock_jf_fetch.return_value = [
        {"Name": "C1", "Path": "/p1", "Genres": ["Action"]}
    ]
    _mock_exists.return_value = True
    
    results = run_sync(config)
    assert results[0]["links"] == 1

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
def test_run_sync_dry_run(mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": [
            {
                "name": "G1",
                "source_type": "genre",
                "source_value": "Action"
            }
        ]
    }
    mock_jf_fetch.return_value = [
        {"Name": "M1", "Path": "/p1", "Genres": ["Action"]}
    ]
    _mock_exists.return_value = True
    
    results = run_sync(config, dry_run=True)
    assert results[0]["links"] == 1
    _mock_symlink.assert_not_called()
    _mock_makedirs.assert_not_called()
    _mock_rmtree.assert_not_called()

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.os.path.exists')
@patch('sync.os.symlink')
@patch('sync.fetch_jellyfin_items')
def test_run_sync_selective(mock_jf_fetch, _mock_symlink, _mock_exists, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "groups": [
            {"name": "G1", "source_type": "genre", "source_value": "Action"},
            {"name": "G2", "source_type": "genre", "source_value": "Comedy"}
        ]
    }
    mock_jf_fetch.return_value = [{"Name": "M1", "Path": "/p1", "Genres": ["Action"]}]
    _mock_exists.return_value = True
    
    # Sync only G1
    results = run_sync(config, group_names=["G1"])
    assert len(results) == 1
    assert results[0]["group"] == "G1"

def test_run_sync_missing_group(tmp_path):
    target = tmp_path / "target"
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": str(target),
        "groups": [{"name": "G1"}]
    }
    results = run_sync(config, group_names=["NonExistent"])
    assert results == []

@patch('sync.shutil.rmtree')
@patch('sync.os.makedirs')
@patch('sync.fetch_tmdb_list')
def test_run_sync_tmdb_error(mock_tmdb, _mock_makedirs, _mock_rmtree):
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": "/target",
        "tmdb_api_key": "tmdb_key",
        "groups": [{"name": "G1", "source_type": "tmdb_list", "source_value": "123"}]
    }
    mock_tmdb.side_effect = Exception("TMDB Unavailable")
    with patch('sync.os.path.exists', return_value=True):
        results = run_sync(config)
    assert results[0]["error"] is not None

@patch('sync._fetch_full_library')
def test_preview_group_complex_error(mock_full):
    mock_full.return_value = (None, "Some error", 500)
    _items, err, code = preview_group("genre", "A AND B", "http://jf", "key")
    assert code == 500
    assert err == "Some error"

@patch('sync.fetch_tmdb_list')
def test_fetch_items_tmdb_no_key(mock_tmdb):
    from sync import _fetch_items_for_tmdb_group
    _items, err, code = _fetch_items_for_tmdb_group("G", "val", "order", "url", "key", "")
    assert code == 400
    assert "TMDb API Key not set" in err

@patch('sync.fetch_tmdb_list')
def test_fetch_items_tmdb_empty(mock_tmdb):
    from sync import _fetch_items_for_tmdb_group
    mock_tmdb.return_value = []
    items, _err, code = _fetch_items_for_tmdb_group("G", "val", "order", "url", "key", "tmdb_key")
    assert code == 200
    assert items == []

@patch('sync.fetch_anilist_list')
def test_fetch_items_anilist_error(mock_ani):
    from sync import _fetch_items_for_anilist_group
    mock_ani.side_effect = Exception("AniList Error")
    _items, err, code = _fetch_items_for_anilist_group("G", "user/status", "order", "url", "key")
    assert code == 400
    assert "AniList fetch error" in err

@patch('sync.fetch_mal_list')
def test_fetch_items_mal_no_id(mock_mal):
    from sync import _fetch_items_for_mal_group
    _items, err, code = _fetch_items_for_mal_group("G", "val", "order", "url", "key", "")
    assert code == 400
    assert "MyAnimeList Client ID not set" in err

@patch('sync.fetch_mal_list')
@patch('sync._fetch_full_library')
def test_fetch_items_mal_with_status(mock_full, mock_mal):
    from sync import _fetch_items_for_mal_group
    mock_mal.return_value = [1]
    mock_full.return_value = ([], None, 200)
    _items, _err, code = _fetch_items_for_mal_group("G", "user/completed", "order", "http://jf", "key", "id")
    assert code == 200
    assert mock_mal.called
    args = mock_mal.call_args[0]
    assert args[2] == "completed"

@patch('sync.fetch_mal_list')
def test_fetch_items_mal_error(mock_mal):
    from sync import _fetch_items_for_mal_group
    mock_mal.side_effect = Exception("MAL Error")
    _items, err, code = _fetch_items_for_mal_group("G", "user", "order", "url", "key", "id")
    assert code == 400
    assert "MAL fetch error" in err

@patch('sync.fetch_mal_list')
def test_fetch_items_mal_empty(mock_mal):
    from sync import _fetch_items_for_mal_group
    mock_mal.return_value = []
    items, _err, code = _fetch_items_for_mal_group("G", "user", "order", "http://jf", "key", "id")
    assert code == 200
    assert items == []

@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_error(mock_trakt):
    from sync import _fetch_items_for_trakt_group
    mock_trakt.side_effect = Exception("Trakt Fail")
    _items, err, code = _fetch_items_for_trakt_group("G", "val", "order", "http://jf", "key", "cli")
    assert code == 400
    assert "Trakt fetch error" in err

@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_empty(mock_trakt):
    from sync import _fetch_items_for_trakt_group
    mock_trakt.return_value = []
    items, _err, code = _fetch_items_for_trakt_group("G", "val", "order", "http://jf", "key", "cli")
    assert code == 200
    assert items == []
