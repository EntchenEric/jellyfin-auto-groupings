import pytest
import requests
from sync import run_sync
from jellyfin import fetch_jellyfin_items

from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_filesystem():
    """Mock filesystem checks to avoid dependency on real files."""
    with patch('sync.os.path.exists', return_value=True), \
         patch('sync.os.makedirs'), \
         patch('sync.os.symlink'), \
         patch('sync.shutil.rmtree'):
        yield

def test_mock_server_up(virtual_jellyfin):
    """Verify the mock server is actually reachable."""
    response = requests.get(f"{virtual_jellyfin}/System/Info")
    assert response.status_code == 200
    assert response.json()["ServerName"] == "Virtual-Jellyfin-Mock"

def test_sync_with_diverse_data(virtual_jellyfin):
    """Test sync with the expanded dataset from virtual_jellyfin."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "any_valid_key",
        "target_path": "/tmp/target",
        "media_path_in_jellyfin": "/media",
        "media_path_on_host": "/tmp/media",
        "groups": [
            {
                "name": "Action Classics",
                "source_type": "complex",
                "source_value": "genre:Action AND year:<2000",
                "sort_order": "SortName"
            },
            {
                "name": "Modern Sci-Fi",
                "source_type": "complex",
                "source_value": "genre:Sci-Fi AND year:>2000",
                "sort_order": "SortName"
            }
        ]
    }
    
    # Action classics: The Matrix (1999) [Action, Sci-Fi]
    # Modern Sci-Fi: Inception (2010), Interstellar (2014)
    
    results = run_sync(config, dry_run=True)
    
    action_classics = next(r for r in results if r["group"] == "Action Classics")
    modern_scifi = next(r for r in results if r["group"] == "Modern Sci-Fi")
    
    assert action_classics["links"] >= 1
    assert modern_scifi["links"] >= 2

def test_sync_robustness_missing_metadata(virtual_jellyfin):
    """Test sync handles items with missing metadata gracefully."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "any_valid_key",
        "target_path": "/tmp/target",
        "groups": [
            {
                "name": "All Movies",
                "source_type": "general",
                "source_value": "all",
                "sort_order": "SortName"
            }
        ]
    }
    
    # This should not crash even with items like "Empty Item" or "Movie Without Year"
    results = run_sync(config, dry_run=True)
    assert len(results) == 1
    # We have ~70 movies + some edge cases. Total items ~140.
    assert results[0]["links"] >= 70

def test_sync_large_volume(virtual_jellyfin):
    """Test sync with a large volume of items (1000+)."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "LARGE_RESPONSE_KEY",
        "target_path": "/tmp/target",
        "groups": [
            {
                "name": "Large Group",
                "source_type": "general",
                "source_value": "all",
                "sort_order": "SortName"
            }
        ]
    }
    
    results = run_sync(config, dry_run=True)
    # 106 unique items * 40 = 4240 items.
    assert results[0]["links"] >= 4000

def test_sync_complex_nested_queries(virtual_jellyfin):
    """Test deep nested logical queries."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "any_valid_key",
        "target_path": "/tmp/target",
        "groups": [
            {
                "name": "Complex Filter",
                "source_type": "complex",
                "source_value": "(genre:Action OR genre:Crime) AND NOT genre:Sci-Fi",
                "sort_order": "SortName"
            }
        ]
    }
    
    results = run_sync(config, dry_run=True)
    assert results[0]["links"] > 0

def test_sync_chaos_robustness(virtual_jellyfin):
    """Test sync handles 'Digital Chaos' scenarios (duplicates, emojis, malformed data)."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "any_valid_key",
        "target_path": "/tmp/target",
        "groups": [
            {
                "name": "Chaos Group",
                "source_type": "general",
                "source_value": "all",
                "sort_order": "SortName"
            }
        ]
    }
    
    # This should not crash despite:
    # - Duplicate ID "chaos_1"
    # - Malformed Year "Nineteen Ninety Nine"
    # - Emoji/RTL Titles
    # - NULL Path
    # - Invalid Item Type
    results = run_sync(config, dry_run=True)
    assert len(results) == 1
    assert results[0]["links"] > 0

def test_sync_mixed_character_encodings(virtual_jellyfin):
    """Test handles mixed LTR/RTL and emoji titles without encoding errors."""
    config = {
        "jellyfin_url": virtual_jellyfin,
        "api_key": "any_valid_key",
        "target_path": "/tmp/target",
        "groups": [
            {
                "name": "International",
                "source_type": "complex",
                "source_value": "year:>2020",
                "sort_order": "SortName"
            }
        ]
    }
    
    results = run_sync(config, dry_run=True)
    assert results[0]["links"] > 0
