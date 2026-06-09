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
    mock_ismount, mock_isdir, mock_walk, mock_fetch, client,
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
    mock_fetch, mock_isdir, mock_walk, mock_ismount, mock_access, client,
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


def test_auto_detect_partial_match():
    """Only some trailing components match."""
    result_j, result_h = _compute_common_root(
        "/movies/action/D.mkv",
        "/host/media/action/D.mkv",
    )
    # Trailing matches: D.mkv, action = 2 components
    assert result_j == "/movies"
    assert result_h == "/host/media"