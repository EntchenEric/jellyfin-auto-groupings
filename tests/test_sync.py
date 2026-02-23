import pytest
import os
import hashlib
from unittest.mock import patch
from sync import (
    _translate_path, 
    get_cover_path,
    parse_complex_query, 
    _match_condition, 
    _eval_item,
    _sort_items_in_memory,
    _match_jellyfin_items_by_provider,
    preview_group,
    _LIBRARY_CACHE,
    _is_in_season
)

def test_translate_path():
    assert _translate_path("/jf/movie.mkv", "/jf", "/host") == "/host/movie.mkv"
    assert _translate_path("/other/movie.mkv", "/jf", "/host") == "/other/movie.mkv"
    assert _translate_path("/jf/sub/movie.mkv", "/jf", "/host") == "/host/sub/movie.mkv"

def test_parse_complex_query():
    rules = parse_complex_query("Action AND NOT Comedy", "genre")
    assert len(rules) == 2
    assert rules[0] == {"operator": "AND", "type": "genre", "value": "Action"}
    assert rules[1] == {"operator": "AND NOT", "type": "genre", "value": "Comedy"}

    rules = parse_complex_query("actor:Tom Hanks OR genre:Drama", "tag")
    assert len(rules) == 2
    assert rules[0] == {"operator": "AND", "type": "actor", "value": "Tom Hanks"}
    assert rules[1] == {"operator": "OR", "type": "genre", "value": "Drama"}

def test_match_condition():
    item = {
        "Genres": ["Action", "Thriller"],
        "People": [{"Name": "Tom Cruise", "Type": "Actor"}],
        "Studios": [{"Name": "Marvel"}],
        "Tags": ["UHD"],
        "ProductionYear": 2022
    }
    
    assert _match_condition(item, "genre", "action") is True
    assert _match_condition(item, "genre", "comedy") is False
    assert _match_condition(item, "actor", "tom cruise") is True
    assert _match_condition(item, "studio", "marvel") is True
    assert _match_condition(item, "tag", "uhd") is True
    assert _match_condition(item, "year", "2022") is True

def test_sort_items_in_memory():
    items = [
        {"Name": "B", "SortName": "B", "ProductionYear": 2020, "CommunityRating": 8.0},
        {"Name": "A", "SortName": "A", "ProductionYear": 2021, "CommunityRating": 7.0},
        {"Name": "C", "SortName": "C", "ProductionYear": 2019, "CommunityRating": 9.0}
    ]
    
    sorted_name = _sort_items_in_memory(items, "SortName")
    assert sorted_name[0]["Name"] == "A"
    
    sorted_year = _sort_items_in_memory(items, "ProductionYear")
    assert sorted_year[0]["ProductionYear"] == 2021
    
    # Descending sorts in SORT_MAP
    sorted_rating = _sort_items_in_memory(items, "CommunityRating")
    assert sorted_rating[0]["CommunityRating"] == 9.0

def test_eval_item():
    item = {"Genres": ["Action"], "ProductionYear": 2020}
    
    # Simple AND
    rules = [{"operator": "AND", "type": "genre", "value": "action"}]
    assert _eval_item(item, rules) is True
    
    # AND NOT
    rules = [
        {"operator": "AND", "type": "genre", "value": "action"},
        {"operator": "AND NOT", "type": "year", "value": "2021"}
    ]
    assert _eval_item(item, rules) is True
    
    rules = [
        {"operator": "AND", "type": "genre", "value": "action"},
        {"operator": "AND NOT", "type": "year", "value": "2020"}
    ]
    assert _eval_item(item, rules) is False
    
    # OR
    rules = [
        {"operator": "AND", "type": "genre", "value": "comedy"},
        {"operator": "OR", "type": "year", "value": "2020"}
    ]
    assert _eval_item(item, rules) is True

    # Inverted first rule (NOT)
    rules = [{"operator": "NOT", "type": "genre", "value": "comedy"}]
    assert _eval_item(item, rules) is True
    
    rules = [{"operator": "NOT", "type": "genre", "value": "action"}]
    assert _eval_item(item, rules) is False

def test_library_cache():
    _LIBRARY_CACHE.clear()
    key = ("http://test", "key")
    _LIBRARY_CACHE[key] = [{"Id": "1"}]
    
    # This is just verifying the global variable is used
    assert key in _LIBRARY_CACHE
    assert _LIBRARY_CACHE[key][0]["Id"] == "1"

def test_get_cover_path(tmp_path):
    # Setup dummy paths
    target_base = str(tmp_path / "target")
    os.makedirs(os.path.join(target_base, ".covers"), exist_ok=True)
    
    # Mock __file__ to control legacy path? A bit hard.
    # Let's just test the logic for check_exists=False
    path = get_cover_path("My Group", target_base, check_exists=False)
    assert ".covers" in path
    assert path.endswith(".jpg")
    
    # Test non-existent with check_exists=True
    assert get_cover_path("Missing Group", target_base, check_exists=True) is None
    
    # Test existent in lib
    lib_path = os.path.join(target_base, ".covers", hashlib.md5(b"Existent", usedforsecurity=False).hexdigest() + ".jpg")
    with open(lib_path, "w") as f:
        f.write("test")
    assert get_cover_path("Existent", target_base, check_exists=True) == lib_path

