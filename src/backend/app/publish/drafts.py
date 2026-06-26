"""Content draft / review system — generate candidates, user picks, then send.

Lightweight approach using publish_records with status=pending:
  1. Workflow generates content → writes a publish_record with status=pending
     (NOT sent yet)
  2. User/admin reviews pending drafts → approve (sends for real) or reject
  3. publish_record transitions: pending → sent (approved) or rejected

This avoids a new table — drafts are just publish_records that haven't been
sent yet. The publish-content skill can write a draft instead of sending when
payload has ``draft: true``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.publish_record import PublishRecord
from app.models.user import User
from app.publish.service import dispatch

router = APIRouter()


@router.get("/drafts")
async def list_drafts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending content drafts awaiting review (user's own + admin sees all)."""
    q = select(PublishRecord).where(PublishRecord.status == "pending")
    if current_user.role not in ("admin", "agent"):
        q = q.where(PublishRecord.user_id == current_user.id)
    q = q.order_by(PublishRecord.created_at.desc())
    result = await db.execute(q)
    return [_draft_to_dict(r) for r in result.scalars().all()]


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending draft — sends it for real via dispatch."""
    draft = await _get_draft(draft_id, current_user, db)
    if draft.status != "pending":
        raise HTTPException(400, detail=f"草稿状态为 {draft.status}，无法审批")

    # Actually send it now
    result = await dispatch({
        "provider": draft.provider,
        "channel_id": draft.channel_id,
        "title": draft.title,
        "content": draft.content_preview or "",  # full content stored in preview for drafts
    })

    # Update the record
    draft.status = "sent" if result.success else "failed"
    draft.success = result.success
    draft.remote_url = result.remote_url
    draft.remote_id = result.remote_id
    draft.error_message = result.error_message
    draft.error_code = result.error_code
    draft.sent_at = datetime.now(timezone.utc) if result.success else None
    await db.commit()
    return {"ok": True, "success": result.success, "message": result.message}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending draft — marks it as rejected (never sent)."""
    draft = await _get_draft(draft_id, current_user, db)
    if draft.status != "pending":
        raise HTTPException(400, detail=f"草稿状态为 {draft.status}，无法拒绝")
    draft.status = "rejected"
    await db.commit()
    return {"ok": True}


@router.post("/drafts")
async def create_draft(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a content draft (for testing or manual content entry)."""
    draft = PublishRecord(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        channel_id=body.get("channel_id"),
        provider=body.get("provider", "feishu"),
        title=body.get("title", "")[:200] or None,
        content_preview=(body.get("content") or "")[:200] or None,
        success=False,
        status="pending",
        media_type=body.get("media_type", "text"),
    )
    db.add(draft)
    await db.commit()
    return {"ok": True, "id": draft.id}


async def _get_draft(draft_id: str, user: User, db: AsyncSession) -> PublishRecord:
    result = await db.execute(
        select(PublishRecord).where(PublishRecord.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(404, detail="草稿不存在")
    if user.role not in ("admin", "agent") and draft.user_id != user.id:
        raise HTTPException(403, detail="无权操作")
    return draft


def _draft_to_dict(r: PublishRecord) -> dict:
    return {
        "id": r.id,
        "provider": r.provider,
        "channel_id": r.channel_id,
        "title": r.title,
        "content_preview": r.content_preview,
        "status": r.status,
        "media_type": r.media_type,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
