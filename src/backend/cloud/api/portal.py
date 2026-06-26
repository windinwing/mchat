"""Portal API router — user-facing channel rental and management."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.chat import ConversationResponse
from app.services.maintenance_gate import ensure_public_api_available
from cloud.schemas.portal import (
    ChannelIntegrationsResponse,
    EmbedCodeResponse,
    MyChannelResponse,
    MyChannelUpdate,
    PortalAiConfigCreate,
    PortalAiConfigOption,
    PortalAiConfigUpdate,
    PortalDashboardStats,
    PortalInvoiceResponse,
    PortalOrderDetailResponse,
    PortalOrderResponse,
    RentChannelRequest,
    ResumeChannelChatRequest,
    StudioDailyMemoryResponse,
    StudioMemoryResponse,
    StudioMemoryUpdate,
)
from cloud.services.portal_chat_service import PortalChatService
from cloud.services.portal_payment_service import PortalPaymentService
from cloud.services.portal_service import PortalService
from cloud.services.studio_memory_service import StudioMemoryService
from app.schemas.workflow_entitlements import WorkflowEntitlementsResponse
from app.services.workflow_entitlements import get_workflow_entitlements

router = APIRouter()


def _block_portal_during_maintenance() -> None:
    ensure_public_api_available()


@router.get("/orders", response_model=list[PortalOrderResponse])
async def list_my_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PortalOrderResponse]:
    """List checkout / subscription orders for the current user."""
    return await PortalPaymentService(db).list_user_orders(current_user)


@router.get("/orders/{order_id}", response_model=PortalOrderDetailResponse)
async def get_my_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalOrderDetailResponse:
    """Order detail for portal UI."""
    return await PortalPaymentService(db).get_order_detail(current_user, order_id)


@router.get("/orders/{order_id}/invoice", response_model=PortalInvoiceResponse)
async def get_order_invoice(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalInvoiceResponse:
    """Invoice payload (client renders printable view)."""
    return await PortalPaymentService(db).get_order_invoice(current_user, order_id)


@router.get("/automation/entitlements", response_model=WorkflowEntitlementsResponse)
async def portal_automation_entitlements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowEntitlementsResponse:
    """Workflow / schedule limits for the current portal user."""
    return await get_workflow_entitlements(db, current_user)


@router.get("/dashboard", response_model=PortalDashboardStats)
async def portal_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalDashboardStats:
    """Get portal dashboard stats for the current user."""
    return await PortalService(db).get_dashboard_stats(current_user)


@router.get("/channels", response_model=list[MyChannelResponse])
async def list_my_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyChannelResponse]:
    """List channels owned by the current user."""
    return await PortalService(db).list_my_channels(current_user)


@router.post("/channels/rent", response_model=MyChannelResponse, status_code=status.HTTP_201_CREATED)
async def rent_channel(
    request: RentChannelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyChannelResponse:
    """Provision a new channel from a published template."""
    try:
        return await PortalService(db).rent_channel(current_user, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create channel: {e}",
        )


@router.get("/ai-configs", response_model=list[PortalAiConfigOption])
async def list_portal_ai_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PortalAiConfigOption]:
    """AI configs owned by the user (for per-channel override)."""
    return await PortalService(db).list_user_ai_configs(current_user)


@router.post("/ai-configs", response_model=PortalAiConfigOption, status_code=status.HTTP_201_CREATED)
async def create_portal_ai_config(
    body: PortalAiConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalAiConfigOption:
    """Create user-owned AI config (API key, model)."""
    return await PortalService(db).create_user_ai_config(current_user, body)


@router.put("/ai-configs/{config_id}", response_model=PortalAiConfigOption)
async def update_portal_ai_config(
    config_id: str,
    body: PortalAiConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalAiConfigOption:
    """Update user-owned AI config."""
    return await PortalService(db).update_user_ai_config(
        current_user, config_id, body
    )


@router.get(
    "/channels/{channel_id}/integrations",
    response_model=ChannelIntegrationsResponse,
)
async def get_channel_integrations(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelIntegrationsResponse:
    """Skills on this channel that support per-assistant API token overrides."""
    return await PortalService(db).get_channel_integrations(current_user, channel_id)


@router.get("/channels/{channel_id}", response_model=MyChannelResponse)
async def get_my_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyChannelResponse:
    """Get a specific channel owned by the user."""
    return await PortalService(db).get_my_channel(current_user, channel_id)


@router.put("/channels/{channel_id}", response_model=MyChannelResponse)
async def update_my_channel(
    channel_id: str,
    request: MyChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyChannelResponse:
    """Update channel settings (user-scoped)."""
    return await PortalService(db).update_my_channel(current_user, channel_id, request)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a channel owned by the user."""
    await PortalService(db).delete_my_channel(current_user, channel_id)


