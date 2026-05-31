"""Workflow orchestration models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SkillWorkflow(Base):
    __tablename__ = "skill_workflows"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    graph_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="workflows")
    steps = relationship(
        "SkillWorkflowStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    runs = relationship(
        "SkillWorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    schedules = relationship("SkillSchedule", back_populates="workflow", lazy="selectin")
    channel_bindings = relationship(
        "ChannelWorkflowBinding",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SkillWorkflowStep(Base):
    __tablename__ = "skill_workflow_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=False, index=True
    )
    step_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id"), nullable=False, index=True
    )
    payload_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    on_error: Mapped[str] = mapped_column(String(20), nullable=False, default="stop")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workflow = relationship("SkillWorkflow", back_populates="steps")
    skill = relationship("Skill", back_populates="workflow_steps")
    runs = relationship(
        "SkillWorkflowStepRun",
        back_populates="step",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SkillWorkflowRun(Base):
    __tablename__ = "skill_workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    workflow = relationship("SkillWorkflow", back_populates="runs")
    user = relationship("User", back_populates="workflow_runs")
    step_runs = relationship(
        "SkillWorkflowStepRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    approvals = relationship(
        "SkillWorkflowApproval",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SkillWorkflowStepRun(Base):
    __tablename__ = "skill_workflow_step_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflow_runs.id"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflow_steps.id"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    workflow_run = relationship("SkillWorkflowRun", back_populates="step_runs")
    step = relationship("SkillWorkflowStep", back_populates="runs")
    skill = relationship("Skill")


class ChannelWorkflowBinding(Base):
    __tablename__ = "channel_workflow_bindings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    match_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all"
    )  # all, contains, regex
    match_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="channel_workflow_bindings")
    channel = relationship("Channel", back_populates="workflow_bindings")
    workflow = relationship("SkillWorkflow", back_populates="channel_bindings")


class SkillWorkflowTemplate(Base):
    """User-saved workflow graph templates (reusable like built-in patent report templates)."""

    __tablename__ = "skill_workflow_templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="custom")
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    graph_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="workflow_templates")
    source_workflow = relationship("SkillWorkflow", foreign_keys=[source_workflow_id])


class SkillWorkflowApproval(Base):
    __tablename__ = "skill_workflow_approvals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflow_runs.id"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skill_workflows.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    node_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, approved, rejected
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    workflow_run = relationship("SkillWorkflowRun", back_populates="approvals")
    workflow = relationship("SkillWorkflow")
    user = relationship("User", foreign_keys=[user_id], back_populates="workflow_approvals")
    approver = relationship("User", foreign_keys=[approved_by])
