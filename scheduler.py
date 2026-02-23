"""
scheduler.py – Background scheduling for Jellyfin Groupings.

Manages a BackgroundScheduler that triggers library synchronisation according
to either a global schedule (with exclusions) or per-group schedules.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import load_config
from sync import run_sync

# Initialize the scheduler
_scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)

def start_scheduler() -> None:
    """Start the background scheduler and load jobs from config."""
    if not _scheduler.running:
        _scheduler.start()
        logger.info("Background scheduler started")
    update_scheduler_jobs()

def update_scheduler_jobs() -> None:
    """Synchronise the scheduled jobs with the current configuration."""
    # Clear existing jobs
    for job in _scheduler.get_jobs():
        _scheduler.remove_job(job.id)

    config = load_config()
    sched_cfg = config.get("scheduler", {})
    groups = config.get("groups", [])

    # 1. Global Scheduler
    if sched_cfg.get("global_enabled"):
        cron_expr = sched_cfg.get("global_schedule")
        if cron_expr:
            try:
                excluded_names = sched_cfg.get("global_exclude_ids", []) # We use names as IDs for now
                _scheduler.add_job(
                    _run_global_sync_job,
                    CronTrigger.from_crontab(cron_expr),
                    id="global_sync",
                    name="Global Sync (with exclusions)",
                    args=[excluded_names]
                )
                logger.info(f"Scheduled global sync: {cron_expr} (excluding: {excluded_names})")
            except Exception as e:
                logger.error(f"Failed to schedule global sync: {e}")

    # 2. Per-group Schedulers
    for group in groups:
        if not isinstance(group, dict):
            continue
            
        group_name = group.get("name")
        if not group_name:
            continue
            
        if group.get("schedule_enabled") and group.get("schedule"):
            cron_expr = group["schedule"]
            try:
                _scheduler.add_job(
                    _run_group_sync_job,
                    CronTrigger.from_crontab(cron_expr),
                    id=f"group_sync_{group_name}",
                    name=f"Sync Group: {group_name}",
                    args=[group_name]
                )
                logger.info(f"Scheduled sync for group '{group_name}': {cron_expr}")
            except Exception as e:
                logger.error(f"Failed to schedule sync for group '{group_name}': {e}")

def _run_global_sync_job(exclude_names: list[str]) -> None:
    """Job handler for global sync."""
    config = load_config()
    all_groups = config.get("groups", [])
    
    # Filter out excluded groups
    sync_names = [
        g.get("name") for g in all_groups 
        if isinstance(g, dict) and g.get("name") and g.get("name") not in exclude_names
    ]
    
    if sync_names:
        logger.info(f"Background global sync starting for groups: {sync_names}")
        run_sync(config, group_names=sync_names)
    else:
        logger.info("Background global sync skipped: no groups to sync after exclusions")

def _run_group_sync_job(group_name: str) -> None:
    """Job handler for a single group sync."""
    config = load_config()
    logger.info(f"Background sync starting for group: {group_name}")
    run_sync(config, group_names=[group_name])
