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
