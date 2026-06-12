"""User model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="agent"
    )  # admin, agent, or custom roles
    skill_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    # null = unlimited, [] = no skills, [id1,id2] = only these
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    account_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active, suspended
    workspace_container_allowed: Mapped[bool | None] = mapped_column(
        default=None,
        nullable=True,
        comment="NULL=follow plan; True=allow container; False=deny container",
    )
    workspace_sidecar_memory: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="Override sidecar memory e.g. 512m, 2g"
    )
    workspace_sidecar_cpus: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="Override sidecar CPU quota e.g. 1.0"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    external_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    password_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When user chose their login password; null = OTP/SSO only",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ai_configs = relationship(
        "AIConfig", back_populates="user", lazy="selectin"
    )
    conversations = relationship(
        "Conversation", back_populates="user", lazy="selectin"
    )
    messages = relationship("Message", back_populates="user", lazy="selectin")
    skills = relationship("Skill", back_populates="user", lazy="selectin")
    knowledge_bases = relationship(
        "KnowledgeBase", back_populates="user", lazy="selectin"
    )
    owned_groups = relationship(
        "Group",
        foreign_keys="Group.owner_user_id",
        lazy="selectin",
    )
    group_memberships = relationship(
        "GroupMember",
        foreign_keys="GroupMember.user_id",
        lazy="selectin",
    )
    embedding_models = relationship(
        "EmbeddingModel", back_populates="user", lazy="selectin"
    )
    customer_configs = relationship(
        "CustomerConfig", back_populates="user", lazy="selectin"
    )
    webhook_configs = relationship(
        "WebhookConfig", back_populates="user", lazy="selectin"
    )
    channels = relationship(
        "Channel", back_populates="user", lazy="selectin"
    )
    skill_schedules = relationship(
        "SkillSchedule", back_populates="user", lazy="selectin"
    )
    skill_schedule_runs = relationship(
        "SkillScheduleRun", back_populates="user", lazy="selectin"
    )
    workflows = relationship("SkillWorkflow", back_populates="user", lazy="selectin")
    workflow_templates = relationship(
        "SkillWorkflowTemplate", back_populates="user", lazy="selectin"
    )
    workflow_runs = relationship(
        "SkillWorkflowRun", back_populates="user", lazy="selectin"
    )
    channel_workflow_bindings = relationship(
        "ChannelWorkflowBinding", back_populates="user", lazy="selectin"
    )
    workflow_approvals = relationship(
        "SkillWorkflowApproval",
        foreign_keys="SkillWorkflowApproval.user_id",
        back_populates="user",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