@router.get("/channels/{channel_id}/embed", response_model=EmbedCodeResponse)
async def get_embed_code(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmbedCodeResponse:
    """Get widget embed code for a channel."""
    return await PortalService(db).get_embed_code(current_user, channel_id)


@router.get("/channels/{channel_id}/knowledge-bases")
async def list_channel_knowledge_bases(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge bases bound to the user's channel."""
    return await PortalService(db).list_channel_knowledge_bases(
        current_user, channel_id
    )


@router.post("/channels/{channel_id}/knowledge-bases", status_code=status.HTTP_201_CREATED)
async def create_channel_knowledge_base(
    channel_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge base and attach it to the channel."""
    return await PortalService(db).create_channel_knowledge_base(
        current_user, channel_id, body
    )


@router.delete(
    "/channels/{channel_id}/knowledge-bases/{kb_id}",
    status_code=status.HTTP_200_OK,
)
async def remove_channel_knowledge_base(
    channel_id: str,
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove KB from channel; delete it only when user-owned."""
    return await PortalService(db).remove_channel_knowledge_base(
        current_user, channel_id, kb_id
    )


@router.post(
    "/channels/{channel_id}/knowledge-bases/{kb_id}/import-file",
    status_code=status.HTTP_201_CREATED,
)
async def import_channel_document(
    channel_id: str,
    kb_id: str,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document into a channel-bound knowledge base."""
    try:
        return await PortalService(db).import_channel_document(
            current_user, channel_id, kb_id, file
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed: {e}",
        ) from e


@router.post(
    "/channels/{channel_id}/chat/resume",
    response_model=ConversationResponse,
)
async def resume_channel_chat(
    channel_id: str,
    request: ResumeChannelChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Resume portal studio chat (persistent thread + Markdown memory)."""
    _block_portal_during_maintenance()
    await PortalService(db).get_my_channel(current_user, channel_id)
    return await PortalChatService(db).get_or_resume_channel_conversation(
        user_id=current_user.id,
        channel_id=channel_id,
        title=request.title,
        force_new=request.force_new,
    )


@router.get("/channels/{channel_id}/memory", response_model=StudioMemoryResponse)
async def get_channel_memory(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudioMemoryResponse:
    """Get MEMORY.md and recent daily log dates for a channel."""
    await PortalService(db).get_my_channel(current_user, channel_id)
    service = StudioMemoryService(current_user.id, channel_id)
    return StudioMemoryResponse(
        memory_md=service.read_memory_file(),
        daily_dates=service.list_daily_dates(),
    )


@router.put("/channels/{channel_id}/memory", response_model=StudioMemoryResponse)
async def update_channel_memory(
    channel_id: str,
    request: StudioMemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudioMemoryResponse:
    """Replace MEMORY.md for a channel."""
    await PortalService(db).get_my_channel(current_user, channel_id)
    service = StudioMemoryService(current_user.id, channel_id)
    service.write_memory_file(request.content, mode="replace")
    return StudioMemoryResponse(
        memory_md=service.read_memory_file(),
        daily_dates=service.list_daily_dates(),
    )


@router.get(
    "/channels/{channel_id}/memory/daily/{date_key}",
    response_model=StudioDailyMemoryResponse,
)
async def get_channel_daily_memory(
    channel_id: str,
    date_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudioDailyMemoryResponse:
    """Get a daily memory log file."""
    await PortalService(db).get_my_channel(current_user, channel_id)
    service = StudioMemoryService(current_user.id, channel_id)
    return StudioDailyMemoryResponse(
        date=date_key,
        content=service.read_daily_file(date_key),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Publishing accounts (portal)
# Publisher accounts are Channel rows whose channel_type is a publisher type.
# Portal users manage them through these dedicated endpoints (not /api/channels
# which needs CHANNELS_WRITE). A publishing-plan gate enforces the per-user
# account quota (e.g. 5 or 10).
# ─────────────────────────────────────────────────────────────────────────────

from app.publish.entitlements import (  # noqa: E402
    PUBLISHER_CHANNEL_TYPES,
    ensure_can_manage_publishing_accounts,
    ensure_within_publishing_quota,
    get_publishing_entitlement,
)
from app.schemas.channel import ChannelCreate  # noqa: E402
from app.services.channel_service import ChannelService  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402


@router.get("/publishing-accounts")
async def list_publishing_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's publisher accounts."""
    all_channels = await ChannelService(db).list_channels(current_user.id)
    return [c for c in all_channels if c.channel_type in PUBLISHER_CHANNEL_TYPES]


@router.get("/publishing-accounts/entitlement")
async def publishing_accounts_entitlement(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's publishing quota (max/current/remaining)."""
    ent = await get_publishing_entitlement(db, current_user.id)
    return {
        "allowed": ent.allowed,
        "max_accounts": ent.max_accounts,
        "current_count": ent.current_count,
        "remaining": ent.remaining,
    }


@router.post("/publishing-accounts", status_code=status.HTTP_201_CREATED)
async def create_publishing_account(
    body: ChannelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a publisher account (plan-gated + quota-checked). Only publisher
    channel_types are allowed."""
    ct = (body.channel_type or "").strip()
    if ct not in PUBLISHER_CHANNEL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持发布类账号，不支持 channel_type={ct}",
        )
    await ensure_within_publishing_quota(db, current_user.id)
    return await ChannelService(db).create_channel(current_user.id, body)


@router.put("/publishing-accounts/{account_id}")
async def update_publishing_account(
    account_id: str,
    body: ChannelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a publisher account (must belong to the current user)."""
    existing = await ChannelService(db).get_channel(account_id, current_user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if existing.channel_type not in PUBLISHER_CHANNEL_TYPES:
        raise HTTPException(status_code=400, detail="仅支持发布类账号")
    await ensure_can_manage_publishing_accounts(db, current_user.id)
    return await ChannelService(db).update_channel(account_id, current_user.id, body)


@router.delete("/publishing-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_publishing_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a publisher account."""
    existing = await ChannelService(db).get_channel(account_id, current_user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    await ChannelService(db).delete_channel(account_id, current_user.id)


# ─────────────────────────────────────────────────────────────────────────────
# Send records (publish history + stats)
# ─────────────────────────────────────────────────────────────────────────────

from sqlalchemy import func as sa_func  # noqa: E402
from app.models.publish_record import PublishRecord  # noqa: E402


@router.get("/send-records")
async def list_send_records(
    provider: str | None = None,
    success: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the user's publish send records (paginated, filterable)."""
    q = sa_select(PublishRecord).where(PublishRecord.user_id == current_user.id)
    if provider:
        q = q.where(PublishRecord.provider == provider)
    if success is not None:
        q = q.where(PublishRecord.success == success)
    q = q.order_by(PublishRecord.created_at.desc()).limit(min(limit, 200)).offset(offset)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "channel_id": r.channel_id,
            "title": r.title,
            "content_preview": r.content_preview,
            "success": r.success,
            "remote_url": r.remote_url,
            "error_message": r.error_message,
            "status": r.status,
            "media_type": r.media_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


@router.get("/send-records/stats")
async def send_records_stats(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats: total/success/failed + breakdown by provider."""
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(days=min(days, 90))
    base = sa_select(PublishRecord).where(
        PublishRecord.user_id == current_user.id,
        PublishRecord.created_at >= since,
    )
    total_r = await db.execute(sa_select(sa_func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0
    ok_r = await db.execute(
        sa_select(sa_func.count()).select_from(
            base.where(PublishRecord.success).subquery()
        )
    )
    ok = ok_r.scalar() or 0
    prov_r = await db.execute(
        sa_select(PublishRecord.provider, sa_func.count(), sa_func.sum(PublishRecord.success))
        .where(PublishRecord.user_id == current_user.id, PublishRecord.created_at >= since)
        .group_by(PublishRecord.provider)
    )
    by_provider = {
        row[0]: {"total": row[1], "success": int(row[2] or 0)}
        for row in prov_r
    }
    return {
        "days": days,
        "total": total,
        "success": ok,
        "failed": total - ok,
        "success_rate": round(ok / total * 100, 1) if total else 0,
        "by_provider": by_provider,
    }


@router.get("/send-records/{record_id}")
async def get_send_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single send record's full detail (including complete content)."""
    result = await db.execute(
        sa_select(PublishRecord).where(
            PublishRecord.id == record_id,
            PublishRecord.user_id == current_user.id,
        )
    )
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {
        "id": r.id,
        "provider": r.provider,
        "channel_id": r.channel_id,
        "title": r.title,
        "content_preview": r.content_preview,
        "success": r.success,
        "remote_url": r.remote_url,
        "remote_id": r.remote_id,
        "error_message": r.error_message,
        "error_code": r.error_code,
        "status": r.status,
        "media_type": r.media_type,
        "workflow_run_id": r.workflow_run_id,
        "workflow_name": r.workflow_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
    }
