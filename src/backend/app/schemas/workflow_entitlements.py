"""Workflow / schedule automation entitlements by subscription plan."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowEntitlementsResponse(BaseModel):
    plan: str = Field(description="Effective automation tier for this account")
    max_workflows: int | None = Field(
        description="Max workflows; null = unlimited"
    )
    max_schedules: int | None = None
    max_runs_month: int | None = None
    dag_enabled: bool = True
    channel_triggers_enabled: bool = True
    workflow_count: int = 0
    schedule_count: int = 0
    runs_month: int = 0
    can_create_workflow: bool = False
    can_create_schedule: bool = False
    can_run_workflow: bool = False
    upgrade_required: bool = False
    upgrade_template_id: str | None = None
    upgrade_channel_id: str | None = None
    plan_label: str = ""
