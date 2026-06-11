"""Additional tests covering remaining uncovered lines in routes.py and sync.py."""

import os
from unittest.mock import patch

import pytest

from config import save_config
from routes import _compute_common_root

# ---------------------------------------------------------------------------
# Routes line 135: auth bypass for index with password set
# ---------------------------------------------------------------------------


def test_check_auth_bypass_index_endpoint(app, monkeypatch) -> None:
    """When APP_PASSWORD is set, the index page is accessible without auth."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    response = app.test_client().get("/")
    assert response.status_code == 200


def test_check_auth_bypass_removed_test_dashboard(app, monkeypatch) -> None:
    """When APP_PASSWORD is set, the removed /test route returns 404 (no auth bypass needed)."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    response = app.test_client().get("/test")
    assert response.status_code == 404


def test_check_auth_valid_password(app, monkeypatch) -> None:
    """Correct password in Basic Auth header allows access."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    from base64 import b64encode

    creds = b64encode(b":secret").decode()
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
) -> None:
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
) -> None:
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


def test_translate_path_fallback(tmp_path) -> None:
    """_translate_path returns original path when translation fails."""
    from sync import _translate_path

    # When path is not under jellyfin_root, returns unchanged
    result = _translate_path("/unrelated/movie.mkv", str(tmp_path / "media"), "/host")
    assert result == "/unrelated/movie.mkv"


# ---------------------------------------------------------------------------
# _compute_common_root edge cases
# ---------------------------------------------------------------------------


def test_auto_detect_multi_common_path() -> None:
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


def test_auto_detect_same_path() -> None:
    """Identical paths return root as os.sep."""
    result_j, result_h = _compute_common_root("/a/b/c.mkv", "/a/b/c.mkv")
    assert result_j == os.sep
    assert result_h == os.sep


def test_auto_detect_no_match() -> None:
    """No matching trailing components returns None."""
    result_j, result_h = _compute_common_root("/a/b/x.mkv", "/c/d/y.mkv")
    assert result_j is None
    assert result_h is None


# ---------------------------------------------------------------------------
# _validate_config_types tests
# ---------------------------------------------------------------------------


def test_validate_config_types_non_string_fields() -> None:
    """Non-string string fields are flagged."""
    from routes import _validate_config_types

    for field in (
        "jellyfin_url",
        "api_key",
        "target_path",
        "media_path_in_jellyfin",
        "media_path_on_host",
        "target_path_in_jellyfin",
        "anilist_api_url",
        "trakt_client_id",
        "tmdb_api_key",
        "mal_client_id",
    ):
        errors = _validate_config_types({field: 123})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_non_list_groups() -> None:
    """Non-list groups field is flagged."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": "not_a_list"})
    assert any("'groups'" in e for e in errors)


def test_validate_config_types_non_bool_fields() -> None:
    """Non-boolean bool fields are flagged."""
    from routes import _validate_config_types

    for field in ("auto_create_libraries", "auto_set_library_covers", "setup_done"):
        errors = _validate_config_types({field: "not_bool"})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_scheduler_non_dict() -> None:
    """Scheduler must be a dict."""
    from routes import _validate_config_types

    errors = _validate_config_types({"scheduler": "not_a_dict"})
    assert any("'scheduler' must be an object" in e for e in errors)


def test_validate_config_types_scheduler_bool_mismatch() -> None:
    """Scheduler bool fields are checked."""
    from routes import _validate_config_types

    for field in ("global_enabled", "cleanup_enabled"):
        cfg = {"scheduler": {field: "not_bool"}}
        errors = _validate_config_types(cfg)
        assert any(f"scheduler.{field}" in e for e in errors), (
            f"Expected error for scheduler.{field}"
        )


def test_validate_config_types_scheduler_str_mismatch() -> None:
    """Scheduler str fields are checked."""
    from routes import _validate_config_types

    for field in ("global_schedule", "cleanup_schedule"):
        cfg = {"scheduler": {field: 123}}
        errors = _validate_config_types(cfg)
        assert any(f"scheduler.{field}" in e for e in errors), (
            f"Expected error for scheduler.{field}"
        )


def test_validate_config_types_scheduler_exclude_non_list() -> None:
    """Scheduler global_exclude_ids must be a list."""
    from routes import _validate_config_types

    errors = _validate_config_types({"scheduler": {"global_exclude_ids": "not_list"}})
    assert any("global_exclude_ids" in e for e in errors)


def test_validate_config_types_group_non_dict() -> None:
    """Group items must be dicts."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": ["not_a_dict"]})
    assert any("groups[0] must be an object" in e for e in errors)


def test_validate_config_types_group_name_non_string() -> None:
    """Group names must be strings."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": 123}]})
    assert any("groups[0].name must be a string" in e for e in errors)


