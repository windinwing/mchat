"""Dynamic skill schedule registration for APScheduler worker."""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.skill_schedule import SkillSchedule
from app.services.skill_schedule_service import SkillScheduleService

SCHEDULE_JOB_PREFIX = "skill_schedule:"


class SkillScheduleRuntime:
    """Keep APScheduler jobs in sync with DB skill schedules."""

    def __init__(self, scheduler: AsyncIOScheduler) -> None:
        self.scheduler = scheduler

    async def sync_from_db(self) -> None:
        """Sync enabled schedule rows to APScheduler jobs."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(SkillSchedule).order_by(SkillSchedule.created_at.desc())
            )
            schedules = result.scalars().all()

            enabled_ids: set[str] = set()
            next_run_updates: dict[str, datetime | None] = {}

            for schedule in schedules:
                if not schedule.enabled:
                    next_run_updates[schedule.id] = None
                    continue

                job_id = self._job_id(schedule.id)
                signature = self._signature(
                    schedule.cron_expr,
                    schedule.timezone,
                    schedule.target_type,
                    schedule.skill_id,
                    schedule.workflow_id,
                )
                enabled_ids.add(schedule.id)

                existing = self.scheduler.get_job(job_id)
                if existing and existing.kwargs.get("signature") == signature:
                    next_run_updates[schedule.id] = existing.next_run_time
                    continue

                if existing:
                    self.scheduler.remove_job(job_id)

                try:
                    trigger = CronTrigger.from_crontab(
                        schedule.cron_expr,
                        timezone=schedule.timezone,
                    )
                    job = self.scheduler.add_job(
                        self._execute_schedule_job,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"schedule_id": schedule.id, "signature": signature},
                        max_instances=1,
                        coalesce=True,
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                    next_run_updates[schedule.id] = job.next_run_time
                except Exception as e:
                    next_run_updates[schedule.id] = None
                    logger.warning(
                        "Skip invalid skill schedule {} (cron='{}', tz='{}'): {}",
                        schedule.id,
                        schedule.cron_expr,
                        schedule.timezone,
                        e,
                    )

            for job in self.scheduler.get_jobs():
                if not job.id.startswith(SCHEDULE_JOB_PREFIX):
                    continue
                schedule_id = job.id[len(SCHEDULE_JOB_PREFIX) :]
                if schedule_id not in enabled_ids:
                    self.scheduler.remove_job(job.id)

            for schedule in schedules:
                schedule.next_run_at = next_run_updates.get(schedule.id)
            await db.commit()
            logger.info(
                "Skill schedule sync complete: {} active",
                len(enabled_ids),
            )

    async def _execute_schedule_job(self, *, schedule_id: str, signature: str) -> None:
        """Execute schedule by id and store run logs."""
        _ = signature
        async with async_session_factory() as db:
            service = SkillScheduleService(db)
            try:
                run = await service.execute_schedule_by_id(schedule_id=schedule_id)
                await db.commit()
                logger.info(
                    "Skill schedule {} executed: status={} duration={}ms",
                    schedule_id,
                    run.status,
                    run.duration_ms or 0,
                )
            except Exception as e:
                await db.rollback()
                logger.warning("Skill schedule {} failed: {}", schedule_id, e)

    @staticmethod
    def _job_id(schedule_id: str) -> str:
        return f"{SCHEDULE_JOB_PREFIX}{schedule_id}"

    @staticmethod
    def _signature(
        cron_expr: str,
        timezone_name: str,
        target_type: str,
        skill_id: str | None,
        workflow_id: str | None,
    ) -> str:
        return (
            f"{cron_expr.strip()}|{timezone_name.strip()}|{target_type}|"
            f"{skill_id or ''}|{workflow_id or ''}"
        )
