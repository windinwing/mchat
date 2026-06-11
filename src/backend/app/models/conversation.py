"""Conversation model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    ai_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_configs.id"), nullable=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("customer_configs.id"), nullable=True, index=True
    )
    visitor_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    client_ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active, closed
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal"
    )
    scope_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    contact_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        lazy="selectin",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation(id={self.id}, title={self.title}, "
            f"status={self.status})>"
        )