def test_validate_config_types_group_source_type_non_string() -> None:
    """Group source_type must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "source_type": 123}]})
    assert any("groups[0].source_type" in e for e in errors)


def test_validate_config_types_group_source_value_non_string() -> None:
    """Group source_value must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "source_value": 123}]})
    assert any("groups[0].source_value" in e for e in errors)


def test_validate_config_types_group_sort_order_non_string() -> None:
    """Group sort_order must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "sort_order": 123}]})
    assert any("groups[0].sort_order" in e for e in errors)


def test_validate_config_types_group_watch_state_non_string() -> None:
    """Group watch_state must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "watch_state": 123}]})
    assert any("groups[0].watch_state" in e for e in errors)


def test_validate_config_types_group_schedule_non_string() -> None:
    """Group schedule must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "schedule": 123}]})
    assert any("groups[0].schedule" in e for e in errors)


def test_validate_config_types_group_bool_fields() -> None:
    """Group boolean fields are checked."""
    from routes import _validate_config_types

    for field in ("schedule_enabled", "seasonal_enabled", "create_as_collection"):
        errors = _validate_config_types({"groups": [{"name": "G", field: "not_bool"}]})
        assert any(f"groups[0].{field}" in e for e in errors), (
            f"Expected error for groups[0].{field}"
        )


def test_validate_config_types_group_seasonal_date_invalid() -> None:
    """Invalid seasonal date format is flagged."""
    from routes import _validate_config_types

    for field in ("seasonal_start", "seasonal_end"):
        errors = _validate_config_types({"groups": [{"name": "G", field: "bad-date"}]})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_group_seasonal_date_valid() -> None:
    """Valid seasonal date format passes."""
    from routes import _validate_config_types

    for field in ("seasonal_start", "seasonal_end"):
        errors = _validate_config_types({"groups": [{"name": "G", field: "10-31"}]})
        assert not any(field in e for e in errors), (
            f"No error expected for valid {field}"
        )


def test_validate_config_types_group_seasonal_date_non_string() -> None:
    """Non-string seasonal date is flagged."""
    from routes import _validate_config_types

    for field in ("seasonal_start", "seasonal_end"):
        errors = _validate_config_types({"groups": [{"name": "G", field: 123}]})
        assert any(field in e for e in errors), f"Expected error for {field}"


def test_validate_config_types_group_rules_non_list() -> None:
    """Group rules must be a list."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "rules": "not_list"}]})
    assert any("groups[0].rules" in e for e in errors)


def test_validate_config_types_group_rules_item_non_dict() -> None:
    """Each item in rules must be a dict."""
    from routes import _validate_config_types

    errors = _validate_config_types({"groups": [{"name": "G", "rules": ["not_dict"]}]})
    assert any("groups[0].rules[0]" in e for e in errors)


def test_validate_config_types_group_rules_type_non_string() -> None:
    """Rule type field must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types(
        {"groups": [{"name": "G", "rules": [{"type": 123}]}]}
    )
    assert any("groups[0].rules[0].type" in e for e in errors)


def test_validate_config_types_group_rules_value_non_string() -> None:
    """Rule value field must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types(
        {"groups": [{"name": "G", "rules": [{"value": 123}]}]}
    )
    assert any("groups[0].rules[0].value" in e for e in errors)


def test_validate_config_types_group_rules_operator_non_string() -> None:
    """Rule operator field must be a string."""
    from routes import _validate_config_types

    errors = _validate_config_types(
        {"groups": [{"name": "G", "rules": [{"operator": 123}]}]}
    )
    assert any("groups[0].rules[0].operator" in e for e in errors)


def test_validate_config_types_group_rules_not_non_bool() -> None:
    """Rule not field must be a boolean."""
    from routes import _validate_config_types

    errors = _validate_config_types(
        {"groups": [{"name": "G", "rules": [{"not": "not_bool"}]}]}
    )
    assert any("groups[0].rules[0].not" in e for e in errors)


def test_validate_config_types_jellyfin_url_bad_format() -> None:
    """jellyfin_url without http(s):// prefix is flagged."""
    from routes import _validate_config_types

    errors = _validate_config_types({"jellyfin_url": "localhost:8096"})
    assert any("jellyfin_url" in e and "http" in e.lower() for e in errors)


def test_validate_config_types_jellyfin_url_valid_http() -> None:
    """jellyfin_url with http:// passes."""
    from routes import _validate_config_types

    errors = _validate_config_types({"jellyfin_url": "http://localhost:8096"})
    assert not any("jellyfin_url" in e for e in errors)


