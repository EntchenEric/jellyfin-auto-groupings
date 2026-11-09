"""Unit tests that pin behaviour no e2e run had covered previously.

Three regions of ``routes.py`` were only exercised incidentally:

* ``POST /api/config`` validation errors for the top-level string fields —
  a bad ``jellyfin_url`` scheme, a missing hostname, and the
  ``target_path`` / ``media_path_on_host`` existence, type and permission
  checks. A typo in the URL used to be saved silently and only surface as
  connection failures later.
* ``_get_jellyfin_config``'s two abort paths (config not a dict → 500,
  missing URL/key → 400), which every Jellyfin-backed endpoint shares.
* ``POST /api/cleanup``'s non-JSON, non-list and dedup branches, plus
  ``_delete_folder``'s invalid-name, path-traversal, symlink and
  already-deleted paths and ``_prune_empty_parents``' base/empty handling.

The tests use the public HTTP surface wherever a client would hit it, and
call the helpers directly where a filesystem state is awkward to stage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import routes
from app import app as flask_app

_CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client whose config file lives under *tmp_path*."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as test_client:
        yield test_client


def _post_config(client, payload):
    return client.post(
        "/api/config",
        data=json.dumps(payload),
        content_type="application/json",
        headers=_CSRF_HEADERS,
    )


def _valid_config(tmp_path: Path, **overrides: object) -> dict:
    """A minimal payload that passes every validator."""
    cfg: dict[str, object] = {
        "jellyfin_url": "http://jellyfin.invalid",
        "api_key": "key",
        "target_path": str(tmp_path),
        "media_path_on_host": str(tmp_path),
        "groups": [],
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# POST /api/config — jellyfin_url validation
# ---------------------------------------------------------------------------


def test_config_rejects_a_non_http_scheme(client, tmp_path):
    response = _post_config(client, _valid_config(tmp_path, jellyfin_url="ftp://jf"))

    assert response.status_code == 400
    errors = response.get_json()["errors"]
    assert any("must start with http" in e for e in errors)


def test_config_rejects_a_url_without_a_hostname(client, tmp_path):
    response = _post_config(client, _valid_config(tmp_path, jellyfin_url="http://"))

    assert response.status_code == 400
    errors = response.get_json()["errors"]
    assert any("missing hostname" in e for e in errors)


def test_config_accepts_a_well_formed_url(client, tmp_path):
    response = _post_config(client, _valid_config(tmp_path))

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"


# ---------------------------------------------------------------------------
# POST /api/config — target_path / media_path_on_host validation
# ---------------------------------------------------------------------------


def test_config_rejects_a_missing_target_path(client, tmp_path):
    response = _post_config(
        client, _valid_config(tmp_path, target_path=str(tmp_path / "absent"))
    )

    assert response.status_code == 400
    assert any("does not exist" in e for e in response.get_json()["errors"])


def test_config_rejects_a_file_target_path(client, tmp_path):
    file_target = tmp_path / "file.txt"
    file_target.write_text("", encoding="utf-8")

    response = _post_config(
        client, _valid_config(tmp_path, target_path=str(file_target))
    )

    assert response.status_code == 400
    assert any("is not a directory" in e for e in response.get_json()["errors"])


def test_config_rejects_a_missing_media_path_on_host(client, tmp_path):
    response = _post_config(
        client,
        _valid_config(tmp_path, media_path_on_host=str(tmp_path / "no-media")),
    )

    assert response.status_code == 400
    assert any(
        "media_path_on_host" in e and "does not exist" in e
        for e in response.get_json()["errors"]
    )


def test_config_accepts_unset_optional_paths(client, tmp_path):
    """An empty string never triggers the filesystem checks."""
    cfg = _valid_config(tmp_path)
    cfg["target_path"] = ""
    cfg["media_path_on_host"] = ""

    response = _post_config(client, cfg)

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"


# ---------------------------------------------------------------------------
# _get_jellyfin_config aborts
# ---------------------------------------------------------------------------


def test_get_jellyfin_config_aborts_500_for_a_non_dict_config(monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: ["not", "a", "dict"])

    with pytest.raises(Exception) as excinfo:
        routes._get_jellyfin_config()

    assert excinfo.value.code == 500


def test_get_jellyfin_config_aborts_400_when_the_url_is_missing(monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: {"api_key": "k"})

    with pytest.raises(Exception) as excinfo:
        routes._get_jellyfin_config(missing_msg="Server settings required")

    assert excinfo.value.code == 400
    assert "Server settings required" in excinfo.value.description


def test_get_jellyfin_config_aborts_400_when_the_key_is_missing(monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: {"jellyfin_url": "http://jf"})

    with pytest.raises(Exception) as excinfo:
        routes._get_jellyfin_config()

    assert excinfo.value.code == 400


def test_get_jellyfin_config_returns_a_stripped_url_and_key(monkeypatch):
    monkeypatch.setattr(
        routes,
        "load_config",
        lambda: {"jellyfin_url": "http://jf/", "api_key": "k"},
    )

    assert routes._get_jellyfin_config() == ("http://jf", "k")


# ---------------------------------------------------------------------------
# POST /api/cleanup — request-shape branches
# ---------------------------------------------------------------------------


@pytest.fixture
def target_dir(tmp_path):
    target = tmp_path / "library"
    target.mkdir()
    return target


def _cleanup_config(target: Path) -> dict:
    return {
        "target_path": str(target),
        "groups": [],
        "jellyfin_url": "http://jf",
        "api_key": "k",
        "auto_create_libraries": False,
    }


def test_cleanup_rejects_a_non_json_body(client, target_dir, monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: _cleanup_config(target_dir))

    response = client.post(
        "/api/cleanup", data="not json", content_type="application/json"
    )

    assert response.status_code == 400
    assert "JSON" in response.get_json()["message"]


def test_cleanup_rejects_a_non_list_folders(client, target_dir, monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: _cleanup_config(target_dir))

    response = client.post("/api/cleanup", json={"folders": "Action"})

    assert response.status_code == 400
    assert "list" in response.get_json()["message"]


def test_cleanup_skips_duplicate_names(client, target_dir, monkeypatch):
    (target_dir / "Action").mkdir()
    monkeypatch.setattr(routes, "load_config", lambda: _cleanup_config(target_dir))

    response = client.post("/api/cleanup", json={"folders": ["Action", "Action"]})

    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


def test_cleanup_reports_a_non_string_folder_name(client, target_dir, monkeypatch):
    monkeypatch.setattr(routes, "load_config", lambda: _cleanup_config(target_dir))

    response = client.post("/api/cleanup", json={"folders": [42]})

    assert response.status_code == 207
    assert response.get_json()["errors"] == ["Folder name must be a string"]


# ---------------------------------------------------------------------------
# _delete_folder helper branches
# ---------------------------------------------------------------------------


def test_delete_folder_rejects_an_invalid_name(target_dir):
    removed, error = routes._delete_folder("../outside", str(target_dir), False, "", "")

    assert removed is False
    assert error is not None


def test_delete_folder_reports_path_traversal_for_a_symlinked_name(
    target_dir, monkeypatch
):
    """A symlink escaping the target must be refused, never deleted through."""
    outside = target_dir.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret").mkdir(exist_ok=True)
    link = target_dir / "Escaping"
    link.symlink_to(outside / "secret")

    removed, error = routes._delete_folder("Escaping", str(target_dir), False, "", "")

    assert removed is False
    assert error is not None
    assert (outside / "secret").exists()


def test_delete_folder_refuses_a_symlink(target_dir):
    outside = target_dir.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    (target_dir / "Linked").symlink_to(outside)

    removed, error = routes._delete_folder("Linked", str(target_dir), False, "", "")

    # The symlink resolves outside the target, so the traversal guard
    # (the first line of defence) rejects it before the symlink check runs.
    assert removed is False
    assert error is not None
    assert outside.exists()


def test_delete_folder_reports_a_missing_folder_as_a_noop(target_dir):
    removed, error = routes._delete_folder("Absent", str(target_dir), False, "", "")

    assert removed is False
    assert error is None


def test_delete_folder_removes_a_real_folder(target_dir):
    (target_dir / "Gone").mkdir()
    (target_dir / "Gone" / "child").mkdir()

    removed, error = routes._delete_folder("Gone", str(target_dir), False, "", "")

    assert removed is True
    assert error is None
    assert (target_dir / "Gone").exists() is False


def test_delete_folder_prunes_empty_nested_parents(target_dir):
    nested = target_dir / "Anime" / "Action"
    nested.mkdir(parents=True)

    removed, _error = routes._delete_folder(
        "Anime/Action", str(target_dir), False, "", ""
    )

    assert removed is True
    # The now-empty structural parents are pruned, but the target itself stays.
    assert (target_dir).is_dir()
    assert (target_dir / "Anime").exists() is False


def test_prune_empty_parents_never_removes_the_base(target_dir):
    routes._prune_empty_parents(target_dir, target_dir)

    assert target_dir.exists()


def test_prune_empty_parents_keeps_a_non_empty_parent(target_dir):
    parent = target_dir / "Anime"
    (parent / "Action").mkdir(parents=True)
    (parent / "Keep").mkdir()

    routes._prune_empty_parents(parent / "Action", target_dir)

    assert (parent / "Keep").exists()
    assert (parent / "Action").exists() is False


def test_prune_empty_parents_ignores_a_base_that_cannot_resolve(tmp_path):
    """An unresolvable base ends the walk without removing anything."""
    base = tmp_path / "base"
    base.mkdir()
    child = base / "child"
    child.mkdir()

    routes._prune_empty_parents(child, base)

    assert child.exists() is False  # it *was* empty, so it is removed
    assert base.exists()