@patch('sync.fetch_jellyfin_items')
def test_match_jellyfin_items_by_provider(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = [
        {"Id": "1", "Name": "M1", "ProviderIds": {"Tmdb": "101"}},
        {"Id": "2", "Name": "M2", "ProviderIds": {"Tmdb": "202"}}
    ]
    items, _err, _code = _match_jellyfin_items_by_provider(
        ["101"], "Tmdb", "tmdb_list_order", "tmdb_list_order", "http://jf", "key", "Group"
    )
    assert len(items) == 1
    assert items[0]["Name"] == "M1"

@patch('sync.fetch_jellyfin_items')
def test_preview_group(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = [{"Name": "M1", "Genres": ["Action"]}]
    
    # Metadata group
    items, _err, code = preview_group("genre", "Action", "http://jf", "key")
    assert code == 200
    assert len(items) == 1
    
    # Complex group (AND)
    _LIBRARY_CACHE.clear() # Ensure _fetch_full_library calls mock
    items, _err, code = preview_group("genre", "Action AND NOT Comedy", "http://jf", "key")
    assert code == 200
    assert len(items) == 1

@patch('sync.fetch_jellyfin_items')
def test_preview_group_fetch_error(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.side_effect = Exception("Network error")
    _items, err, code = preview_group("genre", "Action", "http://jf", "key")
    assert code == 500
    assert "Internal error" in err

def test_parse_complex_query_with_prefixes():
    # Mix of default and specific types
    rules = parse_complex_query("Action AND actor:Tom Hanks AND studio:Marvel", "genre")
    assert rules[0] == {"operator": "AND", "type": "genre", "value": "Action"}
    assert rules[1] == {"operator": "AND", "type": "actor", "value": "Tom Hanks"}
    assert rules[2] == {"operator": "AND", "type": "studio", "value": "Marvel"}

def test_eval_item_multiple_or():
    item = {"Genres": ["Comedy"]}
    rules = [
        {"operator": "AND", "type": "genre", "value": "action"},
        {"operator": "OR", "type": "genre", "value": "drama"},
        {"operator": "OR", "type": "genre", "value": "comedy"}
    ]
    assert _eval_item(item, rules) is True

def test_match_condition_variants():
    item = {
        "Genres": ["Action"],
        "People": [{"Name": "A", "Type": "Actor"}],
        "Studios": [{"Name": "S"}],
        "Tags": ["T"],
        "ProductionYear": 2020
    }
    # Test normalization and missing fields
    # Note: _match_condition expects r_val to be pre-normalized (lower/stripped)
    assert _match_condition(item, "genre", "action") is True
    assert _match_condition({}, "genre", "action") is False
    assert _match_condition(item, "unknown", "val") is False
    assert _match_condition(item, "actor", "b") is False

@patch('sync.fetch_jellyfin_items')
def test_match_by_provider_empty_library(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = []
    items, _err, code = _match_jellyfin_items_by_provider(
        ["101"], "Tmdb", "tmdb_list_order", "tmdb_list_order", "http://jf", "key", "Group"
    )
    assert items == []
    assert code == 200

def test_translate_path_edge_cases():
    # Paths that share a string prefix but are completely different directories
    assert _translate_path("/jelly/movie", "/jell", "/mnt/host") == "/jelly/movie"
    # Root path (normpath strips trailing slash)
    assert _translate_path("/jf/", "/jf", "/host") == "/host"

def test_sort_items_missing_field():
    items = [{"Name": "A"}, {"Name": "B"}]
    # Sorting by missing field should use Name as fallback
    sorted_items = _sort_items_in_memory(items, "ProductionYear")
    assert len(sorted_items) == 2

@patch('sync.fetch_jellyfin_items')
def test_match_jellyfin_items_no_match(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = [
        {"Id": "1", "Name": "M1", "ProviderIds": {"Tmdb": "202"}}
    ]
    # Should return empty if no match
    items, _err, _code = _match_jellyfin_items_by_provider(
        ["101"], "Tmdb", "tmdb_list_order", "tmdb_list_order", "http://jf", "key", "Group"
    )
    assert len(items) == 0

def test_sort_items_rating():
    items = [
        {"Name": "A", "CommunityRating": 5.0},
        {"Name": "B", "CommunityRating": 9.0}
    ]
    sorted_items = _sort_items_in_memory(items, "CommunityRating")
    assert sorted_items[0]["CommunityRating"] == 9.0

def test_sort_items_unknown():
    items = [{"Name": "B"}, {"Name": "A"}]
    # Should return as-is (B then A)
    sorted_items = _sort_items_in_memory(items, "UnknownField")
    assert sorted_items[0]["Name"] == "B"

def test_sort_items_missing_values_logic():
    items = [
        {"SortName": "A"},
        {"SortName": None}
    ]
    # Ascending (SortName)
    res_asc = _sort_items_in_memory(items, "SortName")
    assert res_asc[0]["SortName"] == "A"
    assert res_asc[1]["SortName"] is None

    items_year = [
        {"ProductionYear": 2020},
        {"ProductionYear": None}
    ]
    # Descending (ProductionYear)
    res_desc = _sort_items_in_memory(items_year, "ProductionYear")
    assert res_desc[0]["ProductionYear"] == 2020
    assert res_desc[1]["ProductionYear"] is None

def test_is_in_season():
    from unittest.mock import MagicMock
    with patch('sync.datetime') as mock_datetime:
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now
        
        # Case 1: Within year window
        mock_now.strftime.return_value = "07-15"
        assert _is_in_season("06-01", "09-01") is True
        
        mock_now.strftime.return_value = "05-15"
        assert _is_in_season("06-01", "09-01") is False
        
        # Case 2: Crossing year window
        mock_now.strftime.return_value = "12-15"
        assert _is_in_season("12-01", "01-01") is True
        
        mock_now.strftime.return_value = "01-15"
        assert _is_in_season("12-01", "01-01") is False
        
        mock_now.strftime.return_value = "01-01"
        assert _is_in_season("12-01", "01-01") is False # Exclusive end
        
        # Case 3: Invalid types
        assert _is_in_season(None, "01-01") is True # Defaults to True
