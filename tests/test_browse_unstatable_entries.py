"""One unstatable entry must not blank the whole folder-browser listing.

``GET /api/browse`` powers the folder picker. It built its result in a single
comprehension::

    sorted(
        entry.name
        for entry in Path(path).iterdir()
        if not entry.name.startswith(".")
        and entry.is_dir()
        and not entry.is_symlink()
    )

``Path.is_dir()`` follows a ``stat`` and *raises* ``OSError`` for an entry it
cannot classify — a dangling symlink, a symlink loop, a permission error, a
stale handle on a dropped mount. The comprehension aborts on the first such
entry, so the sibling directories the user can perfectly well browse are lost
too. The handler only catches ``PermissionError`` (-> empty list) and other
``OSError`` (-> HTTP 400), so one odd entry in a directory makes the picker
error out or claim the folder is empty.

A real directory is allowed to contain a broken entry; the picker should show
what it can and skip what it cannot.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
from app import app as flask_app


@pytest.fixture
def client():
    """Flask test client for the API blueprint."""
    flask_app.config.update(TESTING=False)
    return flask_app.test_client()


@pytest.fixture
def browse_root(tmp_path, monkeypatch):
    """Make *tmp_path* a whitelisted browse root for the duration of a test."""
    monkeypatch.setattr(routes, "_BROWSE_ROOTS", (str(tmp_path),))
    return tmp_path


def _fail_stat_for(name: str, exc: OSError):
    """Patch ``Path.is_dir`` to raise for entries whose name is *name*.

    ``os.chmod`` cannot reproduce this portably: the suite may run as root (in
    a container, or the Docker image), where an unreadable mode bit is not
    enforced. Patching the single path keeps the reproduction independent of
    the user and of the filesystem in use.
    """
    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        if self.name == name:
            raise exc
        return real_is_dir(self)

    return patch.object(Path, "is_dir", fake_is_dir)


def test_unstatable_entry_keeps_readable_siblings(client, browse_root):
    """A broken entry is skipped; readable subdirectories are still listed."""
    (browse_root / "Alpha").mkdir()
    (browse_root / "Broken").mkdir()
    (browse_root / "Zeta").mkdir()

    with _fail_stat_for("Broken", OSError(5, "Input/output error", "Broken")):
        response = client.get("/api/browse", query_string={"path": str(browse_root)})

    assert response.status_code == 200
    assert response.get_json()["dirs"] == ["Alpha", "Zeta"]


def test_dangling_symlink_does_not_blank_the_listing(client, browse_root):
    """A real dangling symlink must neither break nor appear in the listing.

    ``Path.is_dir()`` already swallows ``ENOENT``/``ELOOP``, so this pins the
    existing behaviour: a fix for the raising cases must not start offering
    dangling links as browsable directories.
    """
    (browse_root / "Alpha").mkdir()
    (browse_root / "Zeta").mkdir()
    (browse_root / "Gone").symlink_to(browse_root / "does-not-exist")

    response = client.get("/api/browse", query_string={"path": str(browse_root)})

    assert response.status_code == 200
    assert response.get_json()["dirs"] == ["Alpha", "Zeta"]


def test_unreadable_root_still_returns_an_empty_listing(client, browse_root):
    """An unreadable directory lists nothing rather than erroring the picker."""
    real_iterdir = Path.iterdir

    def fake_iterdir(self):
        if self == browse_root:
            raise PermissionError(13, "Permission denied", str(self))
        return real_iterdir(self)

    with patch.object(Path, "iterdir", fake_iterdir):
        response = client.get("/api/browse", query_string={"path": str(browse_root)})

    assert response.status_code == 200
    assert response.get_json()["dirs"] == []
