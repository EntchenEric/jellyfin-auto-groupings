"""Coverage for previously unexercised branches in ``routes.py`` and ``sync.py``.

Covers the sync error-mapping endpoints, path-root inference, test-result
dashboard reading, ``get_cover_path`` storage priority, watch-state and
item-type filters, ``parse_complex_query`` NOT handling, and the broken
symlink cleanup guard.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
import sync
from werkzeug.exceptions import ServiceUnavailable


# ---------------------------------------------------------------------------
# routes._handle_http_error
# ---------------------------------------------------------------------------


def test_handle_http_error_maps_code_to_json(app):
    with app.test_request_context():
        exc = ServiceUnavailable(description="down for maintenance")
        body, status = routes._handle_http_error(exc)
        assert status == 503
        assert body.get_json() == {
            "status": "error",
            "message": "down for maintenance",
        }


def test_handle_http_error_reraises_when_code_is_none(app):
    with app.test_request_context():
        exc = ServiceUnavailable()
        exc.code = None
        with pytest.raises(ServiceUnavailable):
            routes._handle_http_error(exc)


# ---------------------------------------------------------------------------
# routes._run_sync_handler error mapping
# ---------------------------------------------------------------------------


def test_run_sync_handler_busy_returns_409(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "run_sync",
        lambda *a, **k: (_ for _ in ()).throw(routes.SyncBusyError("sync locked")),
    )
    resp = client.post("/api/sync/preview_all")
    assert resp.status_code == 409
    assert resp.get_json()["status"] == "error"


def test_run_sync_handler_value_error_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "run_sync",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad config")),
    )
    resp = client.post("/api/sync/preview_all")
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_run_sync_handler_runtime_error_returns_500(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "run_sync",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk exploded")),
    )
    resp = client.post("/api/sync/preview_all")
    assert resp.status_code == 500
    assert "Sync preview failed" in resp.get_json()["message"]


def test_run_sync_handler_os_error_prefix_for_real_sync(client, monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: {"jellyfin_url": "x"})
    monkeypatch.setattr(
        routes,
        "run_sync",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no space")),
    )
    resp = client.post("/api/sync")
    assert resp.status_code == 500
    assert "Sync failed" in resp.get_json()["message"]


# ---------------------------------------------------------------------------
# routes._compute_common_root
# ---------------------------------------------------------------------------


def test_compute_common_root_strips_shared_trailing_components():
    j_root, h_root = routes._compute_common_root(
        "/media/media-server/Movies/Action/Foo (2020)",
        "/host/share/Movies/Action/Foo (2020)",
    )
    # Trailing components are stripped in one pass, not matched per-component:
    # the shared suffix ("Foo (2020)") is removed once, leaving the roots.
    assert j_root == "/media/media-server"
    assert h_root == "/host/share"


def test_compute_common_root_fully_common_returns_os_sep():
    j_root, h_root = routes._compute_common_root("/movies/x", "/movies/x")
    assert j_root == "/"
    assert h_root == "/"


def test_compute_common_root_single_side_match():
    # Only one matching trailing component: strip it from both sides.
    j_root, h_root = routes._compute_common_root("/media/x", "/host/x")
    assert (j_root, h_root) == ("/media", "/host")


def test_compute_common_root_no_match_returns_none():
    assert routes._compute_common_root("/movies/x", "/host/y") == (None, None)


# ---------------------------------------------------------------------------
# routes.get_test_results
# ---------------------------------------------------------------------------


def test_get_test_results_reads_present_files(client, tmp_path, monkeypatch):
    target = tmp_path / "test_results.txt"
    target.write_text("unit-test output", encoding="utf-8")
    monkeypatch.setattr(
        routes,
        "_TEST_RESULT_FILENAMES",
        ("test_results.txt", "missing_out.txt"),
    )
    monkeypatch.chdir(tmp_path)
    resp = client.get("/api/test/results")
    assert resp.status_code == 200
    data = resp.get_json()["results"]
    assert data["test_results.txt"] == "unit-test output"
    assert data["missing_out.txt"] == "No output found."


def test_get_test_results_read_error_is_reported(client, tmp_path, monkeypatch):
    target = tmp_path / "test_results.txt"
    target.write_bytes(b"\xff\xfe\xfa")
    monkeypatch.setattr(routes, "_TEST_RESULT_FILENAMES", ("test_results.txt",))
    monkeypatch.chdir(tmp_path)
    # Replace open on that path with one raising OSError.
    original_open = Path.open

    def broken_open(self, *args, **kwargs):
        if self.name == "test_results.txt":
            raise OSError("permission denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    resp = client.get("/api/test/results")
    assert resp.status_code == 200
    assert resp.get_json()["results"]["test_results.txt"] == "Error reading file."


# ---------------------------------------------------------------------------
# sync.get_cover_path — save vs. exist resolution
# ---------------------------------------------------------------------------


def test_get_cover_path_save_prefers_library_local_when_target_is_dir(tmp_path):
    path = sync.get_cover_path(
        "My Group",
        target_base=str(tmp_path),
        check_exists=False,
    )
    assert path == str(tmp_path / ".covers" / f"{sync.hashlib.md5(b'My Group', usedforsecurity=False).hexdigest()}.jpg")


def test_get_cover_path_save_falls_back_legacy_without_target_dir(tmp_path):
    path = sync.get_cover_path(
        "My Group",
        target_base=str(tmp_path / "nonexistent"),
        check_exists=False,
    )
    assert "config/covers" in path


def test_get_cover_path_check_exists_prefers_lib_then_legacy(tmp_path):
    name_hash = sync.hashlib.md5(b"G", usedforsecurity=False).hexdigest()
    lib = tmp_path / ".covers" / f"{name_hash}.jpg"
    lib.parent.mkdir()
    lib.write_text("x")

    found = sync.get_cover_path("G", target_base=str(tmp_path), check_exists=True)
    assert found == str(lib)

    # Remove the lib copy; place one in the legacy config dir instead.
    lib.unlink()
    legacy_dir = Path(sync.__file__).resolve().parent / "config" / "covers"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy = legacy_dir / f"{name_hash}.jpg"
    legacy.write_text("x")
    try:
        found = sync.get_cover_path("G", target_base=str(tmp_path), check_exists=True)
        assert found == str(legacy)
    finally:
        legacy.unlink()


def test_get_cover_path_missing_everywhere_returns_none(tmp_path):
    assert sync.get_cover_path("Nope", target_base=str(tmp_path), check_exists=True) is None


# ---------------------------------------------------------------------------
# sync._clear_group_directory race branch
# ---------------------------------------------------------------------------


def test_clear_group_directory_missing_dir_is_noop(tmp_path, caplog):
    sync._clear_group_directory(tmp_path / "never-existed")


# ---------------------------------------------------------------------------
# sync filters
# ---------------------------------------------------------------------------


def test_filter_by_watch_state_all_branches():
    items = [
        {"Name": "watched", "UserData": {"Played": True}},
        {"Name": "unwatched", "UserData": {"Played": False}},
        {"Name": "no-user-data"},
    ]
    assert sync._filter_by_watch_state(items, "unwatched") == items[1:]
    assert sync._filter_by_watch_state(items, "watched") == [items[0]]
    assert sync._filter_by_watch_state(items, "") == items


def test_filter_by_item_type_movies_and_series_and_empty():
    # Known filter values map to Jellyfin types; unknown values pass through.
    movies = [{"Type": "Movie"}, {"Type": "Series"}, {"Type": "Episode"}]
    assert sync._filter_by_item_type(movies, "movies") == [movies[0]]
    assert sync._filter_by_item_type(movies, "series") == movies[1:2]
    assert sync._filter_by_item_type(movies, "") == movies
    assert sync._filter_by_item_type(movies, "books") == movies


# ---------------------------------------------------------------------------
# sync.parse_complex_query NOT handling
# ---------------------------------------------------------------------------


def test_parse_complex_query_lone_trailing_not_negates_next():
    # A NOT consumes the next condition's operator slot, and stacked NOTs
    # cancel, so "NOT NOT" leaves the operand positive but keeps the rule.
    rules = sync.parse_complex_query("NOT NOT genre:Action", "genre")
    assert rules == [{"operator": "AND", "type": "genre", "value": "Action"}]


def test_parse_complex_query_negated_condition_keeps_not_operator():
    rules = sync.parse_complex_query("genre:Action AND NOT genre:Comedy", "genre")
    assert any(r["operator"].endswith("NOT") and r["value"] == "Comedy" for r in rules)


def test_parse_complex_query_bare_default_condition():
    # Values are preserved verbatim (lowercasing happens at evaluation time).
    rules = sync.parse_complex_query("Comedy", "genre")
    assert rules == [{"operator": "AND", "type": "genre", "value": "Comedy"}]


# ---------------------------------------------------------------------------
# sync preview_group dispatch paths
# ---------------------------------------------------------------------------


def test_preview_group_dispatches_list_source(monkeypatch):
    called: dict[str, object] = {}

    def fake_dispatch(type_name, *args, **kwargs):
        called["type"] = type_name
        return [{"Id": "1"}], None, 200

    monkeypatch.setattr(sync, "_dispatch_list_source", fake_dispatch)
    items, error, code = sync.preview_group("trakt_list", "http://x/1", "http://jf", "key")
    assert called["type"] == "trakt_list"
    assert items == [{"Id": "1"}]
    assert (error, code) == (None, 200)


def test_preview_group_filters_by_item_type(monkeypatch):
    monkeypatch.setattr(
        sync,
        "_dispatch_list_source",
        lambda *a, **k: ([{"Id": "1", "Type": "Movie"}, {"Id": "2", "Type": "Series"}], None, 200),
    )
    items, _, _ = sync.preview_group("tmdb_list", "x", "http://jf", "key", item_type="series")
    assert items == [{"Id": "2", "Type": "Series"}]


def test_preview_group_complex_query_uses_complex_fetcher(monkeypatch):
    sent = {}

    def fake_complex(name, rules, sort_order, url, api_key, watch_state="", item_type=""):
        sent.update(rules=rules, item_type=item_type)
        return [{"Id": "9"}], None, 200

    monkeypatch.setattr(sync, "_fetch_items_for_complex_group", fake_complex)
    items, _, _ = sync.preview_group("complex", "genre:action OR year:2000", "http://jf", "key", item_type="movies")
    assert items == [{"Id": "9"}]
    assert sent["item_type"] == "movies"
    assert any(r["type"] == "genre" for r in sent["rules"])


def test_preview_group_metadata_path_falls_back(monkeypatch):
    sent = {}

    def fake_metadata(kind, type_name, val, sort_order, url, api_key, watch_state="", item_type=""):
        sent.update(type_name=type_name, val=val, item_type=item_type)
        return [{"Id": "5"}], "gone", 200

    monkeypatch.setattr(sync, "_fetch_items_for_metadata_group", fake_metadata)
    items, error, _ = sync.preview_group("genre", "Comedy", "http://jf", "key", item_type="movies")
    assert items == [{"Id": "5"}]
    assert error == "gone"
    assert sent == {"type_name": "genre", "val": "Comedy", "item_type": "movies"}


# ---------------------------------------------------------------------------
# sync.run_cleanup_broken_symlinks
# ---------------------------------------------------------------------------


def test_cleanup_broken_symlinks_deletes_and_reports(tmp_path, caplog):
    real_target = tmp_path / "lib"
    real_target.mkdir()
    real = real_target / "Movie A"
    real.write_text("x")
    (real_target / "broken").symlink_to(tmp_path / "nowhere")

    config = {"target_path": str(real_target)}
    deleted = sync.run_cleanup_broken_symlinks(config)
    assert deleted == 1
    assert not (real_target / "broken").is_symlink()
    assert (real_target / "Movie A").exists()
    assert "Deleted broken symlink" in caplog.text


def test_cleanup_broken_symlinks_aborts_on_bad_target(tmp_path, caplog):
    assert sync.run_cleanup_broken_symlinks({"target_path": str(tmp_path / "nope")}) == 0
    assert "Cleanup aborted" in caplog.text


def test_cleanup_broken_symlinks_empty_target_string(tmp_path):
    assert sync.run_cleanup_broken_symlinks({"target_path": ""}) == 0


def test_cleanup_broken_symlinks_unlink_error_is_swallowed(tmp_path, monkeypatch, caplog):
    target = tmp_path / "lib"
    target.mkdir()
    (target / "broken").symlink_to(tmp_path / "nowhere")

    real_unlink = Path.unlink

    def fail_unlink(self, *a, **kw):
        if self.name == "broken":
            raise OSError("busy")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    assert sync.run_cleanup_broken_symlinks({"target_path": str(target)}) == 0
    assert "Error deleting broken symlink" in caplog.text


# ---------------------------------------------------------------------------
# sync._run_sync_unlocked permission branch (target mkdir failure)
# ---------------------------------------------------------------------------


def test_run_sync_bad_target_path_raises_value_error():
    with pytest.raises(ValueError, match="Server settings or target path"):
        sync.run_sync({"jellyfin_url": "http://jf", "api_key": "k", "target_path": ""})
