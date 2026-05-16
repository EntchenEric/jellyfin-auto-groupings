import os
import hashlib
import requests
import pytest
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
    _is_in_season,
    run_cleanup_broken_symlinks,
    _fetch_items_for_recommendations_group,
    _process_collection_group,
    _fetch_items_for_letterboxd_group,
    _fetch_items_for_imdb_group,
    _fetch_items_for_trakt_group,
    _fetch_items_for_tmdb_group,
    _fetch_items_for_anilist_group,
    _fetch_items_for_mal_group,
    _fetch_full_library,
    _fetch_items_for_complex_group,
    _fetch_items_for_metadata_group,
    _process_group,
    run_sync,
    _filter_by_watch_state,
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
    lib_path = os.path.join(target_base, ".covers", hashlib.md5(
        b"Existent", usedforsecurity=False).hexdigest() + ".jpg")
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
def test_match_jellyfin_items_with_watch_state(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = [
        {"Id": "1", "Name": "Played", "ProviderIds": {"Tmdb": "101"}, "UserData": {"Played": True}},
        {"Id": "2", "Name": "Unplayed", "ProviderIds": {"Tmdb": "102"}, "UserData": {"Played": False}}
    ]
    # All
    items, _, _ = _match_jellyfin_items_by_provider(
        ["101", "102"], "Tmdb", "SortName", "SortName", "http://jf", "key", "Group", ""
    )
    assert len(items) == 2
    # Unwatched
    items, _, _ = _match_jellyfin_items_by_provider(
        ["101", "102"], "Tmdb", "SortName", "SortName", "http://jf", "key", "Group", "unwatched"
    )
    assert len(items) == 1
    assert items[0]["Name"] == "Unplayed"
    # Watched
    items, _, _ = _match_jellyfin_items_by_provider(
        ["101", "102"], "Tmdb", "SortName", "SortName", "http://jf", "key", "Group", "watched"
    )
    assert len(items) == 1
    assert items[0]["Name"] == "Played"


@patch('sync.fetch_jellyfin_items')
def test_preview_group(mock_jf):
    _LIBRARY_CACHE.clear()
    mock_jf.return_value = [{"Name": "M1", "Genres": ["Action"]}]
    # Metadata group
    items, _err, code = preview_group("genre", "Action", "http://jf", "key")
    assert code == 200
    assert len(items) == 1
    # Complex group (AND)
    _LIBRARY_CACHE.clear()  # Ensure _fetch_full_library calls mock
    items, _err, code = preview_group("genre", "Action AND NOT Comedy", "http://jf", "key")
    assert code == 200
    assert len(items) == 1


@patch('sync.fetch_jellyfin_items')
def test_fetch_items_for_metadata_group_with_watch_state(mock_jf):
    mock_jf.return_value = [{"Name": "M1"}]
    # Test 'unwatched' calls fetch with Filters=IsUnplayed
    _fetch_items_for_metadata_group("Group", "genre", "Action", "SortName", "http://jf", "key", "unwatched")
    args, _ = mock_jf.call_args
    assert args[2]["Filters"] == "IsUnplayed"
    # Test 'watched' calls fetch with Filters=IsPlayed
    _fetch_items_for_metadata_group("Group", "genre", "Action", "SortName", "http://jf", "key", "watched")
    args, _ = mock_jf.call_args
    assert args[2]["Filters"] == "IsPlayed"
    # Test default doesn't have Filters
    _fetch_items_for_metadata_group("Group", "genre", "Action", "SortName", "http://jf", "key", "")
    args, _ = mock_jf.call_args
    assert "Filters" not in args[2]


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


def test_translate_path_normalization():
    # Redundant separators in path should not affect the result
    assert _translate_path("/jf//movie.mkv", "/jf", "/host") == "/host/movie.mkv"
    # Trailing slash on root should work correctly
    assert _translate_path("/jf/movie.mkv", "/jf/", "/host") == "/host/movie.mkv"
    # Both path and root have trailing slashes
    assert _translate_path("/jf//sub/", "/jf/", "/host") == "/host/sub"


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
        assert _is_in_season("12-01", "01-01") is False  # Exclusive end
        # Case 3: Invalid types
        assert _is_in_season(None, "01-01") is True  # Defaults to True


# ---------------------------------------------------------------------------
# run_cleanup_broken_symlinks
# ---------------------------------------------------------------------------

def test_run_cleanup_broken_symlinks_invalid_path():
    assert run_cleanup_broken_symlinks({"target_path": ""}) == 0
    assert run_cleanup_broken_symlinks({"target_path": "/nonexistent"}) == 0


# ---------------------------------------------------------------------------
# _fetch_items_for_recommendations_group
# ---------------------------------------------------------------------------

def test_fetch_items_recommendations_no_api_key():
    items, error, code = _fetch_items_for_recommendations_group(
        "Rec", "user1", "SortName", "http://jf", "key", None
    )
    assert code == 400
    assert "TMDb API Key not set" in error


def test_fetch_items_recommendations_no_source_value():
    items, error, code = _fetch_items_for_recommendations_group(
        "Rec", "", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 400
    assert "User ID must be selected" in error


@patch('sync.get_user_recent_items')
def test_fetch_items_recommendations_no_tmdb_ids(mock_recent):
    mock_recent.return_value = [{"ProviderIds": {}, "Type": "Movie"}]
    items, error, code = _fetch_items_for_recommendations_group(
        "Rec", "user1", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 200
    assert items == []


@patch('sync.get_user_recent_items')
def test_fetch_items_recommendations_exception(mock_recent):
    mock_recent.side_effect = Exception("Jellyfin down")
    items, error, code = _fetch_items_for_recommendations_group(
        "Rec", "user1", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 400
    assert "Recommendations fetch error" in error


# ---------------------------------------------------------------------------
# _process_collection_group
# ---------------------------------------------------------------------------

@patch('sync.find_collection_by_name')
@patch('sync.add_to_collection')
def test_process_collection_group_dry_run(mock_add, mock_find):
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", "/target", dry_run=True, auto_set_library_covers=False
    )
    assert result["links"] == 1
    assert "items" in result


def test_process_collection_group_no_ids():
    result = _process_collection_group(
        "Group", [], "http://jf", "key", "/target", dry_run=False, auto_set_library_covers=False
    )
    assert result["links"] == 0
    assert "No item IDs" in result["error"]


@patch('sync.find_collection_by_name')
def test_process_collection_group_error(mock_find):
    mock_find.side_effect = Exception("Collection error")
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", "/target", dry_run=False, auto_set_library_covers=False
    )
    assert result["links"] == 0
    assert "Collection error" in result["error"]


# ---------------------------------------------------------------------------
# _fetch_items_for_letterboxd_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_letterboxd_list')
def test_fetch_items_letterboxd_error(mock_fetch):
    mock_fetch.side_effect = Exception("Network error")
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key"
    )
    assert code == 400
    assert "Letterboxd fetch error" in error


@patch('sync.fetch_letterboxd_list')
@patch('sync._fetch_full_library')
def test_fetch_items_letterboxd_empty_list(mock_lib, mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert items == []


@patch('sync.fetch_letterboxd_list')
@patch('sync._fetch_full_library')
def test_fetch_items_letterboxd_watch_state(mock_lib, mock_fetch):
    mock_fetch.return_value = ["tt123"]
    mock_lib.return_value = [
        {"Id": "1", "ProviderIds": {"Imdb": "tt123"}, "UserData": {"Played": True}}
    ], None, 200
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key", watch_state="unwatched"
    )
    assert code == 200
    assert items == []


@patch('sync.fetch_letterboxd_list')
@patch('sync._fetch_full_library')
def test_fetch_items_letterboxd_tmdb_match(mock_lib, mock_fetch):
    mock_fetch.return_value = ["456"]
    mock_lib.return_value = [
        {"Id": "1", "ProviderIds": {"Tmdb": "456"}}
    ], None, 200
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync.fetch_letterboxd_list')
@patch('sync._fetch_full_library')
def test_fetch_items_letterboxd_non_list_order(mock_lib, mock_fetch):
    mock_fetch.return_value = ["tt123", "tt123"]
    mock_lib.return_value = [
        {"Id": "1", "ProviderIds": {"Imdb": "tt123"}}
    ], None, 200
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert len(items) == 1


# ---------------------------------------------------------------------------
# _fetch_items_for_imdb_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_imdb_list')
def test_fetch_items_imdb_error(mock_fetch):
    mock_fetch.side_effect = Exception("IMDb down")
    items, error, code = _fetch_items_for_imdb_group(
        "IMDb", "list_id", "SortName", "http://jf", "key"
    )
    assert code == 400
    assert "IMDb fetch error" in error


@patch('sync.fetch_imdb_list')
def test_fetch_items_imdb_empty(mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_imdb_group(
        "IMDb", "list_id", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert items == []


# ---------------------------------------------------------------------------
# _fetch_items_for_trakt_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_no_client_id(mock_fetch):
    items, error, code = _fetch_items_for_trakt_group(
        "Trakt", "user/list", "SortName", "http://jf", "key", None
    )
    assert code == 400
    assert "Trakt Client ID not set" in error


@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_error(mock_fetch):
    mock_fetch.side_effect = Exception("Trakt down")
    items, error, code = _fetch_items_for_trakt_group(
        "Trakt", "user/list", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 400
    assert "Trakt fetch error" in error


@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_empty(mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_trakt_group(
        "Trakt", "user/list", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 200
    assert items == []


# ---------------------------------------------------------------------------
# _fetch_items_for_tmdb_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_tmdb_list')
def test_fetch_items_tmdb_error(mock_fetch):
    mock_fetch.side_effect = Exception("TMDb down")
    items, error, code = _fetch_items_for_tmdb_group(
        "TMDb", "123", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 400
    assert "TMDb fetch error" in error


@patch('sync.fetch_tmdb_list')
def test_fetch_items_tmdb_empty(mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_tmdb_group(
        "TMDb", "123", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 200
    assert items == []


# ---------------------------------------------------------------------------
# _fetch_items_for_anilist_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_anilist_list')
def test_fetch_items_anilist_error(mock_fetch):
    mock_fetch.side_effect = Exception("AniList down")
    items, error, code = _fetch_items_for_anilist_group(
        "AniList", "user", "SortName", "http://jf", "key"
    )
    assert code == 400
    assert "AniList fetch error" in error


@patch('sync.fetch_anilist_list')
def test_fetch_items_anilist_empty(mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_anilist_group(
        "AniList", "user", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert items == []


# ---------------------------------------------------------------------------
# _fetch_items_for_mal_group
# ---------------------------------------------------------------------------

@patch('sync.fetch_mal_list')
def test_fetch_items_mal_error(mock_fetch):
    mock_fetch.side_effect = Exception("MAL down")
    items, error, code = _fetch_items_for_mal_group(
        "MAL", "user", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 400
    assert "MAL fetch error" in error


@patch('sync.fetch_mal_list')
def test_fetch_items_mal_empty(mock_fetch):
    mock_fetch.return_value = []
    items, error, code = _fetch_items_for_mal_group(
        "MAL", "user", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 200
    assert items == []


# ---------------------------------------------------------------------------
# sync.py edge-case coverage additions
# ---------------------------------------------------------------------------


def test_translate_path_valueerror():
    # os.path.commonpath raises ValueError for mixed abs/relative paths
    assert _translate_path("/foo", ".", "/host") == "/foo"


def test_filter_by_watch_state():
    unwatched = {"UserData": {"Played": False}}
    watched = {"UserData": {"Played": True}}
    no_data = {}

    assert _filter_by_watch_state([unwatched, watched, no_data], "unwatched") == [unwatched, no_data]
    assert _filter_by_watch_state([unwatched, watched, no_data], "watched") == [watched]
    assert _filter_by_watch_state([unwatched, watched, no_data], "all") == [unwatched, watched, no_data]


def test_get_cover_path_no_target_base():
    path = get_cover_path("Group", "", check_exists=False)
    assert "config/covers" in path


@patch('sync.os.path.exists')
def test_get_cover_path_legacy_exists(mock_exists):
    mock_exists.side_effect = lambda p: "config/covers" in p
    path = get_cover_path("LegacyGroup", "/some/target", check_exists=True)
    assert "config/covers" in path


@patch('sync.fetch_jellyfin_items')
def test_fetch_full_library_pagination(mock_fetch):
    _LIBRARY_CACHE.clear()
    page1 = [{"Id": str(i)} for i in range(500)]
    page2 = [{"Id": "500"}]
    mock_fetch.side_effect = [page1, page2]
    items, error, code = _fetch_full_library("http://jf", "key", "Group")
    assert len(items) == 501
    assert code == 200


@patch('sync.fetch_jellyfin_items')
def test_fetch_full_library_request_error(mock_fetch):
    _LIBRARY_CACHE.clear()
    mock_fetch.side_effect = requests.exceptions.ConnectionError("fail")
    items, error, code = _fetch_full_library("http://jf", "key", "Group")
    assert code == 500
    assert "Jellyfin connection error" in error


@patch('sync.fetch_jellyfin_items')
def test_fetch_full_library_unexpected_error(mock_fetch):
    _LIBRARY_CACHE.clear()
    mock_fetch.side_effect = TypeError("bad")
    items, error, code = _fetch_full_library("http://jf", "key", "Group")
    assert code == 500
    assert "Internal error" in error


@patch('sync._fetch_full_library')
def test_match_jellyfin_items_by_provider_library_error(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = ([], "Lib error", 503)
    items, error, code = _match_jellyfin_items_by_provider(
        ["101"], "Tmdb", "tmdb_list_order", "tmdb_list_order", "http://jf", "key", "Group"
    )
    assert code == 503
    assert error == "Lib error"


@patch('sync._match_jellyfin_items_by_provider')
@patch('sync.fetch_imdb_list')
def test_fetch_items_imdb_normal(mock_fetch, mock_match):
    mock_fetch.return_value = ["tt123"]
    mock_match.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_imdb_group(
        "IMDb", "list_id", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync._match_jellyfin_items_by_provider')
@patch('sync.fetch_trakt_list')
def test_fetch_items_trakt_normal(mock_fetch, mock_match):
    mock_fetch.return_value = ["tt123"]
    mock_match.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_trakt_group(
        "Trakt", "user/list", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync._match_jellyfin_items_by_provider')
@patch('sync.fetch_tmdb_list')
def test_fetch_items_tmdb_normal(mock_fetch, mock_match):
    mock_fetch.return_value = ["101"]
    mock_match.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_tmdb_group(
        "TMDb", "123", "SortName", "http://jf", "key", "api_key"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync._match_jellyfin_items_by_provider')
@patch('sync.fetch_anilist_list')
def test_fetch_items_anilist_normal(mock_fetch, mock_match):
    mock_fetch.return_value = [12345]
    mock_match.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_anilist_group(
        "AniList", "user", "SortName", "http://jf", "key"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync._match_jellyfin_items_by_provider')
@patch('sync.fetch_mal_list')
def test_fetch_items_mal_normal(mock_fetch, mock_match):
    mock_fetch.return_value = ["mal123"]
    mock_match.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_mal_group(
        "MAL", "user", "SortName", "http://jf", "key", "client_id"
    )
    assert code == 200
    assert len(items) == 1


@patch('sync._fetch_full_library')
@patch('sync.fetch_letterboxd_list')
def test_fetch_items_letterboxd_library_error(mock_fetch, mock_lib):
    mock_fetch.return_value = ["tt123"]
    mock_lib.return_value = ([], "Lib error", 503)
    items, error, code = _fetch_items_for_letterboxd_group(
        "LB", "user/list", "SortName", "http://jf", "key"
    )
    assert code == 503
    assert error == "Lib error"


@patch('sync._fetch_full_library')
def test_complex_group_empty_rules(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_complex_group(
        "Group", [], "SortName", "http://jf", "key"
    )
    assert items == []


@patch('sync._fetch_full_library')
def test_complex_group_malformed_rule(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_complex_group(
        "Group", [{"type": 123, "value": None}], "SortName", "http://jf", "key"
    )
    assert items == []


@patch('sync._fetch_full_library')
def test_complex_group_watch_state(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = (
        [
            {"Name": "Played", "Genres": ["Action"], "UserData": {"Played": True}},
            {"Name": "Unplayed", "Genres": ["Action"], "UserData": {"Played": False}},
        ],
        None,
        200,
    )
    items, error, code = _fetch_items_for_complex_group(
        "Group",
        [{"operator": "AND", "type": "genre", "value": "action"}],
        "SortName",
        "http://jf",
        "key",
        watch_state="unwatched",
    )
    assert len(items) == 1
    assert items[0]["Name"] == "Unplayed"


@patch('sync.fetch_jellyfin_items')
def test_fetch_items_metadata_request_error(mock_fetch):
    mock_fetch.side_effect = requests.exceptions.ConnectionError("fail")
    items, error, code = _fetch_items_for_metadata_group(
        "Group", "genre", "Action", "SortName", "http://jf", "key"
    )
    assert code == 500
    assert "Jellyfin connection error" in error


@patch('sync.fetch_jellyfin_items')
def test_fetch_items_metadata_unexpected_error(mock_fetch):
    mock_fetch.side_effect = TypeError("bad")
    items, error, code = _fetch_items_for_metadata_group(
        "Group", "genre", "Action", "SortName", "http://jf", "key"
    )
    assert code == 500
    assert "Internal error" in error


@patch('sync.os.path.exists')
@patch('sync.set_collection_image')
@patch('sync.get_cover_path')
@patch('sync.add_to_collection')
@patch('sync.create_collection')
@patch('sync.find_collection_by_name')
def test_process_collection_group_create_and_cover(
    mock_find, mock_create, mock_add, mock_cover, mock_set, mock_exists
):
    mock_find.return_value = None
    mock_create.return_value = "col123"
    mock_cover.return_value = "/cover.jpg"
    mock_exists.return_value = True
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", "/target", dry_run=False, auto_set_library_covers=True
    )
    assert result["links"] == 1
    mock_create.assert_called_once()
    mock_set.assert_called_once()


@patch('sync.os.path.exists')
@patch('sync.set_collection_image')
@patch('sync.get_cover_path')
@patch('sync.add_to_collection')
@patch('sync.find_collection_by_name')
def test_process_collection_group_cover_error(mock_find, mock_add, mock_cover, mock_set, mock_exists):
    mock_find.return_value = "col123"
    mock_cover.return_value = "/cover.jpg"
    mock_set.side_effect = Exception("Cover fail")
    mock_exists.return_value = True
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", "/target", dry_run=False, auto_set_library_covers=True
    )
    assert result["links"] == 1


# --- _process_group ---


def test_process_group_empty_name(tmp_path):
    result = _process_group(
        {}, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["group"] == "(unnamed)"
    assert result["links"] == 0
    assert result["error"] == "Empty group name"


@patch('sync._fetch_items_for_complex_group')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_complex_query(mock_meta, mock_complex, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_complex.return_value = ([{"Name": "M1", "Path": str(host)}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action AND NOT Comedy",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    mock_complex.assert_called_once()
    assert result["links"] == 1


@patch('sync._fetch_items_for_metadata_group')
def test_process_group_no_items(mock_meta, tmp_path):
    mock_meta.return_value = ([], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 0


@patch('sync._fetch_items_for_metadata_group')
def test_process_group_non_dict_item(mock_meta, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = (
        [
            "not a dict",
            {"Id": "1", "Name": "M1", "Path": str(host)},
        ],
        None,
        200,
    )
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 1


@patch('sync._fetch_items_for_metadata_group')
def test_process_group_missing_path(mock_meta, tmp_path):
    mock_meta.return_value = ([{"Id": "1", "Name": "M1"}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 0


@patch('sync.os.symlink')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_symlink_error(mock_meta, mock_symlink, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    mock_symlink.side_effect = OSError("Permission denied")
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 0


@patch('sync.add_virtual_folder')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_library_creation_error(mock_meta, mock_add, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    mock_add.side_effect = Exception("Lib fail")
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group,
        str(tmp_path),
        "http://jf",
        "key",
        "",
        "",
        "",
        "",
        "",
        auto_create_libraries=True,
        auto_set_library_covers=False,
        existing_libraries=[],
        target_path_in_jellyfin="",
    )
    assert result["links"] == 1
    assert "library_error" in result


@patch('sync.add_virtual_folder')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_library_with_jellyfin_path(mock_meta, mock_add, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    _ = _process_group(
        group,
        str(tmp_path),
        "http://jf",
        "key",
        "",
        "",
        "",
        "",
        "",
        auto_create_libraries=True,
        auto_set_library_covers=False,
        existing_libraries=[],
        target_path_in_jellyfin="/jf/target",
    )
    mock_add.assert_called_once()
    call_args = mock_add.call_args[0]
    assert "/jf/target/Test" in call_args[3]


@patch('sync.add_virtual_folder')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_library_already_exists(mock_meta, mock_add, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    _ = _process_group(
        group,
        str(tmp_path),
        "http://jf",
        "key",
        "",
        "",
        "",
        "",
        "",
        auto_create_libraries=True,
        auto_set_library_covers=False,
        existing_libraries=["Test"],
        target_path_in_jellyfin="",
    )
    mock_add.assert_not_called()


@patch('sync.set_virtual_folder_image')
@patch('sync.get_cover_path')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_auto_set_library_covers(mock_meta, mock_cover, mock_set, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    cover = tmp_path / "cover.jpg"
    cover.write_text("cover")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    mock_cover.return_value = str(cover)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group,
        str(tmp_path),
        "http://jf",
        "key",
        "",
        "",
        "",
        "",
        "",
        False,
        False,
        True,
        None,
        "",
    )
    assert result["links"] == 1
    mock_set.assert_called_once()


# --- run_sync ---


def test_run_sync_missing_settings():
    with pytest.raises(ValueError, match="Server settings"):
        run_sync({"jellyfin_url": "", "api_key": "", "target_path": ""})


@patch('sync.get_libraries')
@patch('sync._process_group')
def test_run_sync_get_libraries_error(mock_process, mock_libs, tmp_path):
    mock_libs.side_effect = Exception("Jellyfin down")
    mock_process.return_value = {"group": "Test", "links": 0}
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": str(tmp_path),
        "auto_create_libraries": True,
        "groups": [{"name": "Test", "source_type": "genre", "source_value": "Action"}],
    }
    results = run_sync(config, dry_run=False)
    assert results[0]["links"] == 0


@patch('sync._process_group')
@patch('sync._is_in_season')
@patch('sync.get_libraries')
def test_run_sync_seasonal_cleanup(mock_libs, mock_season, mock_process, tmp_path):
    mock_libs.return_value = []
    mock_season.return_value = False
    mock_process.return_value = {"group": "Test", "links": 0}
    target = tmp_path / "target"
    target.mkdir()
    (target / "Test").mkdir()
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": str(target),
        "groups": [
            {
                "name": "Test",
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            }
        ],
    }
    results = run_sync(config, dry_run=False)
    assert results[0]["status"] == "out_of_season"


# --- run_cleanup_broken_symlinks ---

@patch('sync.os.unlink')
@patch('sync.os.path.exists')
@patch('sync.os.path.islink')
@patch('sync.os.path.isdir')
def test_cleanup_broken_symlinks_unlink_error(mock_isdir, mock_islink, mock_exists, mock_unlink):
    mock_isdir.return_value = True
    mock_islink.return_value = True
    mock_exists.return_value = False
    mock_unlink.side_effect = OSError("Permission denied")
    config = {"target_path": "/target"}
    with patch('sync.os.walk', return_value=[("/target", [], ["link"])]):
        count = run_cleanup_broken_symlinks(config)
    assert count == 0


# --- Remaining branch coverage ---

def test_match_jellyfin_items_by_provider_falsy_provider_id():
    _LIBRARY_CACHE.clear()
    raw_items = [
        {"Id": "1", "ProviderIds": {"Imdb": ""}},
        {"Id": "2", "ProviderIds": {"Imdb": "tt123"}},
    ]
    with patch('sync._fetch_full_library', return_value=(raw_items, None, 200)):
        items, error, code = _match_jellyfin_items_by_provider(
            ["tt123"], "Imdb", "imdb_list_order", "SortName", "http://jf", "key", "Group"
        )
    assert len(items) == 1
    assert items[0]["Id"] == "2"


def test_match_jellyfin_items_by_provider_letterboxd_unmatched():
    _LIBRARY_CACHE.clear()
    raw_items = [{"Id": "1", "ProviderIds": {"Imdb": "tt123"}}]
    with patch('sync._fetch_full_library', return_value=(raw_items, None, 200)):
        items, error, code = _match_jellyfin_items_by_provider(
            ["tt999", "456"], "Tmdb", "letterboxd_list_order", "SortName", "http://jf", "key", "Group"
        )
    assert items == []


def test_match_jellyfin_items_by_provider_letterboxd_watched():
    _LIBRARY_CACHE.clear()
    raw_items = [
        {"Id": "1", "ProviderIds": {"Imdb": "tt111"}, "UserData": {"Played": True}},
        {"Id": "2", "ProviderIds": {"Imdb": "tt222"}, "UserData": {"Played": False}},
    ]
    with patch('sync._fetch_full_library', return_value=(raw_items, None, 200)):
        items, error, code = _match_jellyfin_items_by_provider(
            ["tt111", "tt222"], "Imdb", "letterboxd_list_order", "SortName", "http://jf", "key", "Group", watch_state="watched"
        )
    assert len(items) == 1
    assert items[0]["Id"] == "1"


@patch('sync.get_tmdb_recommendations')
@patch('sync.get_user_recent_items')
def test_fetch_items_recommendations_empty_tmdb_ids(mock_recent, mock_recs):
    mock_recent.return_value = [{"Id": "1", "Name": "M1"}]
    mock_recs.return_value = []
    items, error, code = _fetch_items_for_recommendations_group(
        "Group", "user1", "SortName", "http://jf", "key", "tmdb_key"
    )
    assert items == []
    assert error is None
    assert code == 200


def test_match_condition_empty_type_or_value():
    item = {"Genres": ["Action"]}
    assert _match_condition(item, "", "action") is False
    assert _match_condition(item, "genre", "") is False


def test_match_condition_exception_handling():
    item = {"Genres": 123}  # non-iterable truthy value triggers TypeError in for-loop
    assert _match_condition(item, "genre", "action") is False


def test_eval_item_empty_rules():
    item = {"Name": "M1"}
    assert _eval_item(item, []) is True


def test_eval_item_not_operators():
    item = {"Genres": ["Action"]}
    rules = [
        {"operator": "AND NOT", "type": "genre", "value": "comedy"},
    ]
    assert _eval_item(item, rules) is True

    rules = [
        {"operator": "OR NOT", "type": "genre", "value": "action"},
    ]
    assert _eval_item(item, rules) is False

    rules = [
        {"operator": "AND", "type": "genre", "value": "action"},
        {"operator": "AND NOT", "type": "genre", "value": "comedy"},
    ]
    assert _eval_item(item, rules) is True


@patch('sync._fetch_full_library')
def test_complex_group_non_dict_rule(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_complex_group(
        "Group", [123], "SortName", "http://jf", "key"
    )
    assert items == []


@patch('sync._fetch_full_library')
def test_complex_group_empty_type_value(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = ([{"Name": "M1"}], None, 200)
    items, error, code = _fetch_items_for_complex_group(
        "Group", [{"type": "", "value": ""}], "SortName", "http://jf", "key"
    )
    assert items == []


@patch('sync._fetch_full_library')
def test_complex_group_watched_filter(mock_lib):
    _LIBRARY_CACHE.clear()
    mock_lib.return_value = (
        [
            {"Name": "Played", "Genres": ["Action"], "UserData": {"Played": True}},
            {"Name": "Unplayed", "Genres": ["Action"], "UserData": {"Played": False}},
        ],
        None,
        200,
    )
    items, error, code = _fetch_items_for_complex_group(
        "Group",
        [{"operator": "AND", "type": "genre", "value": "action"}],
        "SortName",
        "http://jf",
        "key",
        watch_state="watched",
    )
    assert len(items) == 1
    assert items[0]["Name"] == "Played"


def test_parse_complex_query_unrecognized_prefix():
    rules = parse_complex_query("foo:bar", "genre")
    assert rules == [{"operator": "AND", "type": "genre", "value": "foo:bar"}]


@patch('sync.add_to_collection')
@patch('sync.find_collection_by_name')
def test_process_collection_group_no_cover(mock_find, mock_add, tmp_path):
    mock_find.return_value = "col123"
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", str(tmp_path), dry_run=False, auto_set_library_covers=True
    )
    assert result["links"] == 1


@patch('sync.add_to_collection')
@patch('sync.find_collection_by_name')
def test_process_collection_group_auto_cover_off(mock_find, mock_add, tmp_path):
    mock_find.return_value = "col123"
    items = [{"Id": "1", "Name": "Movie"}]
    result = _process_collection_group(
        "Group", items, "http://jf", "key", str(tmp_path), dry_run=False, auto_set_library_covers=False
    )
    assert result["links"] == 1


@patch('sync.create_collection')
@patch('sync.add_to_collection')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_create_collection(mock_meta, mock_add, mock_create, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_create.return_value = "col123"
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
        "create_as_collection": True,
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 1
    mock_create.assert_called_once()


@patch('sync._fetch_items_for_metadata_group')
def test_process_group_missing_host_path(mock_meta, tmp_path):
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": "/nonexistent/movie.mkv"}], None, 200)
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group, str(tmp_path), "http://jf", "key", "", "", "", "", "", False, False, False, None, ""
    )
    assert result["links"] == 0


@patch('sync.get_cover_path')
@patch('sync._fetch_items_for_metadata_group')
def test_process_group_auto_cover_missing(mock_meta, mock_cover, tmp_path):
    host = tmp_path / "movie.mkv"
    host.write_text("movie")
    mock_meta.return_value = ([{"Id": "1", "Name": "M1", "Path": str(host)}], None, 200)
    mock_cover.return_value = None
    group = {
        "name": "Test",
        "source_type": "genre",
        "source_value": "Action",
        "sort_order": "SortName",
    }
    result = _process_group(
        group,
        str(tmp_path),
        "http://jf",
        "key",
        "",
        "",
        "",
        "",
        "",
        False,
        False,
        True,
        None,
        "",
    )
    assert result["links"] == 1


def test_is_in_season_invalid_date():
    assert _is_in_season("bad", "also-bad") is True
    assert _is_in_season("01-01", "not-a-date") is True


@patch('sync._process_group')
@patch('sync._is_in_season')
@patch('sync.get_libraries')
def test_run_sync_seasonal_dry_run(mock_libs, mock_season, mock_process, tmp_path):
    mock_libs.return_value = []
    mock_season.return_value = False
    mock_process.return_value = {"group": "Test", "links": 0}
    target = tmp_path / "target"
    target.mkdir()
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": str(target),
        "groups": [
            {
                "name": "Test",
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            }
        ],
    }
    results = run_sync(config, dry_run=True)
    assert results[0]["status"] == "out_of_season"


@patch('sync._process_group')
@patch('sync._is_in_season')
@patch('sync.get_libraries')
def test_run_sync_seasonal_no_dir(mock_libs, mock_season, mock_process, tmp_path):
    mock_libs.return_value = []
    mock_season.return_value = False
    mock_process.return_value = {"group": "Test", "links": 0}
    target = tmp_path / "target"
    target.mkdir()
    # Do NOT create Test subdirectory
    config = {
        "jellyfin_url": "http://jf",
        "api_key": "key",
        "target_path": str(target),
        "groups": [
            {
                "name": "Test",
                "seasonal_enabled": True,
                "seasonal_start": "01-01",
                "seasonal_end": "01-02",
            }
        ],
    }
    results = run_sync(config, dry_run=False)
    assert results[0]["status"] == "out_of_season"
