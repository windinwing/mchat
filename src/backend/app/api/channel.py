"""Channel management API router."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import require_permission, Permission
from app.models.user import User
from app.schemas.channel import (
    ChannelCreate,
    ChannelResponse,
    ChannelWorkflowBindingBundle,
    ChannelWorkflowStatsResponse,
    ChannelWorkflowTemplateCreate,
    ChannelWorkflowTemplateResponse,
    ChannelWorkflowPreviewRequest,
    ChannelWorkflowPreviewResponse,
    ChannelWorkflowBindingResponse,
    ChannelWorkflowBindingUpdate,
    ChannelTestRequest,
    ChannelUpdate,
)
from app.services.channel_service import ChannelService
from app.utils.request import extract_client_ip

router = APIRouter()


def _webhook_url(request: Request, channel_type: str, channel_id: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/channels/webhook/{channel_type}/{channel_id}"


@router.get("/webhook/wechat/{channel_id}")
async def wechat_webhook_verify(
    channel_id: str,
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """WeChat server URL verification (configure this URL in 微信公众平台)."""
    from app.models.channel import Channel

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "wechat")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="WeChat channel not found")

    token = (channel.config or {}).get("token", "")
    check = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode()
    ).hexdigest()
    if check != signature:
        raise HTTPException(status_code=403, detail="Invalid signature")
    return int(echostr) if echostr.isdigit() else echostr


@router.post("/webhook/wechat/{channel_id}")
async def wechat_webhook_receive(
    channel_id: str,
    request: Request,
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    msg_signature: str | None = Query(None, alias="msg_signature"),
    encrypt_type: str | None = Query(None, alias="encrypt_type"),
    db: AsyncSession = Depends(get_db),
):
    """Receive WeChat user messages and return passive XML reply."""
    from app.models.channel import Channel
    from app.services.wechat_channel_service import handle_wechat_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "wechat")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="WeChat channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    body = await request.body()
    try:
        reply_body = await handle_wechat_webhook(
            channel,
            body=body,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            encrypt_type=encrypt_type,
            msg_signature=msg_signature,
            client_ip=extract_client_ip(request),
            db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WeChat webhook error: {e}", exc_info=True)
        return PlainTextResponse("success")

    if reply_body == "success":
        return PlainTextResponse("success")
    return Response(content=reply_body, media_type="application/xml")


# ─── Telegram webhook ────────────────────────────────────────────

@router.post("/webhook/telegram/{channel_id}")
async def telegram_webhook_receive(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive Telegram Bot API updates."""
    from app.models.channel import Channel
    from app.services.telegram_channel_service import handle_telegram_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "telegram")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Telegram channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    body = await request.body()
    try:
        return await handle_telegram_webhook(
            channel, body=body, client_ip=extract_client_ip(request), db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}", exc_info=True)
        return {"ok": True}


# ─── WhatsApp webhook ────────────────────────────────────────────

@router.get("/webhook/whatsapp/{channel_id}")
async def whatsapp_webhook_verify(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """WhatsApp webhook verification (GET with hub.mode, hub.verify_token, hub.challenge)."""
    from app.models.channel import Channel

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "whatsapp")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")

    mode = request.query_params.get("hub.mode", "")
    challenge = request.query_params.get("hub.challenge", "")
    verify_token = request.query_params.get("hub.verify_token", "")
    config = channel.config or {}
    expected_token = str(config.get("verify_token") or "")

    if mode == "subscribe" and verify_token == expected_token:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/whatsapp/{channel_id}")
