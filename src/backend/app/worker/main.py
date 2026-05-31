"""Independent scheduler worker process (default disabled)."""

from __future__ import annotations

import argparse
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.skill_schedule import SkillSchedule
from app.services.skill_schedule_service import SkillScheduleService
from app.services.settings_service import SettingsService
from app.worker.jobs import cleanup_old_logs, reset_monthly_usage_quotas
from app.worker.skill_scheduler import SkillScheduleRuntime


def _build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.worker_timezone)

    if settings.worker_usage_reset_enabled:
        scheduler.add_job(
            reset_monthly_usage_quotas,
            CronTrigger(day=1, hour=0, minute=5),
            id="reset_monthly_usage_quotas",
            max_instances=1,
            replace_existing=True,
            coalesce=True,
        )

    if settings.worker_log_cleanup_enabled:
        scheduler.add_job(
            cleanup_old_logs,
            CronTrigger(hour=3, minute=10),
            id="cleanup_old_logs",
            args=[settings.worker_log_retention_days],
            max_instances=1,
            replace_existing=True,
            coalesce=True,
        )

    return scheduler


async def _run_enabled_skill_schedules_once() -> int:
    count = 0
    async with async_session_factory() as db:
        result = await db.execute(
            select(SkillSchedule).where(SkillSchedule.enabled.is_(True))
        )
        schedules = result.scalars().all()
        service = SkillScheduleService(db)
        for schedule in schedules:
            try:
                await service.execute_schedule(
                    schedule=schedule,
                    trigger_type="worker_once",
                )
                count += 1
            except Exception as e:
                logger.warning("Worker run-once schedule {} failed: {}", schedule.id, e)
        await db.commit()
    return count


async def run_worker(*, run_once: bool = False) -> None:
    """Run worker with scheduled jobs, or execute enabled jobs once."""
    # Sync worker settings from DB (if available), with .env as fallback.
    try:
        async with async_session_factory() as db:
            await SettingsService(db).get_settings()
            await db.commit()
    except Exception as e:
        logger.warning("Worker could not load settings from DB, fallback to .env: {}", e)

    if not settings.worker_enabled:
        logger.info("Worker disabled (WORKER_ENABLED=false), exiting")
        return

    enabled_jobs: list[str] = []
    if settings.worker_usage_reset_enabled:
        enabled_jobs.append("reset_monthly_usage_quotas")
    if settings.worker_log_cleanup_enabled:
        enabled_jobs.append("cleanup_old_logs")

    if not enabled_jobs:
        logger.info("Worker running with dynamic skill schedules only")

    if run_once:
        logger.info("Worker run-once start: {}", ", ".join(enabled_jobs))
        if settings.worker_usage_reset_enabled:
            await reset_monthly_usage_quotas()
        if settings.worker_log_cleanup_enabled:
            await cleanup_old_logs(settings.worker_log_retention_days)
        schedule_count = await _run_enabled_skill_schedules_once()
        logger.info("Worker run-once executed {} skill schedules", schedule_count)
        logger.info("Worker run-once complete")
        return

    scheduler = _build_scheduler()
    schedule_runtime = SkillScheduleRuntime(scheduler)
    scheduler.add_job(
        schedule_runtime.sync_from_db,
        trigger=IntervalTrigger(seconds=30),
        id="sync_skill_schedules",
        max_instances=1,
        replace_existing=True,
        coalesce=True,
    )
    scheduler.start()
    await schedule_runtime.sync_from_db()
    logger.info(
        "Worker started (timezone={}, jobs={})",
        settings.worker_timezone,
        ", ".join(enabled_jobs + ["sync_skill_schedules", "skill_schedule:*"]),
    )
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Worker stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mchat background worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run enabled jobs once then exit",
    )
    args = parser.parse_args()
    asyncio.run(run_worker(run_once=args.once))


if __name__ == "__main__":
    main()

