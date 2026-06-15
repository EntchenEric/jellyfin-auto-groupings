"""Tests for scheduler.py — job scheduling, cron validation, and lifecycle.

Verifies that the APScheduler integration correctly schedules, updates,
and runs global sync, per-group sync, and cleanup jobs, including
edge cases like invalid cron expressions and scheduler stop/start.
"""

from unittest.mock import patch

import pytest

from scheduler import (
    _run_cleanup_job,
    _run_global_sync_job,
    _run_group_sync_job,
    _validate_group_entry,
    start_scheduler,
    update_scheduler_jobs,
    validate_cron,
)


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_clear(mock_load, mock_sched) -> None:
    mock_load.return_value = {"scheduler": {}, "groups": []}
    update_scheduler_jobs()
    mock_sched.remove_all_jobs.assert_called_once()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_global(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "0 0 * * *",
            "global_exclude_ids": ["Excluded"],
            "cleanup_enabled": False,
        },
        "groups": [],
    }
    update_scheduler_jobs()
    # Check if add_job was called for global sync
    mock_sched.add_job.assert_called_once()
    _args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "global_sync"
    assert kwargs["args"] == [["Excluded"]]


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_global_empty_schedule(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "",
            "cleanup_enabled": False,
        },
        "groups": [],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_cleanup_empty_schedule(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {
            "global_enabled": False,
            "cleanup_enabled": True,
            "cleanup_schedule": "",
        },
        "groups": [],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_groups(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [
            {
                "name": "MyGroup",
                "schedule_enabled": True,
                "schedule": "0 12 * * *",
            },
        ],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_called_once()
    _args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "group_sync_MyGroup"
    assert kwargs["args"] == ["MyGroup"]


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_global_sync_job(mock_load, mock_sync) -> None:
    mock_load.return_value = {
        "groups": [
            {"name": "G1"},
            {"name": "Excluded"},
        ],
    }
    _run_global_sync_job(["Excluded"])
    mock_sync.assert_called_once()
    _args, kwargs = mock_sync.call_args
    assert kwargs["group_names"] == ["G1"]


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_group_sync_job(mock_load, mock_sync) -> None:
    _run_group_sync_job("G1")
    mock_sync.assert_called_once()
    _args, kwargs = mock_sync.call_args
    assert kwargs["group_names"] == ["G1"]


@patch("scheduler.load_config")
@patch("scheduler._scheduler")
def test_start_scheduler(mock_sched, mock_load) -> None:
    mock_load.return_value = {}
    mock_sched.running = False
    start_scheduler()
    mock_sched.start.assert_called_once()


@patch("scheduler.load_config")
@patch("scheduler._scheduler")
def test_start_scheduler_already_running(mock_sched, mock_load) -> None:
    """Scheduler already running — should not call start() again."""
    mock_load.return_value = {}
    mock_sched.running = True
    start_scheduler()
    mock_sched.start.assert_not_called()


@patch("scheduler.CronTrigger.from_crontab")
@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_error(mock_load, mock_sched, mock_cron) -> None:
    mock_load.return_value = {
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "invalid_cron",
        },
        "groups": [],
    }
    mock_cron.side_effect = ValueError("Invalid cron")
    # Should log and continue, not raise
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_cleanup(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {
            "cleanup_enabled": True,
            "cleanup_schedule": "0 * * * *",
        },
        "groups": [],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_called_once()
    _args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "cleanup_sync"


# ---------------------------------------------------------------------------
# validate_cron tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected_error"),
    [
        ("0 0 * * *", None),
        ("*/5 * * * *", None),
        ("30 14 1 1 0", None),
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("* * * * * *", "5 fields"),
        ("* * * *", "5 fields"),
        ("60 0 * * *", "Invalid cron"),
        ("not a cron expr", "5 fields"),
    ],
)
def test_validate_cron(expr, expected_error) -> None:
    result = validate_cron(expr)
    if expected_error is None:
        assert result is None
    else:
        assert result is not None
        assert expected_error in result


# ---------------------------------------------------------------------------
# scheduler.py edge cases
# ---------------------------------------------------------------------------


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_non_dict_group(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": ["not_a_dict"],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_group_no_name(mock_load, mock_sched) -> None:
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [{"schedule_enabled": True, "schedule": "0 12 * * *"}],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler.CronTrigger.from_crontab")
@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_group_error(mock_load, mock_sched, mock_cron) -> None:
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [{"name": "BadGroup", "schedule_enabled": True, "schedule": "bad"}],
    }
    mock_cron.side_effect = ValueError("Invalid cron")
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_global_sync_job_all_excluded(mock_load, mock_sync) -> None:
    mock_load.return_value = {
        "groups": [
            {"name": "G1"},
            {"name": "G2"},
        ],
    }
    _run_global_sync_job(["G1", "G2"])
    mock_sync.assert_not_called()


@patch("scheduler.run_cleanup_broken_symlinks")
@patch("scheduler.load_config")
def test_run_cleanup_job(mock_load, mock_cleanup) -> None:
    mock_load.return_value = {"target_path": "/tmp"}
    mock_cleanup.return_value = 5
    _run_cleanup_job()
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# _run_global_sync_job error resilience
# ---------------------------------------------------------------------------


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_global_sync_job_error(mock_load, mock_sync) -> None:
    """_run_global_sync_job catches and logs sync exceptions."""
    mock_load.return_value = {
        "groups": [
            {"name": "G1"},
        ],
    }
    mock_sync.side_effect = RuntimeError("sync failure")
    # Should not raise
    _run_global_sync_job([])
    mock_sync.assert_called_once()


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_global_sync_job_empty_groups(mock_load, mock_sync) -> None:
    """_run_global_sync_job handles empty groups list."""
    mock_load.return_value = {
        "groups": [],
    }
    _run_global_sync_job([])
    mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# _run_group_sync_job error resilience
# ---------------------------------------------------------------------------


@patch("scheduler.run_sync")
@patch("scheduler.load_config")
def test_run_group_sync_job_error(mock_load, mock_sync) -> None:
    """_run_group_sync_job catches and logs sync exceptions."""
    mock_sync.side_effect = ValueError("bad config")
    _run_group_sync_job("G1")
    mock_sync.assert_called_once()


# ---------------------------------------------------------------------------
# Additional edge cases: non-string group name, duplicate names
# ---------------------------------------------------------------------------


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_group_non_str_name(mock_load, mock_sched) -> None:
    """Non-string group names are skipped."""
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [{"name": 42, "schedule_enabled": True, "schedule": "0 12 * * *"}],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch("scheduler._scheduler")
@patch("scheduler.load_config")
def test_update_scheduler_jobs_duplicate_group_names(mock_load, mock_sched) -> None:
    """Duplicate group names log a warning and only register one job."""
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [
            {"name": "SameName", "schedule_enabled": True, "schedule": "0 12 * * *"},
            {"name": "SameName", "schedule_enabled": True, "schedule": "0 6 * * *"},
        ],
    }
    update_scheduler_jobs()
    assert mock_sched.add_job.call_count == 1
    _args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "group_sync_SameName"


