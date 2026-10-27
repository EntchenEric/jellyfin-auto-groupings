"""Behavioural tests for the scheduled job handlers in ``scheduler.py``.

The handlers run on an APScheduler worker thread with nobody watching, so an
exception that escapes one is not reported anywhere: the tick simply dies and
the next one runs on schedule. ``tests/test_sync_run_lock.py`` covers the
"another run holds the lock" skip; this module covers the surrounding contract
— what each handler is handed, what it forwards to ``run_sync``, and which
failures it must absorb rather than propagate.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import scheduler
import sync

# ---------------------------------------------------------------------------
# _run_global_sync_job — selecting the groups to sync
# ---------------------------------------------------------------------------


def test_global_sync_forwards_every_named_group(caplog):
    """The job syncs the configured groups by name, in config order."""
    config = {"groups": [{"name": "Action"}, {"name": "Comedy"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job([])

    run_sync.assert_called_once()
    assert run_sync.call_args.kwargs["group_names"] == ["Action", "Comedy"]
    assert any("Background global sync starting" in r.message for r in caplog.records)


def test_global_sync_skips_excluded_groups():
    """``global_exclude_ids`` is a name exclusion list; excluded groups are dropped."""
    config = {"groups": [{"name": "Action"}, {"name": "Comedy"}, {"name": "Drama"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job(["Comedy"])

    assert run_sync.call_args.kwargs["group_names"] == ["Action", "Drama"]


def test_global_sync_ignores_malformed_group_entries():
    """Non-object entries and non-string names never reach ``run_sync``.

    A hand-edited ``groups`` list can hold bare strings; every consumer treats
    a group as a dict, so the job filters instead of raising.
    """
    config = {
        "groups": [
            {"name": "Action"},
            "not-a-dict",
            {"name": 5},
            {"missing": "name"},
            {"name": "Comedy"},
        ],
    }
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job([])

    assert run_sync.call_args.kwargs["group_names"] == ["Action", "Comedy"]


def test_global_sync_skips_the_run_when_every_group_is_excluded(caplog):
    """Excluding everything must not call ``run_sync`` with an empty list."""
    config = {"groups": [{"name": "Action"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job(["Action"])

    run_sync.assert_not_called()
    assert any("no groups to sync" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad_groups", [None, 42, "abc", {}, True])
def test_global_sync_survives_malformed_groups_section(bad_groups):
    """``"groups": null`` used to raise ``TypeError`` outside the ``try``.

    ``config.json`` is user-editable, so ``groups`` can be any JSON value.
    The handler must log and return like it does for every other failure,
    because an escaping exception kills the tick silently.
    """
    with (
        patch.object(scheduler, "load_config", return_value={"groups": bad_groups}),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job([])  # must not raise

    run_sync.assert_not_called()


def test_global_sync_survives_malformed_exclude_list():
    """A non-list exclusion argument is ignored, not iterated."""
    config = {"groups": [{"name": "Action"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_global_sync_job(None)  # type: ignore[arg-type]

    assert run_sync.call_args.kwargs["group_names"] == ["Action"]


def test_global_sync_logs_and_swallows_unexpected_errors(caplog):
    """A fetcher blowing up must be logged, not raised into the scheduler."""
    config = {"groups": [{"name": "Action"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync", side_effect=RuntimeError("boom")),
    ):
        scheduler._run_global_sync_job([])  # must not raise

    assert any("Background global sync failed" in r.message for r in caplog.records)


def test_global_sync_survives_a_failing_config_load(caplog):
    """``load_config`` failing is itself just another job failure."""
    with patch.object(scheduler, "load_config", side_effect=OSError("unreadable")):
        scheduler._run_global_sync_job([])  # must not raise

    assert any("Background global sync failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _run_group_sync_job
# ---------------------------------------------------------------------------


def test_group_sync_syncs_only_the_requested_group():
    """A per-group job passes exactly one name, never the whole config."""
    config = {"groups": [{"name": "Action"}, {"name": "Comedy"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync") as run_sync,
    ):
        scheduler._run_group_sync_job("Comedy")

    run_sync.assert_called_once()
    assert run_sync.call_args.kwargs["group_names"] == ["Comedy"]


def test_group_sync_logs_and_swallows_unexpected_errors(caplog):
    config = {"groups": [{"name": "Action"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync", side_effect=RuntimeError("boom")),
    ):
        scheduler._run_group_sync_job("Action")  # must not raise

    assert any("Background sync failed for group" in r.message for r in caplog.records)


def test_group_sync_survives_a_failing_config_load(caplog):
    with patch.object(scheduler, "load_config", side_effect=OSError("unreadable")):
        scheduler._run_group_sync_job("Action")  # must not raise

    assert any("Background sync failed for group" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _run_cleanup_job
# ---------------------------------------------------------------------------


def test_cleanup_job_reports_the_deleted_count(caplog):
    """The count is the only evidence the job did anything, so it is logged."""
    with (
        patch.object(scheduler, "load_config", return_value={"target_path": "/tmp"}),
        patch.object(scheduler, "run_cleanup_broken_symlinks", return_value=7) as clean,
    ):
        scheduler._run_cleanup_job()

    clean.assert_called_once()
    assert any("deleted 7 broken symlink" in r.message for r in caplog.records)


def test_cleanup_job_logs_and_swallows_unexpected_errors(caplog):
    with (
        patch.object(scheduler, "load_config", return_value={"target_path": "/tmp"}),
        patch.object(
            scheduler,
            "run_cleanup_broken_symlinks",
            side_effect=OSError("permission denied"),
        ),
    ):
        scheduler._run_cleanup_job()  # must not raise

    assert any("Background cleanup job failed" in r.message for r in caplog.records)


def test_cleanup_job_survives_a_failing_config_load(caplog):
    with patch.object(scheduler, "load_config", side_effect=OSError("unreadable")):
        scheduler._run_cleanup_job()  # must not raise

    assert any("Background cleanup job failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _schedule_cleanup — the cleanup toggle and cron
# ---------------------------------------------------------------------------


def test_cleanup_is_scheduled_by_default():
    """``cleanup_enabled`` defaults to True; omitting the key must still schedule."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_cleanup(fresh, {})
    try:
        assert fresh.get_job("cleanup_sync") is not None
    finally:
        fresh.remove_all_jobs()


