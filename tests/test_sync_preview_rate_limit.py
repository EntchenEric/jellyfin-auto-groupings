"""A preview must not consume the write sync's rate-limit budget.

``POST /api/sync/preview_all`` and ``POST /api/sync`` shared one per-IP
timestamp. The confirmation dialog offers exactly the sequence "Preview First"
followed by "Sync Now", so the preview stamped the IP, the sync that the user
had just confirmed arrived inside :data:`routes._SYNC_RATE_LIMIT_SECONDS`, and
the server answered 429 "Please wait before syncing again" — for the very
action the dialog had just been opened to perform. Nothing was written and
nothing explained why; the only fix available to the user was to click again
after a five-second wait.

A dry run is read-only, so the two kinds now keep separate budgets: repeated
previews are still throttled, and so are repeated syncs, but one does not
exhaust the other's window.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
from app import app as flask_app

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client():
    """Flask test client that sends the CSRF marker header."""
    flask_app.config.update(TESTING=False)
    test_client = flask_app.test_client()
    test_client.environ_base["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    return test_client


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """Start each test with an empty rate-limit map."""
    routes._last_sync_by_ip.clear()
    yield
    routes._last_sync_by_ip.clear()


def _post(client, path: str):
    """POST *path* with a stubbed config loader and no real sync work."""
    with (
        patch("routes.load_config", return_value={"groups": [], "scheduler": {}}),
        patch("routes.run_sync", return_value=[]),
    ):
        return client.post(path, headers=CSRF_HEADERS)


def test_preview_then_sync_is_not_rate_limited(client) -> None:
    """The dialog's "Preview First" -> "Sync Now" path must both succeed."""
    preview = _post(client, "/api/sync/preview_all")
    sync = _post(client, "/api/sync")

    assert preview.status_code == 200
    assert sync.status_code == 200, sync.get_json()
    assert sync.get_json()["status"] == "success"


def test_repeated_syncs_are_still_rate_limited(client) -> None:
    """Splitting the budget must not remove the write-path throttle."""
    first = _post(client, "/api/sync")
    second = _post(client, "/api/sync")

    assert first.status_code == 200
    assert second.status_code == 429


def test_repeated_previews_are_still_rate_limited(client) -> None:
    """Previews keep a throttle of their own."""
    first = _post(client, "/api/sync/preview_all")
    second = _post(client, "/api/sync/preview_all")

    assert first.status_code == 200
    assert second.status_code == 429


def test_sync_does_not_block_a_following_preview(client) -> None:
    """The budgets are independent in both directions."""
    sync = _post(client, "/api/sync")
    preview = _post(client, "/api/sync/preview_all")

    assert sync.status_code == 200
    assert preview.status_code == 200


def test_rate_limit_state_is_keyed_per_kind_and_ip(client) -> None:
    """Each (kind, ip) pair owns one entry, so pruning stays bounded."""
    _post(client, "/api/sync")
    _post(client, "/api/sync/preview_all")

    assert set(routes._last_sync_by_ip) == {
        ("sync", "127.0.0.1"),
        ("preview", "127.0.0.1"),
    }


def test_stale_preview_entries_are_pruned(client, monkeypatch) -> None:
    """A stale entry must not block a client that changes address."""
    routes._last_sync_by_ip[("preview", "10.0.0.9")] = 0.0
    monkeypatch.setattr(routes.time, "monotonic", lambda: 10_000.0)

    assert _post(client, "/api/sync").status_code == 200
    assert ("preview", "10.0.0.9") not in routes._last_sync_by_ip
