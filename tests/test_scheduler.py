import pytest
from unittest.mock import patch, MagicMock
from scheduler import (
    update_scheduler_jobs, 
    _run_global_sync_job, 
    _run_group_sync_job,
    start_scheduler,
    _scheduler
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
            "global_exclude_ids": ["Excluded"]
        },
        "groups": []
    }
    update_scheduler_jobs()
    # Check if add_job was called for global sync
    mock_sched.add_job.assert_called_once()
    args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "global_sync"
    assert kwargs["args"] == [["Excluded"]]

@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_groups(mock_load, mock_sched):
    mock_load.return_value = {
        "scheduler": {"global_enabled": False},
        "groups": [
            {
                "name": "MyGroup",
                "schedule_enabled": True,
                "schedule": "0 12 * * *"
            }
        ]
    }
    update_scheduler_jobs()
    mock_sched.add_job.assert_called_once()
    args, kwargs = mock_sched.add_job.call_args
    assert kwargs["id"] == "group_sync_MyGroup"
    assert kwargs["args"] == ["MyGroup"]

@patch('scheduler.run_sync')
@patch('scheduler.load_config')
def test_run_global_sync_job(mock_load, mock_sync):
    mock_load.return_value = {
        "groups": [
            {"name": "G1"},
            {"name": "Excluded"}
        ]
    }
    _run_global_sync_job(["Excluded"])
    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert kwargs["group_names"] == ["G1"]

@patch('scheduler.run_sync')
@patch('scheduler.load_config')
def test_run_group_sync_job(mock_load, mock_sync):
    _run_group_sync_job("G1")
    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert kwargs["group_names"] == ["G1"]

@patch('scheduler._scheduler')
def test_start_scheduler(mock_sched):
    mock_sched.running = False
    start_scheduler()
    mock_sched.start.assert_called_once()

@patch('scheduler._scheduler')
@patch('scheduler.load_config')
def test_update_scheduler_jobs_error(mock_load, mock_sched):
    mock_load.return_value = {
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "invalid_cron"
        },
        "groups": []
    }
    # Should log and continue, not raise
    update_scheduler_jobs()
    mock_sched.add_job.assert_not_called()
