"""AIConfig model - AI provider configuration."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # openai, anthropic, google
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    api_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2048
    )
    thinking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        server_default="1",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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
    user = relationship("User", back_populates="ai_configs")

    def __repr__(self) -> str:
        return (
            f"<AIConfig(id={self.id}, name={self.name}, "
            f"provider={self.provider}, model={self.model})>"
        )
