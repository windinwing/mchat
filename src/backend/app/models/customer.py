"""Customer config and webhook config models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CustomerConfig(Base):
    __tablename__ = "customer_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    ai_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_configs.id"), nullable=True
    )
    ai_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # True = use this channel's ai_config_id instead of only template default
    skill_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # enabled skill ids for this agent; null/[] = none selected
    knowledge_base_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # knowledge bases for RAG; null/[] = none selected
    auto_reply_rules: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # semantic/keyword rules that auto-send files, links, or videos
    channel_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # per-channel system instructions (skills, routing); not shown to visitors
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    offline_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    domains: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # comma-separated allowed domains
    position: Mapped[str] = mapped_column(
        String(20), nullable=False, default="right"
    )  # left, right
    pre_chat_fields: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # [{key, label, required?, type?}] shown before first message
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    widget_session_ttl_hours: Mapped[int] = mapped_column(
        nullable=False, default=24
    )

    # Channel rental / vertical RAG fields
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free"
    )  # free, free_trial, pro, enterprise
    workspace_mode: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # null = auto from plan; local | container
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active_order_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    skill_bindings: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # per-channel secrets for skills, e.g. {"earth2037": {"secrets": {"game_api_key": "..."}}}
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channel_templates.id"), nullable=True, index=True
    )
    channel_category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="customer_service"
    )  # customer_service, patent_rag, medical_rag, etc.

    # Usage tracking
    usage_messages_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    usage_tokens_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    usage_documents_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    usage_storage_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    usage_messages_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
    )
    usage_tokens_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100000
    )
    last_usage_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
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
    user = relationship("User", back_populates="customer_configs")
    template = relationship("ChannelTemplate", back_populates="customer_configs")

    def __repr__(self) -> str:
        return f"<CustomerConfig(id={self.id}, name={self.name})>"


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # comma-separated event names
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
    user = relationship("User", back_populates="webhook_configs")

    def __repr__(self) -> str:
        return f"<WebhookConfig(id={self.id}, name={self.name})>"