async def whatsapp_webhook_receive(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive WhatsApp Cloud API webhook events."""
    from app.models.channel import Channel
    from app.services.whatsapp_channel_service import handle_whatsapp_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "whatsapp")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    body = await request.body()
    config = channel.config or {}

    # Verify X-Hub-Signature-256 (Meta requires this for POST)
    app_secret = str(config.get("app_secret") or "").strip()
    if app_secret:
        import hashlib
        import hmac

        sig_header = request.headers.get("X-Hub-Signature-256", "")
        if not sig_header.startswith("sha256="):
            raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")
        expected = sig_header[7:]
        computed = hmac.new(
            app_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(computed, expected):
            raise HTTPException(status_code=401, detail="Signature mismatch")

    try:
        return await handle_whatsapp_webhook(
            channel, body=body, client_ip=extract_client_ip(request), db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}", exc_info=True)
        return {"ok": True}


# ─── Slack webhook ───────────────────────────────────────────────

@router.post("/webhook/slack/{channel_id}")
async def slack_webhook_receive(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive Slack Events API events."""
    from app.models.channel import Channel
    from app.services.slack_channel_service import handle_slack_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "slack")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Slack channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    body = await request.body()
    try:
        return await handle_slack_webhook(
            channel, body=body, client_ip=extract_client_ip(request), db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}", exc_info=True)
        return {"ok": True}


# ─── LINE webhook ────────────────────────────────────────────────

