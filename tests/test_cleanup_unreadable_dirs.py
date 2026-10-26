"""One unreadable directory must not blank the whole cleanup listing.

``GET /api/cleanup`` walks the target directory to offer leftover folders for
deletion.  The walk used a bare ``directory.iterdir()`` inside a single
``try`` that the handler wrapped in ``except OSError: return _error(..., 500)``.
A nested folder the service account cannot read is ordinary in practice (a
root-owned library directory, a mount that dropped away, a stale NFS handle),
and it made the endpoint answer HTTP 500 with *no* items — the user lost every
other deletable folder because of one they never asked about.

The walk now skips an unreadable subtree, logs it, and returns what it could
read.  These tests pin that behaviour for both the descent into a structural
parent and the top-level listing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from app import app as flask_app


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Point the config module at an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.fixture
def client():
    """Flask test client for the API blueprint."""
    flask_app.config.update(TESTING=False)
    return flask_app.test_client()


def _deny(path_to_deny: Path):
    """Patch ``Path.iterdir`` to raise ``PermissionError`` for one directory.

    ``os.chmod`` cannot express this portably: the suite may run as root (in a
    container, or the Docker image), where an unreadable mode bit is not
    enforced and the test would silently pass without reproducing the bug.
    Patching the one path keeps the reproduction independent of the user.
    """
    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        if self == path_to_deny:
            raise PermissionError(13, "Permission denied", str(self))
        return real_iterdir(self)

    return patch.object(Path, "iterdir", fake_iterdir)


def test_unreadable_nested_folder_keeps_other_items(temp_config, client, tmp_path):
    """A group nested under an unreadable parent must not fail the listing."""
    target = tmp_path / "library"
    target.mkdir()
    (target / "Anime" / "Blocked" / "Action").mkdir(parents=True)
    (target / "Standalone").mkdir()
    temp_config.write_text(
        json.dumps(
            {
                "target_path": str(target),
                # "Anime/Blocked" is a structural parent, so the walk descends
                # into it and hits the unreadable directory.
                "groups": [{"name": "Anime/Blocked/Action"}],
            }
        ),
        encoding="utf-8",
    )

    with _deny(target / "Anime" / "Blocked"):
        response = client.get("/api/cleanup")

    assert response.status_code == 200
    names = [item["name"] for item in response.get_json()["items"]]
    # The readable sibling survives; the unreadable subtree contributes nothing
    # because its contents cannot be enumerated.
    assert names == ["Standalone"]


def test_unreadable_entry_is_not_offered_for_deletion(temp_config, client, tmp_path):
    """An entry whose ``stat`` fails must not become a deletable item."""
    target = tmp_path / "library"
    target.mkdir()
    (target / "Good").mkdir()
    (target / "Broken").mkdir()
    temp_config.write_text(
        json.dumps({"target_path": str(target), "groups": []}),
        encoding="utf-8",
    )

    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        if self.name == "Broken":
            raise OSError(5, "Input/output error", str(self))
        return real_is_dir(self)

    with patch.object(Path, "is_dir", fake_is_dir):
        response = client.get("/api/cleanup")

    assert response.status_code == 200
    names = [item["name"] for item in response.get_json()["items"]]
    assert names == ["Good"]


def test_unreadable_target_root_returns_an_empty_list(temp_config, client, tmp_path):
    """An unreadable target root yields no items instead of a 500.

    There is nothing to offer for deletion, and answering "no leftovers" is
    more useful to the cleanup dialog than an error page it would only render
    as a toast.
    """
    target = tmp_path / "library"
    target.mkdir()
    temp_config.write_text(
        json.dumps({"target_path": str(target), "groups": []}),
        encoding="utf-8",
    )

    with _deny(target):
        response = client.get("/api/cleanup")

    assert response.status_code == 200
    assert response.get_json()["items"] == []