def test_validate_config_types_jellyfin_url_valid_https() -> None:
    """jellyfin_url with https:// passes."""
    from routes import _validate_config_types

    errors = _validate_config_types({"jellyfin_url": "https://jellyfin.example.com"})
    assert not any("jellyfin_url" in e for e in errors)


def test_validate_config_types_valid_passthrough() -> None:
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


def test_validate_config_types_empty_config() -> None:
    """Empty config produces no errors (all fields optional)."""
    from routes import _validate_config_types

    errors = _validate_config_types({})
    assert errors == []


def test_update_config_rejects_bad_types(client, temp_config) -> None:
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


def test_auto_detect_partial_match() -> None:
    """Only some trailing components match."""
    result_j, result_h = _compute_common_root(
        "/movies/action/D.mkv",
        "/host/media/action/D.mkv",
    )
    # Trailing matches: D.mkv, action = 2 components
    assert result_j == "/movies"
    assert result_h == "/host/media"


# ---------------------------------------------------------------------------
# Health endpoint coverage
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_health_check_configured(client) -> None:
    """
    GET /api/health returns ok status, configured=True when
    jellyfin_url, api_key, and target_path are all set.
    """
    from config import save_config

    save_config(
        {
            "jellyfin_url": "http://jellyfin:8096",
            "api_key": "test-key-123",
            "target_path": "/media/groupings",
            "groups": [{"name": "Movies"}, {"name": "Shows"}],
        },
    )
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["healthcheck"]["ok"] is True
    assert data["healthcheck"]["configured"] is True
    assert data["healthcheck"]["groups"] == 2


@pytest.mark.usefixtures("temp_config")

# ---------------------------------------------------------------------------
# _validate_cron_expressions direct unit tests
# ---------------------------------------------------------------------------


def test_validate_cron_expressions_global_disabled() -> None:
    """No error when global_enabled is False with invalid schedule."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"global_enabled": False, "global_schedule": "invalid"},
    })
    assert errors == []


def test_validate_cron_expressions_global_enabled_bad() -> None:
    """Error when global_enabled is True with invalid schedule."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"global_enabled": True, "global_schedule": "bad"},
    })
    assert any("Global schedule" in e for e in errors)


def test_validate_cron_expressions_global_enabled_valid() -> None:
    """No error when global_enabled is True with valid schedule."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"global_enabled": True, "global_schedule": "0 0 * * *"},
    })
    assert errors == []


def test_validate_cron_expressions_cleanup_disabled() -> None:
    """No error when cleanup is disabled with invalid schedule."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"cleanup_enabled": False, "cleanup_schedule": "invalid"},
    })
    assert errors == []


def test_validate_cron_expressions_cleanup_enabled_bad() -> None:
    """Error when cleanup is enabled with invalid schedule."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"cleanup_enabled": True, "cleanup_schedule": "bad"},
    })
    assert any("Cleanup schedule" in e for e in errors)


def test_validate_cron_expressions_cleanup_empty_schedule() -> None:
    """Empty cleanup schedule doesn't cause error even when enabled."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {"cleanup_enabled": True, "cleanup_schedule": ""},
    })
    assert errors == []


def test_validate_cron_expressions_group_disabled() -> None:
    """No error when group schedule is disabled with bad cron."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "groups": [{"name": "G1", "schedule_enabled": False, "schedule": "invalid"}],
    })
    assert errors == []


def test_validate_cron_expressions_group_enabled_bad() -> None:
    """Error when group schedule is enabled with bad cron."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "groups": [{"name": "G1", "schedule_enabled": True, "schedule": "bad"}],
    })
    assert any("G1" in e for e in errors)


def test_validate_cron_expressions_group_enabled_no_schedule() -> None:
    """No error when group schedule is enabled but no schedule set."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "groups": [{"name": "G1", "schedule_enabled": True}],
    })
    assert errors == []


def test_validate_cron_expressions_all_valid() -> None:
    """No errors when all expressions are valid."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "0 0 * * *",
            "cleanup_enabled": True,
            "cleanup_schedule": "0 * * * *",
        },
        "groups": [
            {"name": "G1", "schedule_enabled": True, "schedule": "*/30 * * * *"},
        ],
    })
    assert errors == []


def test_validate_cron_expressions_group_no_name() -> None:
    """Unnamed group uses "unnamed" in error message."""
    from routes import _validate_cron_expressions

    errors = _validate_cron_expressions({
        "groups": [{"schedule_enabled": True, "schedule": "bad"}],
    })
    assert any("unnamed" in e for e in errors)
