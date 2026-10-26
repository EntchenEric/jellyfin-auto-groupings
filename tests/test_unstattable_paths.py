"""A path the kernel refuses to ``stat`` must not become an HTTP 500.

``Path.exists()`` and ``Path.is_dir()`` run ``stat`` and only swallow the
"not there" errors (``ENOENT``, ``ENOTDIR``, ``ELOOP``). A path the kernel
rejects outright still raises: a single component longer than ``NAME_MAX``
(255 bytes on ext4) yields ``OSError(ENAMETOOLONG)``, and a damaged entry can
yield ``EIO``.

Every handler that inspects a user-supplied path opened with one of those
calls unguarded, so a long value aborted the request:

* ``GET /api/browse?path=<4000 chars>`` — ``Path(raw).resolve()`` succeeds
  because only the existing parts are resolved, then ``is_dir()`` raises and
  Flask answered with an unhandled 500 instead of the ``400`` every other
  malformed path gets.
* ``POST /api/cleanup`` with a long ``folders`` entry — ``_delete_folder``
  called ``path.exists()`` and the whole request failed, discarding the other
  (deletable) folders in the same body.
* ``GET``/``POST /api/cleanup`` with a long ``target_path`` in the config —
  the guard that is supposed to answer "nothing to list" / "target path not
  found" raised before it could return.

The fix routes those checks through ``routes._safe_exists`` /
``routes._safe_is_dir``, which treat an unstattable path as absent and log it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
from app import app as flask_app

#: One path component past the ext4 ``NAME_MAX`` of 255 bytes.
_TOO_LONG = "a" * 4000


@pytest.fixture
def client():
    """Flask test client for the API blueprint.

    State-changing requests must carry the CSRF marker header, exactly as the
    SPA's ``fetch`` wrapper sends it.
    """
    flask_app.config.update(TESTING=False)
    test_client = flask_app.test_client()
    test_client.environ_base["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    return test_client


@pytest.fixture
def target_dir(tmp_path):
    """A writable target directory used as ``target_path``."""
    return tmp_path


def _config_for(target: object, **overrides: object) -> dict:
    """Return the minimal config the cleanup endpoints read."""
    config: dict[str, object] = {
        "target_path": str(target),
        "groups": [],
        "jellyfin_url": "",
        "api_key": "",
        "auto_create_libraries": False,
    }
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_safe_exists_treats_oserror_as_absent():
    assert routes._safe_exists("/" + _TOO_LONG) is False


def test_safe_is_dir_treats_oserror_as_absent():
    assert routes._safe_is_dir("/" + _TOO_LONG) is False


def test_safe_exists_and_is_dir_report_real_paths(target_dir):
    assert routes._safe_exists(target_dir) is True
    assert routes._safe_is_dir(target_dir) is True
    assert routes._safe_exists(target_dir / "missing") is False
    assert routes._safe_is_dir(target_dir / "missing") is False


# ---------------------------------------------------------------------------
# GET /api/browse
# ---------------------------------------------------------------------------


def test_browse_rejects_an_overlong_path_with_400(client, tmp_path, monkeypatch):
    """A name the kernel refuses is a bad request, not a server error."""
    monkeypatch.setattr(routes, "_BROWSE_ROOTS", (str(tmp_path),))

    response = client.get("/api/browse", query_string={"path": "/" + _TOO_LONG})

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_browse_still_lists_a_normal_root(client, tmp_path, monkeypatch):
    """The guard must not change the happy path."""
    (tmp_path / "Alpha").mkdir()
    (tmp_path / "Zeta").mkdir()
    monkeypatch.setattr(routes, "_BROWSE_ROOTS", (str(tmp_path),))

    response = client.get("/api/browse", query_string={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.get_json()["dirs"] == ["Alpha", "Zeta"]


# ---------------------------------------------------------------------------
# POST /api/cleanup
# ---------------------------------------------------------------------------


def test_cleanup_reports_only_the_unstattable_folder(client, target_dir, monkeypatch):
    """One bad name fails that entry; the rest of the request still runs."""
    (target_dir / "Real").mkdir()
    monkeypatch.setattr(routes, "load_config", lambda: _config_for(target_dir))

    response = client.post(
        "/api/cleanup",
        json={"folders": [_TOO_LONG, "Real"]},
    )

    assert response.status_code == 207, response.get_json()
    body = response.get_json()
    # The good folder was deleted even though it shared the request.
    assert body["deleted"] == 1
    assert (target_dir / "Real").exists() is False
    assert len(body["errors"]) == 1
    assert "Failed to inspect" in body["errors"][0]


def test_cleanup_error_message_does_not_repeat_the_whole_name(
    client, target_dir, monkeypatch
):
    """A rejected name is elided so the message stays readable."""
    monkeypatch.setattr(routes, "load_config", lambda: _config_for(target_dir))

    response = client.post("/api/cleanup", json={"folders": [_TOO_LONG]})

    message = response.get_json()["errors"][0]
    assert len(message) < 500, message
    assert "more chars" in message


# ---------------------------------------------------------------------------
# target_path from the config
# ---------------------------------------------------------------------------


def test_get_cleanup_ignores_an_overlong_target_path(client, monkeypatch):
    """An unstattable target path lists nothing instead of raising."""
    monkeypatch.setattr(routes, "load_config", lambda: _config_for("/" + _TOO_LONG))

    response = client.get("/api/cleanup")

    assert response.status_code == 200
    assert response.get_json()["items"] == []


def test_post_cleanup_reports_missing_target_path(client, monkeypatch):
    """An unstattable target path answers 404, the same as a missing one."""
    monkeypatch.setattr(routes, "load_config", lambda: _config_for("/" + _TOO_LONG))

    response = client.post("/api/cleanup", json={"folders": ["Anime"]})

    assert response.status_code == 404
    assert response.get_json()["status"] == "error"


def test_get_cleanup_still_lists_real_folders(client, target_dir, monkeypatch):
    """The guard must not change the happy path."""
    (target_dir / "Leftover").mkdir()
    monkeypatch.setattr(routes, "load_config", lambda: _config_for(target_dir))

    response = client.get("/api/cleanup")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["items"]] == ["Leftover"]


# ---------------------------------------------------------------------------
# Regression: a raising stat is still reported as this folder's failure
# ---------------------------------------------------------------------------


def test_delete_folder_reports_a_raising_stat(monkeypatch, target_dir):
    """``_delete_folder`` answers ``(False, message)`` instead of raising."""
    real_exists = Path.exists

    def fake_exists(self):
        if self.name == "Broken":
            raise OSError(5, "Input/output error", "Broken")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    removed, error = routes._delete_folder(
        "Broken",
        str(target_dir),
        False,
        "",
        "",
    )

    assert removed is False
    assert error is not None
    assert "Failed to inspect" in error


def test_delete_folder_with_a_healthy_name_still_deletes(monkeypatch, target_dir):
    """The guard must not break ordinary deletion."""
    (target_dir / "Gone").mkdir()

    removed, error = routes._delete_folder("Gone", str(target_dir), False, "", "")

    assert (removed, error) == (True, None)
    assert (target_dir / "Gone").exists() is False
