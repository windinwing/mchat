"""PublishRecord — durable log of every outbound publish attempt.

Unlike the workflow run JSON (which is large and hard to query), this table
stores one row per publish action for fast list/filter/stat queries. Written
by publish.service.dispatch after each attempt (success or failure).

The ``media_type`` / ``status`` fields anticipate video publishing: a review
flow can produce candidates (status=reviewed/rejected) before the final send
(status=sent).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    # Which publisher account was used (Channel id). Nullable for ad-hoc sends.
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # e.g. "feishu" / "playwright_client" (platform resolved by caller if needed)

    # Origin: which workflow run produced this send.
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Content snapshot (truncated for the list view).
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Outcome.
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Lifecycle: sent (direct) / reviewed (approved-then-sent) / rejected.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")
    # Content kind: text / image / video (video reserved for future).
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_publish_records_user_created", "user_id", "created_at"),
        Index("idx_publish_records_provider", "provider"),
    )