# ---------------------------------------------------------------------------
# _validate_group_entry tests
# ---------------------------------------------------------------------------


def test_validate_group_entry_valid() -> None:
    """Valid group dict returns its name."""
    result = _validate_group_entry({"name": "MyGroup"})
    assert result == "MyGroup"


def test_validate_group_entry_not_dict() -> None:
    """Non-dict entries return None."""
    assert _validate_group_entry("not_a_dict") is None
    assert _validate_group_entry(42) is None
    assert _validate_group_entry(None) is None


def test_validate_group_entry_missing_name() -> None:
    """Dict without a name key returns None."""
    assert _validate_group_entry({"schedule_enabled": True}) is None


def test_validate_group_entry_non_string_name() -> None:
    """Non-string name values return None."""
    assert _validate_group_entry({"name": 42}) is None
    assert _validate_group_entry({"name": []}) is None
    assert _validate_group_entry({"name": None}) is None


def test_validate_group_entry_whitespace_only_name() -> None:
    """Whitespace-only group names return None (stripped to empty)."""
    assert _validate_group_entry({"name": "   "}) is None
    assert _validate_group_entry({"name": "\t\n"}) is None


def test_validate_group_entry_strips_whitespace() -> None:
    """Group names with surrounding whitespace are stripped."""
    result = _validate_group_entry({"name": "  MyGroup  "})
    assert result == "MyGroup"


def test_validate_group_entry_empty_string_name() -> None:
    """Empty string name returns None."""
    assert _validate_group_entry({"name": ""}) is None
