"""Skill schedule models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SkillSchedule(Base):
    __tablename__ = "skill_schedules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    skill_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skills.id"), nullable=True, index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="skill"
    )  # skill, workflow
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="skill_schedules")
    skill = relationship("Skill", back_populates="schedules")
    workflow = relationship("SkillWorkflow", back_populates="schedules")
    runs = relationship(
        "SkillScheduleRun",
        back_populates="schedule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SkillScheduleRun(Base):
    __tablename__ = "skill_schedule_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schedule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skill_schedules.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    skill_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skills.id"), nullable=True, index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="skill"
    )  # skill, workflow
    target_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="cron")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    schedule = relationship("SkillSchedule", back_populates="runs")
    user = relationship("User", back_populates="skill_schedule_runs")
    skill = relationship("Skill")
    workflow = relationship("SkillWorkflow")
