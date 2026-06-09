"""Additional tests covering remaining uncovered lines in routes.py and sync.py."""

import os
from unittest.mock import patch

import pytest

from config import save_config
from routes import _compute_common_root

# ---------------------------------------------------------------------------
# Routes line 136: auth bypass for index/test_dashboard with password set
# ---------------------------------------------------------------------------


def test_check_auth_bypass_index_endpoint(app, monkeypatch):
    """When APP_PASSWORD is set, the index page is accessible without auth."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    response = app.test_client().get("/")
    assert response.status_code == 200


def test_check_auth_bypass_test_dashboard(app, monkeypatch):
    """When APP_PASSWORD is set, the test dashboard is accessible without auth."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    response = app.test_client().get("/test")
    assert response.status_code == 200


def test_check_auth_valid_password(app, monkeypatch):
    """Correct password in Basic Auth header allows access."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    from base64 import b64encode

    creds = b64encode(":secret".encode()).decode()
    response = app.test_client().get(
        "/api/config",
        headers={"Authorization": f"Basic {creds}"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Routes line 745: search root is not a directory (continue in walk loop)
# ---------------------------------------------------------------------------


@patch("routes.fetch_jellyfin_items")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.os.path.ismount")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_skip_non_dir_root(
    mock_ismount,
    mock_isdir,
    mock_walk,
    mock_fetch,
    client,
):
    """Search roots that are not directories are skipped."""
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    # First call (checking root) returns False -> skip, then second call for fallback root
    mock_isdir.side_effect = [False, True]
    mock_ismount.return_value = False
    mock_walk.return_value = [("/media/movies", [], ["M1.mkv"])]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Routes line 858: suggested_target fallback when home dir not writable
# ---------------------------------------------------------------------------


@patch("routes.os.access")
@patch("routes.os.path.ismount")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_home_not_writable(
    mock_fetch,
    mock_isdir,
    mock_walk,
    mock_ismount,
    mock_access,
    client,
):
    """When home dir is not writable, suggested_target uses CWD fallback."""
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    mock_walk.return_value = [("/media/movies", [], ["M1.mkv"])]
    mock_access.return_value = False
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200
    data = response.get_json()
    assert "jellyfin-groupings-virtual" in data["detected"]["target_path"]


# ---------------------------------------------------------------------------
# Sync line 160-161: OSError/ValueError except in _translate_path
# ---------------------------------------------------------------------------


def test_translate_path_fallback(tmp_path):
    """_translate_path returns original path when translation fails."""
    from sync import _translate_path

    # When path is not under jellyfin_root, returns unchanged
    result = _translate_path("/unrelated/movie.mkv", str(tmp_path / "media"), "/host")
    assert result == "/unrelated/movie.mkv"


# ---------------------------------------------------------------------------
# _compute_common_root edge cases
# ---------------------------------------------------------------------------


def test_auto_detect_multi_common_path():
    """Multiple trailing path components match."""
    result_j, result_h = _compute_common_root(
        "/media/movies/action/D.mkv",
        "/jellyfin/media/movies/action/D.mkv",
    )
    # Trailing matches: D.mkv, action, movies, media = 4 components
    # j_root: / stripped to root → os.sep
    # h_root: /jellyfin
    assert result_j == os.sep
    assert result_h == "/jellyfin"


def test_auto_detect_same_path():
    """Identical paths return root as os.sep."""
    result_j, result_h = _compute_common_root("/a/b/c.mkv", "/a/b/c.mkv")
    assert result_j == os.sep
    assert result_h == os.sep


def test_auto_detect_no_match():
    """No matching trailing components returns None."""
    result_j, result_h = _compute_common_root("/a/b/x.mkv", "/c/d/y.mkv")
    assert result_j is None
    assert result_h is None


# ---------------------------------------------------------------------------
# _validate_config_types tests
# ---------------------------------------------------------------------------


def test_validate_config_types_non_string_fields():
    """Non-string string fields are flagged."""
    from routes import _validate_config_types

    for field in (
        "jellyfin_url",
        "target_path",
        "media_path_in_jellyfin",
        "media_path_on_host",
        "target_path_in_jellyfin",
    ):
        errors = _validate_config_types({field: 123})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_non_list_groups():
    """Non-list groups field is flagged."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": "not_a_list"})
    assert any("'groups'" in e for e in errors)


