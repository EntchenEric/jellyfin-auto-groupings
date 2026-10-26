"""Concurrent sync runs must not clear each other's group directories.

Each group directory is wiped and refilled one symlink at a time:

* :func:`sync._prepare_group_directory` deletes the links the group owns.
* :func:`sync._create_group_symlinks` then creates the new ones in a loop.

Nothing serialised two runs, so a scheduled sync overlapping a ``POST
/api/sync`` from the UI left the directory holding an arbitrary mix of both.
The reproduced shape: run A creates 50 links, run B clears the directory
part-way through and creates its own 50, and the directory ends with 41 of A's
links and all 50 of B's — 91 entries for a group whose rule resolved 50 items.

``scheduler.sync_lock`` did not help. It is a ``threading.Lock`` held only by
the three scheduler job handlers, so the HTTP route never took it, and with
gunicorn's multiple workers (the Dockerfile default is 2) each process had its
own copy anyway.

``sync.sync_run_guard`` closes both gaps: an in-process ``threading.Lock`` for
threads of one worker plus an exclusive ``flock`` on ``<config dir>/sync.lock``
for separate workers. These tests pin that the lock is actually exclusive, that
it is released on every exit path, and that a conflicting run is reported as a
409 rather than silently starting.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sync
from app import app as flask_app


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    """Point the run lock at a writable per-test directory."""
    monkeypatch.setattr(sync, "CONFIG_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------


def test_guard_blocks_a_second_acquire(lock_dir) -> None:
    """A second run must fail while the first holds the lock."""
    with (
        sync.sync_run_guard(),
        pytest.raises(sync.SyncBusyError),
        sync.sync_run_guard(timeout=0.1),
    ):
        pytest.fail("the guard allowed two overlapping runs")


def test_guard_is_reusable_after_release(lock_dir) -> None:
    """Releasing the lock must let the next run proceed."""
    with sync.sync_run_guard():
        pass
    with sync.sync_run_guard(timeout=0.1):
        pass


def test_guard_releases_on_exception(lock_dir) -> None:
    """A crashing run must not leave the lock held forever."""
    with pytest.raises(RuntimeError), sync.sync_run_guard():
        msg = "boom"
        raise RuntimeError(msg)

    with sync.sync_run_guard(timeout=0.1):
        pass


def test_guard_is_exclusive_across_processes(lock_dir) -> None:
    """A run in another process must block, not just another thread.

    This is the case the old ``threading.Lock`` could not cover: the Docker
    image runs gunicorn with several workers, each with its own
    ``sync_lock``, and a handheld ``python3 sync.py`` would not share it
    either.
    """
    holder = f"""
import sys, time
sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
import sync
sync.CONFIG_DIR = {str(lock_dir)!r}
with sync.sync_run_guard():
    print("held", flush=True)
    time.sleep(10)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", holder],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "held"
        with (
            pytest.raises(sync.SyncBusyError),
            sync.sync_run_guard(timeout=0.2),
        ):
            pytest.fail("another process held the lock but the run started")
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_guard_creates_its_lock_file(lock_dir) -> None:
    """The lock file is created in the config directory, not the target."""
    with sync.sync_run_guard():
        assert (lock_dir / "sync.lock").exists()


def test_guard_survives_an_unwritable_lock_location(monkeypatch) -> None:
    """A read-only config directory must not make syncing impossible.

    The in-process lock is still held, so the run is serialised against other
    threads; only the cross-process guarantee is lost, which the warning says.
    """
    monkeypatch.setattr(sync, "CONFIG_DIR", "/proc/definitely-not-writable")

    with sync.sync_run_guard():
        pass


def test_guard_timeout_zero_fails_immediately(lock_dir) -> None:
    """``timeout=0`` reports the conflict without waiting."""
    with sync.sync_run_guard():
        started = time.monotonic()
        with pytest.raises(sync.SyncBusyError), sync.sync_run_guard(timeout=0):
            pytest.fail("timeout=0 still acquired the lock")
        assert time.monotonic() - started < 1.0


# ---------------------------------------------------------------------------
# run_sync / run_cleanup_broken_symlinks take the lock
# ---------------------------------------------------------------------------