def test_cleanup_can_be_disabled():
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_cleanup(fresh, {"cleanup_enabled": False})
    try:
        assert fresh.get_job("cleanup_sync") is None
    finally:
        fresh.remove_all_jobs()


def test_cleanup_with_an_empty_schedule_is_not_registered():
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_cleanup(
        fresh,
        {"cleanup_enabled": True, "cleanup_schedule": ""},
    )
    try:
        assert fresh.get_job("cleanup_sync") is None
    finally:
        fresh.remove_all_jobs()


def test_cleanup_with_an_invalid_cron_is_logged_and_skipped(caplog):
    """A bad cron in config must not abort scheduling of the other jobs."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_cleanup(
        fresh,
        {"cleanup_enabled": True, "cleanup_schedule": "not a cron"},
    )
    try:
        assert fresh.get_job("cleanup_sync") is None
    finally:
        fresh.remove_all_jobs()
    assert any("Failed to schedule cleanup job" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _schedule_group_syncs — duplicate names and invalid crons
# ---------------------------------------------------------------------------


def test_duplicate_group_names_register_a_single_job(caplog):
    """Two entries with the same name would fight over one job id."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_group_syncs(
        fresh,
        [
            {"name": "Action", "schedule_enabled": True, "schedule": "0 1 * * *"},
            {"name": "Action", "schedule_enabled": True, "schedule": "0 2 * * *"},
        ],
    )
    try:
        ids = [job.id for job in fresh.get_jobs()]
        assert ids.count("group_sync_Action") == 1
    finally:
        fresh.remove_all_jobs()
    assert any("Duplicate group name" in r.message for r in caplog.records)


