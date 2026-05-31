"""Skill model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="tool"
    )  # tool, function, webhook
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
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
    user = relationship("User", back_populates="skills")
    schedules = relationship(
        "SkillSchedule",
        back_populates="skill",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    workflow_steps = relationship("SkillWorkflowStep", back_populates="skill", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Skill(id={self.id}, name={self.name}, "
            f"enabled={self.enabled})>"
        )
