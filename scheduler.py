"""scheduler.py - Background scheduling for Jellyfin Groupings.

Manages a BackgroundScheduler that triggers library synchronisation according
to either a global schedule (with exclusions) or per-group schedules.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from apscheduler.schedulers.background import (
    BackgroundScheduler,  # type: ignore[import-untyped]
)
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from config import load_config
from sync import run_cleanup_broken_symlinks, run_sync

# Initialize the scheduler
_scheduler = BackgroundScheduler()
sync_lock = threading.Lock()
logger = logging.getLogger(__name__)

__all__ = [
    "start_scheduler",
    "update_scheduler_jobs",
    "validate_cron",
]


def start_scheduler() -> None:
    """Start the background scheduler and load jobs from config."""
    if not _scheduler.running:
        _scheduler.start()
        logger.info("Background scheduler started")
    update_scheduler_jobs()


def _schedule_global_sync(
    scheduler: BackgroundScheduler,
    sched_cfg: dict[str, Any],
) -> None:
    """Add the global sync job if enabled."""
    if not sched_cfg.get("global_enabled"):
        return
    cron_expr = sched_cfg.get("global_schedule")
    if not cron_expr:
        return
    try:
        excluded_names = sched_cfg.get("global_exclude_ids", [])
        scheduler.add_job(
            _run_global_sync_job,
            CronTrigger.from_crontab(cron_expr),
            id="global_sync",
            name="Global Sync (with exclusions)",
            args=[excluded_names],
        )
        logger.info(
            "Scheduled global sync: %s (excluding: %s)",
            cron_expr,
            excluded_names,
        )
    except ValueError:
        logger.exception("Failed to schedule global sync (invalid cron: %s)", cron_expr)


def _schedule_group_syncs(scheduler: BackgroundScheduler, groups: list[Any]) -> None:
    """Add per-group sync jobs for groups that have scheduling enabled."""
    seen_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_name = group.get("name")
        if not group_name:
            continue
        if not isinstance(group_name, str):
            continue
        if group.get("schedule_enabled") and group.get("schedule"):
            cron_expr = group["schedule"]
            job_id = f"group_sync_{group_name}"
            if job_id in seen_ids:
                logger.warning(
                    "Duplicate group name %r — only one schedule job will run",
                    group_name,
                )
                continue
            seen_ids.add(job_id)
            try:
                scheduler.add_job(
                    _run_group_sync_job,
                    CronTrigger.from_crontab(cron_expr),
                    id=job_id,
                    name=f"Sync Group: {group_name}",
                    args=[group_name],
                    replace_existing=False,
                )
                logger.info("Scheduled sync for group '%s': %s", group_name, cron_expr)
            except ValueError:
                logger.exception(
                    "Failed to schedule sync for group '%s' (invalid cron: %s)",
                    group_name,
                    cron_expr,
                )


def _schedule_cleanup(
    scheduler: BackgroundScheduler,
    sched_cfg: dict[str, Any],
) -> None:
    """Add the broken-symlink cleanup job if enabled."""
    if not sched_cfg.get("cleanup_enabled", True):
        return
    cleanup_cron = sched_cfg.get("cleanup_schedule", "0 * * * *")
    if not cleanup_cron:
        return
    try:
        scheduler.add_job(
            _run_cleanup_job,
            CronTrigger.from_crontab(cleanup_cron),
            id="cleanup_sync",
            name="Cleanup Broken Symlinks",
        )
        logger.info("Scheduled cleanup job: %s", cleanup_cron)
    except ValueError:
        logger.exception(
            "Failed to schedule cleanup job (invalid cron: %s)",
            cleanup_cron,
        )


def update_scheduler_jobs() -> None:
    """Synchronise the scheduled jobs with the current configuration."""
    _scheduler.remove_all_jobs()

    config = load_config()
    sched_cfg = config.get("scheduler", {})
    groups = config.get("groups", [])

    _schedule_global_sync(_scheduler, sched_cfg)
    _schedule_group_syncs(_scheduler, groups)
    _schedule_cleanup(_scheduler, sched_cfg)


def _run_global_sync_job(exclude_names: list[str]) -> None:
    """Job handler for global sync."""
    config = load_config()
    all_groups = config.get("groups", [])

    # Filter out excluded groups
    sync_names: list[str] = []
    for g in all_groups:
        if isinstance(g, dict):
            name = g.get("name")
            if isinstance(name, str) and name not in exclude_names:
                sync_names.append(name)

    if sync_names:
        logger.info("Background global sync starting for groups: %s", sync_names)
        with sync_lock:
            try:
                run_sync(config, group_names=sync_names)
            except (ValueError, OSError, RuntimeError) as exc:
                logger.error(
                    "Background global sync failed: %s",
                    exc,
                    exc_info=True,
                )
    else:
        logger.info(
            "Background global sync skipped: no groups to sync after exclusions",
        )


def _run_group_sync_job(group_name: str) -> None:
    """Job handler for a single group sync."""
    config = load_config()
    logger.info("Background sync starting for group: %s", group_name)
    with sync_lock:
        try:
            run_sync(config, group_names=[group_name])
        except (ValueError, OSError, RuntimeError) as exc:
            logger.error(
                "Background sync failed for group '%s': %s",
                group_name,
                exc,
                exc_info=True,
            )


def _run_cleanup_job() -> None:
    """Job handler for cleaning up broken symlinks."""
    config = load_config()
    logger.info("Background cleanup job starting")
    with sync_lock:
        deleted = run_cleanup_broken_symlinks(config)
        logger.info(
            "Background cleanup job finished: deleted %s broken symlinks",
            deleted,
        )


def validate_cron(expr: str) -> str | None:
    """Validate a cron expression.

    Args:
        expr: A 5-field cron expression (e.g. ``"0 0 * * *"``).

    Returns:
        ``None`` if valid, otherwise an error message string.

    Examples:
        >>> validate_cron("0 0 * * *")
        >>> validate_cron("")  # doctest: +SKIP
        'Cron expression must not be empty'

    """
    if not expr or not expr.strip():
        return "Cron expression must not be empty"

    expr = expr.strip()
    fields = expr.split()
    if len(fields) != 5:
        return f"Cron expression must have 5 fields (minute hour day month weekday), got {len(fields)}"

    try:
        CronTrigger.from_crontab(expr)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Invalid cron expression: {exc}"
    return None


def _validate_data_key(config: dict[str, Any], key: str, expected_type: type) -> bool:
    """Validate that *key* in *config* is of *expected_type*.

    Returns ``True`` if the key is missing (no error), ``False`` if present
    but wrong type.
    """
    if key not in config:
        return True
    return isinstance(config[key], expected_type)
