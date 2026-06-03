"""Skill schedule service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.skill import Skill
from app.models.skill_schedule import SkillSchedule, SkillScheduleRun
from app.models.workflow import SkillWorkflow
from app.schemas.skill_schedule import (
    SkillScheduleCreate,
    SkillScheduleResponse,
    SkillScheduleRunResponse,
    SkillScheduleUpdate,
)
from app.skill.executor import execute_skill
from app.workspace.context import workspace_execution_scope
from app.workspace.resolver import build_workspace_context
from app.services.workflow_service import WorkflowService


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _as_result_dict(result: Any) -> dict:
    if isinstance(result, dict):
        return result
    if isinstance(result, (str, int, float, bool, list)):
        return {"value": result}
    return {"value": str(result)}


class SkillScheduleService:
    """Business logic for skill schedule CRUD and execution."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_skill_for_user(self, *, skill_id: str, user_id: str) -> Skill:
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Skill not found",
            )
        return skill

    async def _get_schedule_for_user(
        self, *, schedule_id: str, user_id: str
    ) -> SkillSchedule:
        result = await self.db.execute(
            select(SkillSchedule)
            .options(
                selectinload(SkillSchedule.skill),
                selectinload(SkillSchedule.workflow),
            )
            .where(SkillSchedule.id == schedule_id, SkillSchedule.user_id == user_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found",
            )
        return schedule

    async def _get_workflow_for_user(
        self, *, workflow_id: str, user_id: str
    ) -> SkillWorkflow:
        result = await self.db.execute(
            select(SkillWorkflow).where(
                SkillWorkflow.id == workflow_id, SkillWorkflow.user_id == user_id
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )
        return workflow

    @staticmethod
    def _to_schedule_response(schedule: SkillSchedule) -> SkillScheduleResponse:
        skill_name = schedule.skill.name if schedule.skill else None
        workflow_name = schedule.workflow.name if schedule.workflow else None
        target_name = skill_name or workflow_name or ""
        return SkillScheduleResponse(
            id=schedule.id,
            target_type=schedule.target_type,
            skill_id=schedule.skill_id,
            skill_name=skill_name,
            workflow_id=schedule.workflow_id,
            workflow_name=workflow_name,
            target_name=target_name,
            name=schedule.name,
            cron_expr=schedule.cron_expr,
            timezone=schedule.timezone,
            payload=schedule.payload,
            enabled=schedule.enabled,
            last_run_at=schedule.last_run_at,
            next_run_at=schedule.next_run_at,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )

    @staticmethod
    def _to_run_response(run: SkillScheduleRun) -> SkillScheduleRunResponse:
        skill_name = run.skill.name if run.skill else None
        workflow_name = run.workflow.name if run.workflow else None
        return SkillScheduleRunResponse(
            id=run.id,
            schedule_id=run.schedule_id,
            target_type=run.target_type,
            target_name=run.target_name,
            skill_id=run.skill_id,
            skill_name=skill_name,
            workflow_id=run.workflow_id,
            workflow_name=workflow_name,
            trigger_type=run.trigger_type,
            status=run.status,
            payload=run.payload,
            result=run.result,
            error=run.error,
            duration_ms=run.duration_ms,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    async def list_schedules(self, *, user_id: str) -> list[SkillScheduleResponse]:
        result = await self.db.execute(
            select(SkillSchedule)
            .options(
                selectinload(SkillSchedule.skill),
                selectinload(SkillSchedule.workflow),
            )
            .where(SkillSchedule.user_id == user_id)
            .order_by(SkillSchedule.created_at.desc())
        )
        schedules = result.scalars().all()
        return [self._to_schedule_response(s) for s in schedules]

    async def create_schedule(
        self, *, user_id: str, data: SkillScheduleCreate
    ) -> SkillScheduleResponse:
        target_type = data.target_type
        skill_id: str | None = None
        workflow_id: str | None = None
        if target_type == "skill":
            if not data.skill_id:
                raise HTTPException(status_code=400, detail="skill_id is required")
            skill = await self._get_skill_for_user(skill_id=data.skill_id, user_id=user_id)
            skill_id = skill.id
        else:
            if not data.workflow_id:
                raise HTTPException(status_code=400, detail="workflow_id is required")
            workflow = await self._get_workflow_for_user(
                workflow_id=data.workflow_id, user_id=user_id
            )
            workflow_id = workflow.id
        schedule = SkillSchedule(
            user_id=user_id,
            target_type=target_type,
            skill_id=skill_id,
            workflow_id=workflow_id,
            name=data.name.strip(),
            cron_expr=data.cron_expr.strip(),
            timezone=data.timezone.strip(),
            payload=data.payload,
            enabled=data.enabled,
        )
        self.db.add(schedule)
        await self.db.flush()
        schedule = await self._get_schedule_for_user(
            schedule_id=schedule.id, user_id=user_id
        )
        return self._to_schedule_response(schedule)

    async def update_schedule(
        self, *, schedule_id: str, user_id: str, data: SkillScheduleUpdate
    ) -> SkillScheduleResponse:
        schedule = await self._get_schedule_for_user(
            schedule_id=schedule_id, user_id=user_id
        )
        update_data = data.model_dump(exclude_unset=True)

        if "target_type" in update_data and update_data["target_type"] is not None:
            schedule.target_type = str(update_data["target_type"]).strip().lower()

        if "skill_id" in update_data and update_data["skill_id"] is not None:
            skill = await self._get_skill_for_user(
                skill_id=update_data["skill_id"], user_id=user_id
            )
            schedule.skill_id = skill.id
            schedule.target_type = "skill"
            schedule.workflow_id = None

        if "workflow_id" in update_data and update_data["workflow_id"] is not None:
            workflow = await self._get_workflow_for_user(
                workflow_id=update_data["workflow_id"], user_id=user_id
            )
            schedule.workflow_id = workflow.id
            schedule.target_type = "workflow"
            schedule.skill_id = None

        if "name" in update_data and update_data["name"] is not None:
            schedule.name = update_data["name"].strip()
        if "cron_expr" in update_data and update_data["cron_expr"] is not None:
            schedule.cron_expr = update_data["cron_expr"].strip()
        if "timezone" in update_data and update_data["timezone"] is not None:
            schedule.timezone = update_data["timezone"].strip()
        if "payload" in update_data:
            schedule.payload = update_data["payload"]
        if "enabled" in update_data and update_data["enabled"] is not None:
            schedule.enabled = bool(update_data["enabled"])

        if schedule.target_type == "skill" and not schedule.skill_id:
            raise HTTPException(status_code=400, detail="skill_id is required")
        if schedule.target_type == "workflow" and not schedule.workflow_id:
            raise HTTPException(status_code=400, detail="workflow_id is required")

        await self.db.flush()
        schedule = await self._get_schedule_for_user(
            schedule_id=schedule.id, user_id=user_id
        )
        return self._to_schedule_response(schedule)

    async def delete_schedule(self, *, schedule_id: str, user_id: str) -> None:
        schedule = await self._get_schedule_for_user(
            schedule_id=schedule_id, user_id=user_id
        )
        await self.db.delete(schedule)
        await self.db.flush()

    async def list_runs(
        self, *, user_id: str, schedule_id: str | None = None, limit: int = 30
    ) -> list[SkillScheduleRunResponse]:
        safe_limit = max(1, min(limit, 200))
        stmt = select(SkillScheduleRun).options(selectinload(SkillScheduleRun.skill)).where(
            SkillScheduleRun.user_id == user_id
        )
        stmt = stmt.options(selectinload(SkillScheduleRun.workflow))
        if schedule_id:
            stmt = stmt.where(SkillScheduleRun.schedule_id == schedule_id)
        stmt = stmt.order_by(SkillScheduleRun.started_at.desc()).limit(safe_limit)
        result = await self.db.execute(stmt)
        runs = result.scalars().all()
        return [self._to_run_response(r) for r in runs]

    async def run_once(
        self,
        *,
        schedule_id: str,
        user_id: str,
        payload_override: dict | None = None,
    ) -> SkillScheduleRunResponse:
        schedule = await self._get_schedule_for_user(
            schedule_id=schedule_id, user_id=user_id
        )
        run = await self.execute_schedule(
            schedule=schedule,
            trigger_type="manual",
            payload_override=payload_override,
        )
        return self._to_run_response(run)

    async def execute_schedule(
        self,
        *,
        schedule: SkillSchedule,
        trigger_type: str = "cron",
        payload_override: dict | None = None,
    ) -> SkillScheduleRun:
        payload = (
            payload_override if payload_override is not None else (schedule.payload or {})
        )
        if not isinstance(payload, dict):
            raise RuntimeError("schedule payload must be a JSON object")

        started_at = datetime.now(timezone.utc)
        run = SkillScheduleRun(
            schedule_id=schedule.id,
            user_id=schedule.user_id,
            target_type=schedule.target_type,
            skill_id=schedule.skill_id,
            workflow_id=schedule.workflow_id,
            trigger_type=trigger_type,
            status="running",
            payload=payload,
            started_at=started_at,
        )
        self.db.add(run)
        await self.db.flush()

        try:
            if schedule.target_type == "workflow":
                workflow = schedule.workflow
                if workflow is None and schedule.workflow_id:
                    wf_result = await self.db.execute(
                        select(SkillWorkflow).where(SkillWorkflow.id == schedule.workflow_id)
                    )
                    workflow = wf_result.scalar_one_or_none()
                if workflow is None:
                    raise RuntimeError(f"schedule {schedule.id} workflow not found")
                if not workflow.enabled:
                    raise RuntimeError(f"workflow '{workflow.name}' is disabled")
                run.target_name = workflow.name
                workflow_run = await WorkflowService(self.db).execute_workflow(
                    workflow=workflow,
                    trigger_type=trigger_type,
                    input_payload=payload,
                )
                run.status = "success" if workflow_run.status == "success" else "failed"
                run.result = workflow_run.output_payload
                run.error = workflow_run.error
            else:
                skill = schedule.skill
                if skill is None and schedule.skill_id:
                    skill_result = await self.db.execute(
                        select(Skill).where(Skill.id == schedule.skill_id)
                    )
                    skill = skill_result.scalar_one_or_none()
                if skill is None:
                    raise RuntimeError(f"schedule {schedule.id} skill not found")
                if not skill.enabled:
                    raise RuntimeError(f"skill '{skill.name}' is disabled")
                run.target_name = skill.name
                async with workspace_execution_scope(
                    build_workspace_context(schedule.user_id)
                ):
                    raw_result = await execute_skill(skill, payload)
                result_dict = _as_result_dict(raw_result)
                has_error = bool(
                    isinstance(raw_result, dict) and raw_result.get("error")
                )
                run.status = "failed" if has_error else "success"
                run.result = None if has_error else result_dict
                run.error = str(result_dict.get("error")) if has_error else None

            finished_at = datetime.now(timezone.utc)
            run.finished_at = finished_at
            run.duration_ms = _duration_ms(started_at, finished_at)
            schedule.last_run_at = finished_at
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.error = str(e)
            run.finished_at = finished_at
            run.duration_ms = _duration_ms(started_at, finished_at)
            schedule.last_run_at = finished_at

        await self.db.flush()
        run_result = await self.db.execute(
            select(SkillScheduleRun)
            .options(
                selectinload(SkillScheduleRun.skill),
                selectinload(SkillScheduleRun.workflow),
            )
            .where(SkillScheduleRun.id == run.id)
        )
        loaded_run = run_result.scalar_one()
        return loaded_run

    async def execute_schedule_by_id(self, *, schedule_id: str) -> SkillScheduleRun:
        result = await self.db.execute(
            select(SkillSchedule)
            .options(
                selectinload(SkillSchedule.skill),
                selectinload(SkillSchedule.workflow),
            )
            .where(SkillSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise RuntimeError(f"schedule {schedule_id} not found")
        if not schedule.enabled:
            raise RuntimeError(f"schedule {schedule_id} is disabled")
        return await self.execute_schedule(schedule=schedule, trigger_type="cron")

