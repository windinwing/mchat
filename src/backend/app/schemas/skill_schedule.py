"""Skill schedule schemas."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field, field_validator


class SkillScheduleBase(BaseModel):
    target_type: str = Field(default="skill")
    skill_id: str | None = Field(default=None, min_length=1, max_length=36)
    workflow_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(..., min_length=1, max_length=120)
    cron_expr: str = Field(..., min_length=9, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    payload: dict | None = None
    enabled: bool = True

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"skill", "workflow"}:
            raise ValueError("target_type must be skill or workflow")
        return val

    @field_validator("cron_expr")
    @classmethod
    def validate_cron_expr(cls, value: str) -> str:
        expr = value.strip()
        try:
            CronTrigger.from_crontab(expr)
        except ValueError as e:
            raise ValueError(
                "cron_expr must be standard 5-field crontab format"
            ) from e
        return expr

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        tz = value.strip()
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid timezone: {tz}") from e
        return tz


class SkillScheduleCreate(SkillScheduleBase):
    pass


class SkillScheduleUpdate(BaseModel):
    target_type: str | None = None
    skill_id: str | None = Field(default=None, min_length=1, max_length=36)
    workflow_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cron_expr: str | None = Field(default=None, min_length=9, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    payload: dict | None = None
    enabled: bool | None = None

    @field_validator("target_type")
    @classmethod
    def validate_optional_target_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        val = value.strip().lower()
        if val not in {"skill", "workflow"}:
            raise ValueError("target_type must be skill or workflow")
        return val

    @field_validator("cron_expr")
    @classmethod
    def validate_optional_cron_expr(cls, value: str | None) -> str | None:
        if value is None:
            return None
        expr = value.strip()
        try:
            CronTrigger.from_crontab(expr)
        except ValueError as e:
            raise ValueError(
                "cron_expr must be standard 5-field crontab format"
            ) from e
        return expr

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        tz = value.strip()
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid timezone: {tz}") from e
        return tz


class SkillScheduleRunOnceRequest(BaseModel):
    payload: dict | None = None


class SkillScheduleResponse(BaseModel):
    id: str
    target_type: str
    skill_id: str | None = None
    skill_name: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    target_name: str
    name: str
    cron_expr: str
    timezone: str
    payload: dict | None = None
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SkillScheduleRunResponse(BaseModel):
    id: str
    schedule_id: str | None = None
    target_type: str
    target_name: str | None = None
    skill_id: str | None = None
    skill_name: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    trigger_type: str
    status: str
    payload: dict | None = None
    result: dict | None = None
    error: str | None = None
    duration_ms: int | None = None
    started_at: datetime
    finished_at: datetime | None = None


class SkillScheduleRunResult(BaseModel):
    run: SkillScheduleRunResponse
