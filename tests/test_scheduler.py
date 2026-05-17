from unittest.mock import patch

from scheduler import (
    _run_cleanup_job,
    _run_global_sync_job,
    _run_group_sync_job,
    start_scheduler,
    update_scheduler_jobs,
    validate_cron,
)


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_clear(mock_load, mock_sched):
    mock_load.return_value = {"scheduler": {}, "groups": []}
    update_scheduler_jobs()
    mock_sched.remove_all_jobs.assert_called_once()


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_global(mock_load, mock_sched):
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


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_groups(mock_load, mock_sched):
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


@patch('scheduler.run_sync')
@patch('scheduler.load_config')
def test_run_global_sync_job(mock_load, mock_sync):
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


@patch('scheduler.run_sync')
@patch('scheduler.load_config')
def test_run_group_sync_job(mock_load, mock_sync):
    _run_group_sync_job("G1")
    mock_sync.assert_called_once()
    _args, kwargs = mock_sync.call_args
    assert kwargs["group_names"] == ["G1"]


@patch('scheduler.load_config')
@patch('scheduler._scheduler')
def test_start_scheduler(mock_sched, mock_load):
    mock_load.return_value = {}
    mock_sched.running = False
    start_scheduler()
    mock_sched.start.assert_called_once()


@patch('scheduler.CronTrigger.from_crontab')
@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_error(mock_load, mock_sched, mock_cron):
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


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_cleanup(mock_load, mock_sched):
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


def test_validate_cron_valid():
    assert validate_cron("0 0 * * *") is None
    assert validate_cron("*/5 * * * *") is None
    assert validate_cron("30 14 1 1 0") is None


def test_validate_cron_empty():
    assert validate_cron("") is not None
    assert validate_cron("   ") is not None


def test_validate_cron_wrong_field_count():
    err = validate_cron("* * * * * *")
    assert err is not None
    assert "5 fields" in err
    err = validate_cron("* * * *")
    assert err is not None
    assert "5 fields" in err


def test_validate_cron_invalid_values():
    err = validate_cron("60 0 * * *")
    assert err is not None
    err = validate_cron("not a cron expr")
    assert err is not None


# ---------------------------------------------------------------------------
# scheduler.py edge cases
# ---------------------------------------------------------------------------


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_non_dict_group(mock_load, mock_sched):
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": ["not_a_dict"],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_group_no_name(mock_load, mock_sched):
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [{"schedule_enabled": True, "schedule": "0 12 * * *"}],
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch('scheduler.CronTrigger.from_crontab')
@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_group_error(mock_load, mock_sched, mock_cron):
    mock_load.return_value = {
        "scheduler": {"global_enabled": False, "cleanup_enabled": False},
        "groups": [{"name": "BadGroup", "schedule_enabled": True, "schedule": "bad"}],
    }
    mock_cron.side_effect = ValueError("Invalid cron")
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()


@patch('scheduler.run_sync')
@patch('scheduler.load_config')
def test_run_global_sync_job_all_excluded(mock_load, mock_sync):
    mock_load.return_value = {
        "groups": [
            {"name": "G1"},
            {"name": "G2"},
        ],
    }
    _run_global_sync_job(["G1", "G2"])
    mock_sync.assert_not_called()


@patch('scheduler.run_cleanup_broken_symlinks')
@patch('scheduler.load_config')
def test_run_cleanup_job(mock_load, mock_cleanup):
    mock_load.return_value = {"target_path": "/tmp"}
    mock_cleanup.return_value = 5
    _run_cleanup_job()
    mock_cleanup.assert_called_once()