def test_group_names_are_stripped_before_use():
    """A name stored with padding must not produce a padded job id."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_group_syncs(
        fresh,
        [{"name": "  Action  ", "schedule_enabled": True, "schedule": "0 1 * * *"}],
    )
    try:
        assert fresh.get_job("group_sync_Action") is not None
    finally:
        fresh.remove_all_jobs()


@pytest.mark.parametrize("bad_name", ["", "   ", 5, None])
def test_invalid_group_names_are_not_scheduled(bad_name):
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_group_syncs(
        fresh,
        [{"name": bad_name, "schedule_enabled": True, "schedule": "0 1 * * *"}],
    )
    try:
        assert fresh.get_jobs() == []
    finally:
        fresh.remove_all_jobs()


def test_invalid_group_cron_is_logged_and_skipped(caplog):
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_group_syncs(
        fresh,
        [{"name": "Action", "schedule_enabled": True, "schedule": "bogus"}],
    )
    try:
        assert fresh.get_jobs() == []
    finally:
        fresh.remove_all_jobs()
    assert any("Failed to schedule sync for group" in r.message for r in caplog.records)


def test_disabled_group_is_not_scheduled():
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_group_syncs(
        fresh,
        [{"name": "Action", "schedule_enabled": False, "schedule": "0 1 * * *"}],
    )
    try:
        assert fresh.get_jobs() == []
    finally:
        fresh.remove_all_jobs()


# ---------------------------------------------------------------------------
# start_scheduler / validate_cron
# ---------------------------------------------------------------------------


def test_start_scheduler_reloads_jobs_when_already_running():
    """A second call must refresh jobs rather than call ``start()`` again."""

    class _Running:
        running = True

        def __init__(self) -> None:
            self.start_calls = 0

        def start(self) -> None:
            self.start_calls += 1

    fake = _Running()
    with (
        patch.object(scheduler, "_scheduler", fake),
        patch.object(scheduler, "update_scheduler_jobs") as update,
    ):
        scheduler.start_scheduler()

    assert fake.start_calls == 0
    update.assert_called_once()


def test_start_scheduler_starts_a_stopped_scheduler():
    class _Stopped:
        running = False

        def __init__(self) -> None:
            self.start_calls = 0

        def start(self) -> None:
            self.start_calls += 1

    fake = _Stopped()
    with (
        patch.object(scheduler, "_scheduler", fake),
        patch.object(scheduler, "update_scheduler_jobs") as update,
    ):
        scheduler.start_scheduler()

    assert fake.start_calls == 1
    update.assert_called_once()


@pytest.mark.parametrize(
    ("expr", "ok"),
    [
        ("0 * * * *", True),
        ("*/5 2 * * 1-5", True),
        (" 0 0 * * * ", True),
        ("61 * * * *", False),
        ("0 0 * *", False),
        ("not a cron", False),
        ("", False),
        ("   ", False),
    ],
)
def test_validate_cron_accepts_only_real_expressions(expr: str, ok: bool) -> None:
    assert (scheduler.validate_cron(expr) is None) is ok


@pytest.mark.parametrize("bad", [None, 5, [], {}, True])
def test_validate_cron_reports_non_strings_without_raising(bad) -> None:
    """The value comes straight from ``config.json``, so any JSON type is possible."""
    message = scheduler.validate_cron(bad)
    assert message is not None
    assert "must be a string" in message


def test_validate_cron_message_names_the_field_count():
    """The count is the actionable part: five fields, not four."""
    message = scheduler.validate_cron("0 0 * *")
    assert message is not None
    assert "4" in message


# ---------------------------------------------------------------------------
# Busy ticks are skips, not failures
# ---------------------------------------------------------------------------


def test_busy_skip_is_narrower_than_the_generic_handler():
    """``SyncBusyError`` is a normal skip and must not log a traceback.

    If the generic ``except Exception`` ran first, every busy tick would be
    logged as a full traceback and would read like a failure in the logs.
    """
    config = {"groups": [{"name": "Action"}]}
    with (
        patch.object(scheduler, "load_config", return_value=config),
        patch.object(scheduler, "run_sync", side_effect=sync.SyncBusyError("busy")),
        patch.object(scheduler.logger, "exception") as exception_log,
    ):
        scheduler._run_global_sync_job([])

    exception_log.assert_not_called()


# ---------------------------------------------------------------------------
# _schedule_global_sync — the guard clauses
# ---------------------------------------------------------------------------


def test_global_sync_is_not_scheduled_when_disabled():
    """``global_enabled`` off is the normal state; no job may be registered."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_global_sync(
        fresh,
        {"global_enabled": False, "global_schedule": "0 0 * * *"},
    )
    try:
        assert fresh.get_job("global_sync") is None
    finally:
        fresh.remove_all_jobs()


def test_global_sync_is_not_scheduled_without_a_schedule():
    """Enabling the toggle but leaving the cron empty must not register a job.

    An empty cron would otherwise reach ``CronTrigger.from_crontab`` and log a
    traceback on every config save.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_global_sync(
        fresh,
        {"global_enabled": True, "global_schedule": ""},
    )
    try:
        assert fresh.get_job("global_sync") is None
    finally:
        fresh.remove_all_jobs()


def test_global_sync_is_scheduled_with_its_exclusions():
    """The exclusion list is baked into the job args at scheduling time."""
    from apscheduler.schedulers.background import BackgroundScheduler

    fresh = BackgroundScheduler()
    scheduler._schedule_global_sync(
        fresh,
        {
            "global_enabled": True,
            "global_schedule": "0 3 * * *",
            "global_exclude_ids": ["Comedy"],
        },
    )
    try:
        job = fresh.get_job("global_sync")
        assert job is not None
        assert job.args[0] == ["Comedy"]
    finally:
        fresh.remove_all_jobs()