@router.post("/webhook/line/{channel_id}")
async def line_webhook_receive(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive LINE Messaging API webhook events."""
    from app.models.channel import Channel
    from app.services.line_channel_service import handle_line_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "line")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="LINE channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    signature_header = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        return await handle_line_webhook(
            channel, body=body, signature_header=signature_header,
            client_ip=extract_client_ip(request), db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LINE webhook error: {e}", exc_info=True)
        return {"ok": True}


# ─── DingTalk webhook ────────────────────────────────────────────

@router.post("/webhook/dingtalk/{channel_id}")
async def dingtalk_webhook_receive(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive DingTalk outgoing message webhook events."""
    from app.models.channel import Channel
    from app.services.dingtalk_channel_service import handle_dingtalk_webhook

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.channel_type == "dingtalk")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="DingTalk channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=403, detail="Channel disabled")

    body = await request.body()
    config = channel.config or {}

    # Verify DingTalk signature
    app_secret = str(config.get("app_secret") or "").strip()
    if app_secret:
        import hashlib
        import hmac
        from base64 import b64encode

        timestamp = request.headers.get("timestamp", "")
        sign = request.headers.get("sign", "")
        if not timestamp or not sign:
            raise HTTPException(status_code=401, detail="Missing DingTalk signature headers")
        string_to_sign = f"{timestamp}\n{app_secret}"
        computed = b64encode(
            hmac.new(
                app_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        if computed != sign:
            raise HTTPException(status_code=401, detail="DingTalk signature mismatch")

    try:
        return await handle_dingtalk_webhook(
            channel, body=body, client_ip=extract_client_ip(request), db=db,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DingTalk webhook error: {e}", exc_info=True)
        return {"ok": True}


# ─── Webhook info ────────────────────────────────────────────────

@router.get("/{channel_id}/webhook-info")
async def get_channel_webhook_info(
    channel_id: str,
    request: Request,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Return callback URL for channel types that need external webhook configuration."""
    service = ChannelService(db)
    channel = await service.get_channel(channel_id=channel_id, user_id=admin.id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    url = _webhook_url(request, channel.channel_type, channel_id)
    hints: dict[str, str] = {
        "wechat": (
            "在微信公众号后台 → 开发 → 基本配置 → 服务器配置，填入此 URL；"
            "Token、EncodingAESKey 与本页一致，并务必选择「客服配置（Agent）」"
        ),
        "telegram": "Use this URL with setWebhook: https://api.telegram.org/bot<TOKEN>/setWebhook?url=<THIS_URL>",
        "whatsapp": "In Meta Business App → WhatsApp → Configuration → Webhook, set this as Callback URL and enter the Verify Token from config.",
        "slack": "In Slack App → Event Subscriptions → Request URL, set this URL. Also enable events: message.channels, app_mention.",
        "line": "In LINE Developers Console → Messaging API → Webhook URL, set this URL.",
        "dingtalk": "In DingTalk Open Platform → Robot → Outgoing Message, set this URL.",
    }
    hint = hints.get(channel.channel_type)
    return {"channel_type": channel.channel_type, "webhook_url": url, "hint": hint}


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List all channels."""
    service = ChannelService(db)
    return await service.list_channels(user_id=admin.id)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get a channel."""
    service = ChannelService(db)
    channel = await service.get_channel(
        channel_id=channel_id, user_id=admin.id
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    request: ChannelCreate,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new channel."""
    service = ChannelService(db)
    return await service.create_channel(
        user_id=admin.id, data=request
    )


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: str,
    request: ChannelUpdate,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update a channel."""
    service = ChannelService(db)
    channel = await service.update_channel(
        channel_id=channel_id, user_id=admin.id, data=request
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a channel."""
    service = ChannelService(db)
    success = await service.delete_channel(
        channel_id=channel_id, user_id=admin.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found")
    return None


@router.post("/test", response_model=dict)
async def test_channel(
    request: ChannelTestRequest,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Test a channel connection."""
    service = ChannelService(db)
    return await service.test_channel(
        user_id=admin.id,
        channel_type=request.channel_type,
        config=request.config,
    )


@router.get("/{channel_id}/workflows", response_model=list[ChannelWorkflowBindingResponse])
async def list_channel_workflows(
    channel_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    return await service.list_channel_workflow_bindings(
        channel_id=channel_id, user_id=admin.id
    )


@router.put("/{channel_id}/workflows", response_model=list[ChannelWorkflowBindingResponse])
async def replace_channel_workflows(
    channel_id: str,
    request: ChannelWorkflowBindingUpdate,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    try:
        return await service.replace_channel_workflow_bindings(
            channel_id=channel_id,
            user_id=admin.id,
            bindings=request.bindings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{channel_id}/workflows/preview",
    response_model=ChannelWorkflowPreviewResponse,
)
async def preview_channel_workflow_match(
    channel_id: str,
    request: ChannelWorkflowPreviewRequest,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    try:
        return await service.preview_channel_workflow_bindings(
            channel_id=channel_id,
            user_id=admin.id,
            content=request.content,
            event_type=request.event_type,
            dispatch_mode=request.dispatch_mode,
            bindings_override=request.bindings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{channel_id}/workflows/export", response_model=ChannelWorkflowBindingBundle)
async def export_channel_workflow_bundle(
    channel_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    try:
        return await service.export_channel_workflow_bundle(
            channel_id=channel_id,
            user_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{channel_id}/workflows/import", response_model=list[ChannelWorkflowBindingResponse])
async def import_channel_workflow_bundle(
    channel_id: str,
    request: ChannelWorkflowBindingBundle,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    try:
        return await service.import_channel_workflow_bundle(
            channel_id=channel_id,
            user_id=admin.id,
            bundle=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{channel_id}/workflows/stats", response_model=ChannelWorkflowStatsResponse)
async def channel_workflow_stats(
    channel_id: str,
    days: int = Query(default=7, ge=1, le=90),
    admin: User = Depends(require_permission(Permission.CHANNELS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    return await service.channel_workflow_stats(
        channel_id=channel_id,
        user_id=admin.id,
        days=days,
    )


@router.get("/templates/workflow", response_model=list[ChannelWorkflowTemplateResponse])
async def list_channel_workflow_templates(
    admin: User = Depends(require_permission(Permission.CHANNELS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await ChannelService(db).list_workflow_templates(user_id=admin.id)


@router.post("/templates/workflow", response_model=ChannelWorkflowTemplateResponse)
async def create_channel_workflow_template(
    request: ChannelWorkflowTemplateCreate,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await ChannelService(db).save_workflow_template(
        user_id=admin.id,
        data=request,
    )


@router.delete("/templates/workflow/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_workflow_template(
    template_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    ok = await ChannelService(db).delete_workflow_template(
        user_id=admin.id,
        template_id=template_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    return None


@router.post(
    "/{channel_id}/workflows/apply-template/{template_id}",
    response_model=list[ChannelWorkflowBindingResponse],
)
async def apply_channel_workflow_template(
    channel_id: str,
    template_id: str,
    admin: User = Depends(require_permission(Permission.CHANNELS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = ChannelService(db)
    try:
        return await service.apply_workflow_template_to_channel(
            channel_id=channel_id,
            user_id=admin.id,
            template_id=template_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
