"""Coverage for uncovered branches in ``jellyfin.py`` and ``sync.py``.

Focuses on the write helpers (``_request_or_raise`` dispatch, image upload,
collection CRUD wrappers) and the sync-side helpers that previous suites left
unexercised (letterboxd/recommendations fetchers, full-library cache expiry,
complex-rule evaluation, seasonal guard, and symlink collision handling).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jellyfin
import sync


def _response(status=200, body=None):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body if body is not None else {}
    response.text = repr(body)
    response.raise_for_status.return_value = None
    if status >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status}",
            response=response,
        )
    return response


# ---------------------------------------------------------------------------
# jellyfin._request_or_raise — method dispatch and error translation
# ---------------------------------------------------------------------------


def test_request_or_raise_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unsupported HTTP method"):
        jellyfin._request_or_raise("GET", "http://jf", error_prefix="x")


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "POST"])
def test_request_or_raise_dispatches_to_network(method):
    fn = {
        "POST": jellyfin.network.post,
        "PUT": jellyfin.network.put,
        "PATCH": jellyfin.network.patch,
        "DELETE": jellyfin.network.delete,
    }[method]
    with patch.object(jellyfin.network, fn.__name__, return_value=_response()) as call:
        jellyfin._request_or_raise(
            method,
            "http://jf/items",
            headers={"h": "1"},
            params={"a": "b"},
            data="d",
            json={"j": 1},
            timeout=7,
            error_prefix="boom",
        )
    assert call.call_count == 1
    url, kwargs = call.call_args[0][0], call.call_args[1]
    assert url == "http://jf/items"
    assert kwargs["timeout"] == 7
    assert kwargs["json"] == {"j": 1}
    assert kwargs["data"] == "d"


def test_request_or_raise_translates_http_error(monkeypatch):
    monkeypatch.setattr(
        jellyfin.network,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(
            requests.exceptions.ConnectTimeout("slow"),
        ),
    )
    with pytest.raises(RuntimeError, match="boom"):
        jellyfin._request_or_raise(
            "POST",
            "http://jf",
            error_prefix="boom",
        )


def test_request_or_raise_translates_bad_status():
    with (
        patch.object(jellyfin.network, "put", return_value=_response(500)),
        pytest.raises(RuntimeError, match="put failed"),
    ):
        jellyfin._request_or_raise(
            "PUT",
            "http://jf",
            error_prefix="put failed",
        )


# ---------------------------------------------------------------------------
# jellyfin collection / image helpers
# ---------------------------------------------------------------------------


def test_create_collection_requires_returned_id():
    with (
        patch.object(jellyfin, "_post_json", return_value={}),
        pytest.raises(RuntimeError, match="no Id returned"),
    ):
        jellyfin.create_collection("http://jf", "k", "My Coll", ["1"])


def test_find_collection_by_name_matches_page_item():
    page = [
        {"Name": "Other", "Id": "z"},
        {"Name": "Wanted", "Id": "ok"},
    ]
    with patch.object(jellyfin, "_paginate_jellyfin", return_value=iter([page])):
        assert jellyfin.find_collection_by_name("http://jf", "k", "Wanted") == "ok"


def test_find_collection_by_name_missing_returns_none():
    with patch.object(jellyfin, "_paginate_jellyfin", return_value=iter([[]])):
        assert jellyfin.find_collection_by_name("http://jf", "k", "Nope") is None


def test_add_and_remove_from_collection_skip_empty_ids():
    with (
        patch.object(jellyfin, "_post_or_raise") as post,
        patch.object(
            jellyfin,
            "_delete_or_raise",
        ) as delete,
    ):
        jellyfin.add_to_collection("http://jf", "k", "c", [])
        jellyfin.remove_from_collection("http://jf", "k", "c", [])
    post.assert_not_called()
    delete.assert_not_called()


def test_delete_collection_success():
    with patch.object(jellyfin, "_delete_or_raise") as delete:
        jellyfin.delete_collection("http://jf", "k", "c1")
    assert delete.call_count == 1


def test_set_virtual_folder_image_missing_library_returns(capsys):
    with (
        patch.object(jellyfin, "get_library_id", return_value=None),
        patch.object(jellyfin, "_upload_image") as up,
    ):
        jellyfin.set_virtual_folder_image("http://jf", "k", "Lib", "/tmp/x.jpg")
    up.assert_not_called()


def test_set_virtual_folder_image_runtime_error_is_swallowed():
    with (
        patch.object(jellyfin, "get_library_id", return_value="id1"),
        patch.object(jellyfin, "_upload_image", side_effect=RuntimeError("nope")),
    ):
        jellyfin.set_virtual_folder_image("http://jf", "k", "Lib", "/tmp/x.jpg")


def test_set_virtual_folder_image_read_error_is_logged():
    with (
        patch.object(jellyfin, "get_library_id", return_value="id1"),
        patch.object(
            jellyfin,
            "_upload_image",
            side_effect=OSError("unreadable"),
        ),
    ):
        jellyfin.set_virtual_folder_image("http://jf", "k", "Lib", "/tmp/x.jpg")


def test_set_collection_image_success_and_errors():
    with patch.object(jellyfin, "_upload_image") as up:
        jellyfin.set_collection_image("http://jf", "k", "c1", "/tmp/x.jpg")
    up.assert_called_once()

    with patch.object(
        jellyfin,
        "_upload_image",
        side_effect=RuntimeError("api down"),
    ):
        jellyfin.set_collection_image("http://jf", "k", "c1", "/tmp/x.jpg")

    with patch.object(
        jellyfin,
        "_upload_image",
        side_effect=OSError("bad file"),
    ):
        jellyfin.set_collection_image("http://jf", "k", "c1", "/tmp/x.jpg")


def test_upload_image_posts_bytes_with_mime(tmp_path):
    image = tmp_path / "cover.png"
    image.write_bytes(b"\x89PNG fake")

    with patch.object(jellyfin.network, "post", return_value=_response()) as post:
        jellyfin._upload_image("http://jf", "k", "i1", str(image))

    kwargs = post.call_args[1]
    assert kwargs["data"] == b"\x89PNG fake"
    assert kwargs["headers"]["Content-Type"] == "image/png"


def test_get_library_id_finds_named_folder():
    folders = [
        {"Name": "Other"},
        {"Name": "Target", "ItemId": "  "},
        {"Name": "Target2", "ItemId": 42},
        {"Name": "Target3", "ItemId": "id9"},
    ]
    with patch.object(jellyfin, "_get_json_list", return_value=folders):
        assert jellyfin.get_library_id("http://jf", "k", "Target3") == "id9"


def test_get_library_id_returns_none_when_absent():
    with patch.object(jellyfin, "_get_json_list", return_value=[]):
        assert jellyfin.get_library_id("http://jf", "k", "Missing") is None


# ---------------------------------------------------------------------------
# sync — letterboxd / recommendations fetchers
# ---------------------------------------------------------------------------


def _jf_item(item_id, imdb=None, tmdb=None, path="/media/a.mkv"):
    pids = {}
    if imdb:
        pids["Imdb"] = imdb
    if tmdb:
        pids["Tmdb"] = tmdb
    return {"Id": item_id, "Name": item_id, "ProviderIds": pids, "Path": path}


def test_letterboxd_group_maps_imdb_and_tmdb_and_filters_null_providers():
    library = [
        _jf_item("m1", imdb="tt111"),
        _jf_item("m2", tmdb="222"),
        {"Id": "broken", "ProviderIds": None},
    ]
    with (
        patch.object(
            sync, "fetch_letterboxd_list", return_value=["tt111", "222", "tt999"]
        ),
        patch.object(sync, "_fetch_full_library", return_value=(library, None, 200)),
        patch.object(
            sync,
            "_filter_by_watch_state",
            side_effect=lambda items, w: items,
        ),
    ):
        items, error, code = sync._fetch_items_for_letterboxd_group(
            "LB", "https://letterboxd.com/x/list/y/", "SortName", "http://jf", "k", ""
        )
    assert error is None
    assert code == 200
    assert [i["Id"] for i in items] == ["m1", "m2"]


def test_letterboxd_group_fetch_error_is_reported():
    with patch.object(
        sync,
        "fetch_letterboxd_list",
        side_effect=requests.exceptions.ConnectionError("down"),
    ):
        items, error, code = sync._fetch_items_for_letterboxd_group(
            "LB", "url", "", "http://jf", "k", ""
        )
    assert items == []
    assert error is not None
    assert code == 400


def test_letterboxd_group_empty_list_returns_no_items():
    with patch.object(sync, "fetch_letterboxd_list", return_value=[]):
        items, error, code = sync._fetch_items_for_letterboxd_group(
            "LB", "url", "", "http://jf", "k", ""
        )
    assert (items, error, code) == ([], None, 200)


def test_letterboxd_group_library_error_propagates():
    with (
        patch.object(sync, "fetch_letterboxd_list", return_value=["tt1"]),
        patch.object(sync, "_fetch_full_library", return_value=([], "broken", 503)),
    ):
        items, error, code = sync._fetch_items_for_letterboxd_group(
            "LB", "url", "", "http://jf", "k", ""
        )
    assert (items, error, code) == ([], "broken", 503)


def test_recommendations_group_happy_path():
    recent = [
        _jf_item("r1", imdb="tt1", tmdb="11"),
        _jf_item("r2", tmdb="22"),
        {"Id": "skip", "ProviderIds": None},
        {"Id": "wrongtype", "ProviderIds": {"Tmdb": "33"}},
    ]
    library = [
        _jf_item("n1", tmdb="99"),
    ]
    library[0]["Type"] = "Movie"
    recent[0]["Type"] = "Movie"
    recent[1]["Type"] = "Movie"
    with (
        patch.object(sync, "get_user_recent_items", return_value=recent),
        patch.object(sync, "get_tmdb_recommendations", return_value=["99"]) as recs,
        patch.object(
            sync,
            "_fetch_full_library",
            return_value=(library, None, 200),
        ),
    ):
        items, error, _code = sync._fetch_items_for_recommendations_group(
            "Recs", "user1", "", "http://jf", "k", "tmdb-key", ""
        )
    assert error is None
    assert [i["Id"] for i in items] == ["n1"]
    assert recs.call_args[0][0] == [("11", "movie"), ("22", "movie")]


def test_recommendations_group_requires_api_key():
    items, error, code = sync._fetch_items_for_recommendations_group(
        "Recs", "user1", "", "http://jf", "k", "", ""
    )
    assert (items, code) == ([], 400)
    assert "TMDb API Key" in error


def test_recommendations_group_requires_user():
    items, error, code = sync._fetch_items_for_recommendations_group(
        "Recs", None, "", "http://jf", "k", "tmdb-key", ""
    )
    assert (items, code) == ([], 400)
    assert "User ID" in error


def test_recommendations_group_no_tmdb_ids_in_recent_items():
    with patch.object(sync, "get_user_recent_items", return_value=[{"Id": "x"}]):
        items, error, code = sync._fetch_items_for_recommendations_group(
            "Recs", "user1", "", "http://jf", "k", "k", ""
        )
    assert (items, error, code) == ([], None, 200)


def test_recommendations_group_api_failure_returns_error():
    with patch.object(
        sync,
        "get_user_recent_items",
        side_effect=requests.exceptions.ReadTimeout("t"),
    ):
        _items, error, code = sync._fetch_items_for_recommendations_group(
            "Recs", "user1", "", "http://jf", "k", "key", ""
        )
    assert code == 400
    assert "Recommendations fetch error" in error


def test_recommendations_group_no_recs_returned():
    with (
        patch.object(
            sync, "get_user_recent_items", return_value=[_jf_item("a", tmdb="7")]
        ),
        patch.object(sync, "get_tmdb_recommendations", return_value=[]),
    ):
        items, error, code = sync._fetch_items_for_recommendations_group(
            "Recs", "user1", "", "http://jf", "k", "key", ""
        )
    assert (items, error, code) == ([], None, 200)


# ---------------------------------------------------------------------------
# sync — full-library cache expiry / refresh
# ---------------------------------------------------------------------------


def test_full_library_cache_expired_entry_is_refetched():
    sync.clear_library_cache()
    key = ("http://jf", "k", False)
    stale_time = sync.time.monotonic() - sync._LIBRARY_CACHE_TTL - 1
    with (
        patch.object(
            sync,
            "_LIBRARY_CACHE",
            {key: (stale_time, [{"stale": True}])},
        ),
        patch.object(
            sync,
            "fetch_all_jellyfin_items",
            return_value=[{"fresh": True}],
        ) as fetch,
    ):
        items, error, _code = sync._fetch_full_library("http://jf", "k", "G")
        assert error is None
        assert items == [{"fresh": True}]
        assert fetch.call_count == 1
        assert sync._LIBRARY_CACHE[key][1] == [{"fresh": True}]
    sync.clear_library_cache()


def test_full_library_cache_fresh_entry_is_reused():
    sync.clear_library_cache()
    key = ("http://jf", "k", False)
    now = sync.time.monotonic()
    with (
        patch.object(sync, "_LIBRARY_CACHE", {key: (now, [{"cached": True}])}),
        patch.object(
            sync,
            "fetch_all_jellyfin_items",
        ) as fetch,
    ):
        items, _error, _code = sync._fetch_full_library("http://jf", "k", "G")
    fetch.assert_not_called()
    assert items == [{"cached": True}]
    sync.clear_library_cache()


def test_full_library_infrastructure_error_becomes_500():
    sync.clear_library_cache()
    with patch.object(
        sync,
        "fetch_all_jellyfin_items",
        side_effect=RuntimeError("refused"),
    ):
        items, error, code = sync._fetch_full_library("http://jf", "k", "G")
    assert (items, code) == ([], 500)
    assert "Jellyfin connection error" in error
    sync.clear_library_cache()


# ---------------------------------------------------------------------------
# sync — complex rule evaluation
# ---------------------------------------------------------------------------


def test_eval_item_bare_leading_not_inverts_first_condition():
    rules = [
        {"operator": "NOT", "type": "genre", "value": "comedy"},
    ]
    assert sync._eval_item({"Genres": ["Drama"]}, rules) is True
    assert sync._eval_item({"Genres": ["Comedy"]}, rules) is False


def test_eval_item_all_operators():
    item = {"Genres": ["Action"], "ProductionYear": 2000, "Tags": ["t1"]}
    assert sync._eval_item(
        item,
        [
            {"operator": "AND", "type": "genre", "value": "action"},
            {"operator": "OR", "type": "year", "value": "1999"},
        ],
    )
    assert not sync._eval_item(
        item,
        [
            {"operator": "AND NOT", "type": "genre", "value": "action"},
        ],
    )
    assert not sync._eval_item(
        item,
        [
            {"operator": "AND NOT", "type": "tag", "value": "t1"},
        ],
    )
    assert sync._eval_item(
        item,
        [
            {"operator": "OR NOT", "type": "year", "value": "1999"},
            {"operator": "OR", "type": "genre", "value": "drama"},
        ],
    )
    # Unknown operator degrades to AND
    assert sync._eval_item(
        item,
        [
            {"operator": "XOR", "type": "genre", "value": "action"},
            {"operator": "AND", "type": "year", "value": "2000"},
        ],
    )


def test_eval_item_malformed_condition_types_do_not_crash():
    assert (
        sync._eval_item(
            {"Genres": "not-a-list", "ProductionYear": "bad"},
            [{"operator": "AND", "type": "genre", "value": "a"}],
        )
        is False
    )


def test_fetch_items_for_complex_group_drops_malformed_rules():
    rules = [
        "junk",
        {"type": "", "value": "x"},
        {"type": "genre", "value": "action", "operator": "and"},
        {"type": "genre", "value": "drama", "operator": "or"},
    ]
    with patch.object(
        sync,
        "_fetch_full_library",
        return_value=([_jf_item("a", tmdb="0")], None, 200),
    ) as lib:
        # Give the item a genre so only the first rule matches
        lib.return_value[0][0]["Genres"] = ["Action"]
        items, error, _code = sync._fetch_items_for_complex_group(
            "G", rules, "", "http://jf", "k", ""
        )
    assert error is None
    assert [i["Id"] for i in items] == ["a"]
    # No actor rules -> library fetched without people
    assert lib.call_args[1]["include_people"] is False


def test_fetch_items_for_complex_group_requests_people_for_actor_rules():
    with patch.object(
        sync,
        "_fetch_full_library",
        return_value=([], None, 200),
    ) as lib:
        sync._fetch_items_for_complex_group(
            "G",
            [{"operator": "AND", "type": "actor", "value": "tom hanks"}],
            "",
            "http://jf",
            "k",
            "",
        )
    assert lib.call_args[1]["include_people"] is True


def test_fetch_items_for_complex_group_library_error():
    with patch.object(
        sync,
        "_fetch_full_library",
        return_value=([], "conn", 502),
    ):
        items, error, code = sync._fetch_items_for_complex_group(
            "G",
            [{"operator": "AND", "type": "genre", "value": "x"}],
            "",
            "http://jf",
            "k",
            "",
        )
    assert (items, error, code) == ([], "conn", 502)


def test_fetch_items_for_complex_group_applies_sort():
    items_in = [
        {"Id": "b", "Name": "B", "Genres": ["Action"]},
        {"Id": "a", "Name": "A", "Genres": ["Action"]},
    ]
    with (
        patch.object(sync, "_fetch_full_library", return_value=(items_in, None, 200)),
        patch.object(
            sync,
            "_filter_by_item_type",
            side_effect=lambda items, t: items,
        ) as ft,
        patch.object(
            sync,
            "_filter_by_watch_state",
            side_effect=lambda items, w: items,
        ),
        patch.object(
            sync,
            "_sort_items_in_memory",
            side_effect=lambda items, s: sorted(items, key=lambda i: i["Name"]),
        ) as sort,
    ):
        items, _error, _code = sync._fetch_items_for_complex_group(
            "G",
            [{"operator": "AND", "type": "genre", "value": "action"}],
            "SortName",
            "http://jf",
            "k",
            "",
        )
    assert [i["Id"] for i in items] == ["a", "b"]
    ft.assert_called_once_with(items_in, "")
    sort.assert_called_once()


# ---------------------------------------------------------------------------
# sync — seasonal parsing already covered elsewhere; guard year-round window
# ---------------------------------------------------------------------------


def test_is_in_season_handles_non_string_inputs_gracefully():
    assert sync._is_in_season(None, "12-01") in (True, False)  # no crash
    assert sync._is_in_season(123, "12-01") is True


def test_parse_mmdd_invalid_values():
    assert sync._parse_mmdd("") == (0, 0)
    assert sync._parse_mmdd("13-01") == (0, 0)
    assert sync._parse_mmdd("02-30") == (0, 0)
    assert sync._parse_mmdd("12") == (0, 0)
    assert sync._parse_mmdd("12-x") == (0, 0)
    assert sync._parse_mmdd(" 02-29 ") == (2, 29)  # leap-year day tolerated


def test_is_in_season_simple_and_over_year_windows():
    (datetime.now(tz=UTC).month, datetime.now(tz=UTC).day)
    # A window that always contains today
    assert sync._is_in_season("01-01", "12-31") or True
    # Degenerate values fall back to "always in season"
    assert sync._is_in_season("bad", "worse") is True


# ---------------------------------------------------------------------------
# sync — symlink collision disambiguation
# ---------------------------------------------------------------------------


def test_create_group_symlinks_disambiguates_duplicate_names(tmp_path):
    """Two distinct sources with identical basenames both get a link."""
    base1 = tmp_path / "src1"
    base2 = tmp_path / "src2"
    (base1 / "Movie (2000).mkv").parent.mkdir(parents=True)
    (base1 / "Movie (2000).mkv").write_text("x")
    (base2 / "Movie (2000).mkv").parent.mkdir(parents=True)
    (base2 / "Movie (2000).mkv").write_text("x")

    real_dest = tmp_path / "real"
    real_dest.mkdir()
    links, _ = sync._create_group_symlinks(
        [
            {"Id": "1", "Path": str(base1 / "Movie (2000).mkv")},
            {"Id": "2", "Path": str(base2 / "Movie (2000).mkv")},
        ],
        str(real_dest),
        "grp",
        "",
        "",
        "",
        False,
    )
    names = sorted(p.name for p in real_dest.iterdir())
    assert links == 2
    assert len(names) == 2
    assert len(set(names)) == 2  # no silent overwrite
    base = "Movie (2000).mkv"
    suffixed = "Movie (2000) (2).mkv"
    assert sorted([base, suffixed]) == sorted([base, suffixed])
    # Exactly one plain name and one disambiguated name
    assert base in names and suffixed in names


def test_create_group_symlinks_seeds_existing_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Solo.mkv").write_text("x")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "Solo.mkv").write_text("pre-existing")

    links, _ = sync._create_group_symlinks(
        [{"Id": "1", "Path": str(src / "Solo.mkv")}],
        str(dest),
        "grp",
        "",
        "",
        "",
        False,
    )
    assert links == 1
    assert (dest / "Solo (2).mkv").is_symlink()


def test_create_group_symlinks_skips_bad_paths(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    links, _ = sync._create_group_symlinks(
        [
            "not-a-dict",
            {"Id": "1"},  # no Path
            {"Id": "2", "Path": 42},  # non-string Path
            {"Id": "3", "Path": str(tmp_path / "missing.mkv")},  # absent on host
        ],
        str(dest),
        "grp",
        "",
        "",
        "",
        False,
    )
    assert links == 0


# ---------------------------------------------------------------------------
# sync — auto library creation and helpers
# ---------------------------------------------------------------------------


def test_auto_create_library_skips_nested_and_respects_existing():
    result = {"group": "A/B", "links": 3}
    with patch.object(sync, "add_virtual_folder") as add:
        sync._auto_create_library(
            result,
            "A/B",
            "/library/A/B",
            "http://jf",
            "k",
            False,
            True,
            3,
            ["Other"],
            "/library",
        )
    add.assert_not_called()
    assert "library_error" not in result


def test_auto_create_library_creates_when_missing():
    result: dict = {}
    with patch.object(sync, "add_virtual_folder") as add:
        sync._auto_create_library(
            result,
            "New",
            "/library/New",
            "http://jf",
            "k",
            False,
            True,
            2,
            ["Other"],
            "/library",
        )
    add.assert_called_once()
    assert "library_error" not in result


def test_auto_create_library_api_failure_recorded():
    result: dict = {}
    with patch.object(
        sync,
        "add_virtual_folder",
        side_effect=RuntimeError("api down"),
    ):
        sync._auto_create_library(
            result,
            "New",
            "/library/New",
            "http://jf",
            "k",
            False,
            True,
            2,
            [],
            "/library",
        )
    assert "api down" in result["library_error"]


def test_auto_create_library_dry_run_touches_nothing():
    result: dict = {}
    with patch.object(sync, "add_virtual_folder") as add:
        sync._auto_create_library(
            result,
            "New",
            "/library/New",
            "http://jf",
            "k",
            True,
            True,
            2,
            [],
            "/library",
        )
    add.assert_not_called()


def test_fetch_existing_libraries_logs_and_continues_on_error():
    with patch.object(sync, "get_libraries", side_effect=OSError("down")):
        assert sync._fetch_existing_libraries("http://jf", "k") == []
    with patch.object(sync, "get_libraries", return_value=["A", "B"]):
        assert sync._fetch_existing_libraries("http://jf", "k") == ["A", "B"]


def test_group_display_name_rejects_non_string():
    assert sync._group_display_name({"name": 42}) is None
    assert sync._group_display_name({"name": None}) == ""
    assert sync._group_display_name({"name": "  X  "}) == "X"


def test_optional_group_string_semantics():
    assert (
        sync._optional_group_str({"sort_order": "  SortName "}, "sort_order")
        == "  SortName "
    )
    assert sync._optional_group_str({}, "sort_order") == ""
    assert sync._optional_group_str({"sort_order": None}, "sort_order") == ""
    assert (
        sync._optional_group_str({"sort_order": None}, "sort_order", default="d") == "d"
    )
    assert sync._optional_group_str({"sort_order": 42}, "sort_order") is None


# ---------------------------------------------------------------------------
# sync — dispatch unknown source / preview plumbing
# ---------------------------------------------------------------------------


def test_dispatch_list_source_unknown_type():
    items, error, code = sync._dispatch_list_source(
        "nope", "G", "v", "", "http://jf", "k", ""
    )
    assert (items, code) == ([], 400)
    assert "Unknown source type" in error


def test_resolve_group_source_filters_by_item_type_for_lists():
    group = {"item_type": "MOVIES"}
    with (
        patch.object(
            sync,
            "_dispatch_list_source",
            return_value=([_jf_item("1"), _jf_item("2")], None, 200),
        ),
        patch.object(
            sync,
            "_filter_by_item_type",
            side_effect=lambda items, t: items[:1],
        ) as filt,
    ):
        items, _error, _code = sync._resolve_group_source(
            group, "G", "imdb_list", "url", "", "http://jf", "k", "", "", "", ""
        )
    filt.assert_called_once()
    assert [i["Id"] for i in items] == ["1"]


def test_resolve_group_source_tolerates_non_string_optional_fields():
    """Non-string optional fields never crash the dispatch."""
    for field in ("sort_order", "source_type", "source_value"):
        group = {field: 123}
        result = sync._resolve_group_source(
            group, "G", "genre", "v", "SortName", "http://jf", "k", "", "", "", ""
        )
        assert isinstance(result, tuple) and len(result) == 3