def _minimal_config(tmp_path: Path) -> dict:
    return {
        "jellyfin_url": "http://127.0.0.1:1",
        "api_key": "key",
        "target_path": str(tmp_path / "target"),
        "groups": [],
    }


def test_run_sync_takes_the_lock(tmp_path, lock_dir) -> None:
    """A real sync must not start while another run holds the lock."""
    with sync.sync_run_guard(), pytest.raises(sync.SyncBusyError):
        sync.run_sync(_minimal_config(tmp_path))


def test_dry_run_does_not_need_the_lock(tmp_path, lock_dir) -> None:
    """A preview writes nothing, so it stays usable during a sync."""
    with sync.sync_run_guard():
        assert sync.run_sync(_minimal_config(tmp_path), dry_run=True) == []


def test_cleanup_takes_the_lock(tmp_path, lock_dir) -> None:
    """Cleanup deletes from the directories a sync refills, so it locks too."""
    target = tmp_path / "target"
    target.mkdir()
    with sync.sync_run_guard(), pytest.raises(sync.SyncBusyError):
        sync.run_cleanup_broken_symlinks({"target_path": str(target)})


# ---------------------------------------------------------------------------
# HTTP behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Flask test client that sends the CSRF marker header."""
    flask_app.config.update(TESTING=False)
    test_client = flask_app.test_client()
    test_client.environ_base["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    return test_client


def test_sync_route_returns_409_when_busy(client, lock_dir) -> None:
    """A busy server reports the conflict instead of a generic failure."""
    with sync.sync_run_guard():
        response = client.post("/api/sync")

    assert response.status_code == 409
    body = response.get_json()
    assert body["status"] == "error"
    assert "already" in body["message"].lower()


def test_sync_route_starts_after_the_lock_is_released(client, lock_dir) -> None:
    """A finished run must not leave the route permanently reporting 409."""
    with sync.sync_run_guard():
        pass
    with patch("routes.load_config", return_value=_minimal_config(Path("/tmp"))):
        response = client.post("/api/sync")
    assert response.status_code != 409


def test_cleanup_route_returns_409_when_busy(client, lock_dir, tmp_path) -> None:
    """Deleting a folder a sync is refilling is refused, not raced."""
    target = tmp_path / "target"
    target.mkdir()
    config = {"target_path": str(target), "groups": []}
    with sync.sync_run_guard(), patch("routes.load_config", return_value=config):
        response = client.post("/api/cleanup", json={"folders": ["Action"]})

    assert response.status_code == 409


def test_cleanup_route_still_deletes_when_idle(client, lock_dir, tmp_path) -> None:
    """The lock must not break the ordinary cleanup path."""
    target = tmp_path / "target"
    stale = target / "Leftover"
    stale.mkdir(parents=True)
    config = {"target_path": str(target), "groups": []}
    with patch("routes.load_config", return_value=config):
        response = client.post("/api/cleanup", json={"folders": ["Leftover"]})

    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1
    assert not stale.exists()


# ---------------------------------------------------------------------------
# Scheduler jobs skip rather than queue behind a long run
# ---------------------------------------------------------------------------


def test_scheduler_job_skips_when_busy(caplog) -> None:
    """A scheduled tick during a run logs a skip and returns."""
    import scheduler

    config = {
        "groups": [
            {"name": "Action", "schedule_enabled": True, "schedule": "* * * * *"}
        ],
    }
    with (
        patch("scheduler.load_config", return_value=config),
        patch("scheduler.run_sync", side_effect=sync.SyncBusyError("busy")),
    ):
        scheduler._run_group_sync_job("Action")

    assert any("skipped" in record.message.lower() for record in caplog.records)


def test_cleanup_job_skips_when_busy(caplog) -> None:
    """The scheduled cleanup must not fail loudly on a normal skip."""
    import scheduler

    with (
        patch("scheduler.load_config", return_value={"target_path": "/tmp"}),
        patch(
            "scheduler.run_cleanup_broken_symlinks",
            side_effect=sync.SyncBusyError("busy"),
        ),
    ):
        scheduler._run_cleanup_job()

    assert any("skipped" in record.message.lower() for record in caplog.records)