def test_validate_config_types_non_bool_fields():
    """Non-boolean bool fields are flagged."""
    from routes import _validate_config_types

    for field in ("auto_create_libraries", "auto_set_library_covers", "setup_done"):
        errors = _validate_config_types({field: "not_bool"})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_scheduler_non_dict():
    """Scheduler must be a dict."""
    from routes import _validate_config_types

    errors = _validate_config_types({"scheduler": "not_a_dict"})
    assert any("'scheduler' must be an object" in e for e in errors)


def test_validate_config_types_scheduler_bool_mismatch():
    """Scheduler bool fields are checked."""
    from routes import _validate_config_types

    for field in ("global_enabled", "cleanup_enabled"):
        cfg = {"scheduler": {field: "not_bool"}}
        errors = _validate_config_types(cfg)
        assert any(f"scheduler.{field}" in e for e in errors), (
            f"Expected error for scheduler.{field}"
        )


def test_validate_config_types_scheduler_str_mismatch():
    """Scheduler str fields are checked."""
    from routes import _validate_config_types

    for field in ("global_schedule", "cleanup_schedule"):
        cfg = {"scheduler": {field: 123}}
        errors = _validate_config_types(cfg)
        assert any(f"scheduler.{field}" in e for e in errors), (
            f"Expected error for scheduler.{field}"
        )


def test_validate_config_types_scheduler_exclude_non_list():
    """Scheduler global_exclude_ids must be a list."""
    from routes import _validate_config_types

    errors = _validate_config_types({"scheduler": {"global_exclude_ids": "not_list"}})
    assert any("global_exclude_ids" in e for e in errors)


def test_validate_config_types_group_non_dict():
    """Group items must be dicts."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": ["not_a_dict"]})
    assert any("groups[0] must be an object" in e for e in errors)


def test_validate_config_types_group_name_non_string():
    """Group names must be strings."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": 123}]})
    assert any("groups[0].name must be a string" in e for e in errors)


def test_validate_config_types_valid_passthrough():
    """Valid config produces no errors."""
    from routes import _validate_config_types

    valid_config = {
        "jellyfin_url": "http://localhost:8096",
        "target_path": "/virtual",
        "media_path_in_jellyfin": "/data/media",
        "media_path_on_host": "/media",
        "target_path_in_jellyfin": "/virtual",
        "groups": [{"name": "TestGroup"}],
        "auto_create_libraries": False,
        "auto_set_library_covers": True,
        "setup_done": True,
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "0 0 * * *",
            "cleanup_enabled": False,
            "cleanup_schedule": "0 * * * *",
            "global_exclude_ids": ["Excluded"],
        },
    }
    errors = _validate_config_types(valid_config)
    assert errors == []


def test_validate_config_types_empty_config():
    """Empty config produces no errors (all fields optional)."""
    from routes import _validate_config_types

    errors = _validate_config_types({})
    assert errors == []


def test_update_config_rejects_bad_types(client, temp_config):
    """POST /api/config with wrong type returns 400."""
    from config import save_config

    save_config({})
    response = client.post(
        "/api/config",
        json={"jellyfin_url": 12345},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data is not None
    assert (
        "type" in data.get("error", "").lower()
        or "type" in data.get("message", "").lower()
    )


def test_auto_detect_partial_match():
    """Only some trailing components match."""
    result_j, result_h = _compute_common_root(
        "/movies/action/D.mkv",
        "/host/media/action/D.mkv",
    )
    # Trailing matches: D.mkv, action = 2 components
    assert result_j == "/movies"
    assert result_h == "/host/media"
