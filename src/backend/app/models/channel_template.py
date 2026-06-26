"""Channel template model for vertical RAG packages."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChannelTemplate(Base):
    __tablename__ = "channel_templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="customer_service", index=True
    )
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)

    price_monthly_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    price_yearly_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)

    # Publishing add-on: max outbound publisher accounts (xiaohongshu/feishu/...)
    # this plan grants. 0 = not a publishing plan (no publishing access).
    max_publishing_accounts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    default_ai_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_configs.id"), nullable=True
    )
    default_ai_config_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_skill_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    default_knowledge_base_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    default_knowledge_base_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_theme: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_offline_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    integration_schema: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # [{"skill":"earth2037","fields":[{"key":"game_api_key","label":"游戏 API Key","secret":true}]}]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer_configs = relationship(
        "CustomerConfig", back_populates="template"
    )

    def __repr__(self) -> str:
        return (
            f"<ChannelTemplate(id={self.id}, name={self.name}, "
            f"category={self.category})>"
        )
