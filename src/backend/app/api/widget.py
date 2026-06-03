"""Widget/public API router (no auth required for most endpoints)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.models.customer import CustomerConfig
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.schemas.agent import CustomerConfigResponse
from app.schemas.chat import ConversationResponse, InitConversationRequest
from app.schemas.speech import SpeechConfigResponse, TranscribeResponse
from app.services.stt_service import STTError, STTService
from app.services.chat_service import ChatService
from app.services.subscription_gate import (
    channel_subscription_active,
    subscription_inactive_message,
)
from app.services.widget_chat_service import (
    ensure_widget_domain_allowed,
    prepare_widget_chat,
    resolve_assistant_message,
    sse_line,
    widget_contact_info,
)
from app.utils.chat_upload import save_chat_attachment
from app.utils.request import extract_client_ip


def _conversation_belongs_to_customer(
    conversation: Conversation,
    customer_id: str,
    customer: CustomerConfig,
    visitor_token: str | None = None,
) -> bool:
    """Ensure visitor conversation belongs to this widget customer and visitor."""
    from app.services.widget_chat_service import _visitor_matches

    if conversation.user_id is not None:
        return False
    if not _visitor_matches(conversation, visitor_token):
        return False
    if conversation.customer_id == customer_id:
        return True
    if conversation.contact_info == widget_contact_info(customer_id):
        return True
    return False


def _normalize_id_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        sid = str(item).strip()
        if sid:
            out.append(sid)
    return out


async def _resolve_skill_override_ids(
    db: AsyncSession,
    *,
    user_id: str,
    skill_id: str | None,
) -> list[str] | None:
    sid = (skill_id or "").strip()
    if not sid:
        return None

    result = await db.execute(
        select(Skill).where(
            Skill.id == sid,
            Skill.user_id == user_id,
            Skill.enabled == True,
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=400, detail="指定技能不存在或已禁用")
    return [skill.id]


class WidgetChatRequest(BaseModel):
    """Request body for widget chat endpoint."""
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(None, alias="conversationId")
    visitor_token: str | None = Field(
        None,
        alias="visitorToken",
        max_length=64,
        description="Per-browser-tab visitor id; must match conversation owner",
    )
    skill_id: str | None = Field(None, alias="skillId")

    model_config = {"populate_by_name": True}


class WidgetChatResponse(BaseModel):
    """Response for widget chat."""
    response: str = Field(..., alias="response")
    conversation_id: str = Field(..., alias="conversationId")
    message_id: str = Field(..., alias="messageId")
    user_attachments: list[dict] | None = Field(None, alias="userAttachments")

    model_config = {"populate_by_name": True}


router = APIRouter()


@router.get("/config/{customer_id}", response_model=CustomerConfigResponse)
async def get_widget_config(
    customer_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get widget configuration for embedding (no auth)."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Widget config not found")
    ensure_widget_domain_allowed(config, request)
    return config


@router.get("/config/{customer_id}/full")
async def get_widget_config_full(
    customer_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get full widget configuration including theme, welcome message, etc."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Widget config not found")

    ensure_widget_domain_allowed(config, request)

    sub_active = channel_subscription_active(config)
    theme = config.theme or {}
    return {
        "id": config.id,
        "name": config.name,
        "welcome_message": config.welcome_message or "你好！有什么可以帮助你的？",
        "offline_message": (
            config.offline_message
            if sub_active
            else subscription_inactive_message(config)
        ),
        "subscription_active": sub_active,
        "position": config.position,
        "theme": {
            "primaryColor": theme.get("primaryColor", "#3b82f6"),
            "botName": theme.get("botName", config.name),
            "widgetTitle": theme.get("widgetTitle", config.name),
            "launcherIcon": theme.get("launcherIcon", "chat"),
            "launcherText": theme.get("launcherText", ""),
            "showcaseSkillIds": _normalize_id_list(theme.get("showcaseSkillIds")),
        },
        "enabled": config.enabled,
        "pre_chat_fields": config.pre_chat_fields or [],
    }


@router.get("/config/{customer_id}/showcase")
async def get_widget_showcase_config(
    customer_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get skill showcase config for rendering multi-skill chat panels."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Widget config not found")

    ensure_widget_domain_allowed(config, request)

    theme = config.theme or {}
    showcase_ids = _normalize_id_list(theme.get("showcaseSkillIds"))
    showcase_set = set(showcase_ids)

    allowed_skill_ids = set(_normalize_id_list(config.skill_ids))

    result = await db.execute(
        select(Skill).where(
            Skill.user_id == config.user_id,
            Skill.enabled == True,
        )
    )
    all_skills = list(result.scalars().all())

    visible_skills = []
    for skill in all_skills:
        if skill.id not in allowed_skill_ids:
            continue
        if showcase_set and skill.id not in showcase_set:
            continue
        visible_skills.append(skill)

    return {
        "customer_id": config.id,
        "name": config.name,
        "welcome_message": config.welcome_message or "你好！有什么可以帮助你的？",
        "theme": {
            "primaryColor": theme.get("primaryColor", "#3b82f6"),
            "botName": theme.get("botName", config.name),
            "widgetTitle": theme.get("widgetTitle", config.name),
            "launcherIcon": theme.get("launcherIcon", "chat"),
            "launcherText": theme.get("launcherText", ""),
            "showcaseSkillIds": showcase_ids,
        },
        "skills": [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
            }
            for skill in visible_skills
        ],
    }


@router.get("/showcases")
async def list_public_showcases(
    db: AsyncSession = Depends(get_db),
):
    """List enabled customer agents that expose at least one showcase skill."""
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.enabled == True)
    )
    configs = list(result.scalars().all())

    showcases: list[dict] = []
    for config in configs:
        theme = config.theme or {}
        showcase_ids = _normalize_id_list(theme.get("showcaseSkillIds"))
        allowed_skill_ids = set(_normalize_id_list(config.skill_ids))

        result = await db.execute(
            select(Skill).where(
                Skill.user_id == config.user_id,
                Skill.enabled == True,
            )
        )
        all_skills = list(result.scalars().all())

        visible_skills = []
        for skill in all_skills:
            if skill.id not in allowed_skill_ids:
                continue
            if showcase_ids and skill.id not in showcase_ids:
                continue
            visible_skills.append(skill)

        if not visible_skills:
            continue

        showcases.append(
            {
                "customer_id": config.id,
                "name": config.name,
                "welcome_message": config.welcome_message or "你好！有什么可以帮助你的？",
                "theme": {
                    "primaryColor": theme.get("primaryColor", "#3b82f6"),
                    "botName": theme.get("botName", config.name),
                    "widgetTitle": theme.get("widgetTitle", config.name),
                    "launcherIcon": theme.get("launcherIcon", "chat"),
                    "launcherText": theme.get("launcherText", ""),
                },
                "skill_count": len(visible_skills),
                "skills": [
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                    }
                    for skill in visible_skills[:6]
                ],
            }
        )

    return {"items": showcases}


@router.post("/conversation", response_model=ConversationResponse)
async def create_visitor_conversation(
    request: InitConversationRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a visitor conversation (no auth)."""
    chat_service = ChatService(db)
    conversation = await chat_service.init_visitor_conversation(
        visitor_id=request.visitor_id,
        title=request.title,
        ai_config_id=request.ai_config_id,
        contact_info=request.contact_info,
        client_ip=extract_client_ip(http_request),
    )
    return conversation


@router.post("/{customer_id}/upload", response_model=WidgetChatResponse)
async def widget_upload_attachment(
    customer_id: str,
    http_request: Request,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None, alias="conversationId"),
    visitor_token: str | None = Form(None, alias="visitorToken"),
    skill_id: str | None = Form(None, alias="skillId"),
    content: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload image/file from widget and get AI reply."""
    attachment = await save_chat_attachment(file)
    display = (content or "").strip() or attachment["name"]
    try:
        ctx = await prepare_widget_chat(
            db,
            customer_id,
            display,
            conversation_id,
            http_request,
            visitor_token=visitor_token,
            extra_data={"attachments": [attachment]},
        )
        from app.bot.engine import process_message

        skill_ids_override = await _resolve_skill_override_ids(
            db,
            user_id=ctx.customer.user_id,
            skill_id=skill_id,
        )

        full_response = ""
        async for token in process_message(
            ctx.conversation,
            ctx.user_message,
            ctx.ai_config,
            db,
            customer_config=ctx.customer,
            skill_ids_override=skill_ids_override,
        ):
            full_response += token

        await db.flush()
        assistant_msg = await resolve_assistant_message(db, ctx.conversation.id)
        await db.commit()

        return WidgetChatResponse(
            response=full_response or "抱歉，我暂时无法回复，请稍后再试。",
            conversation_id=ctx.conversation.id,
            message_id=assistant_msg.id if assistant_msg else ctx.user_message.id,
            user_attachments=[attachment],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Widget upload error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}",
        ) from e


@router.post("/{customer_id}/chat", response_model=WidgetChatResponse)
async def widget_chat(
    customer_id: str,
    body: WidgetChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a message from widget and get AI reply (no auth, non-streaming fallback)."""
    try:
        ctx = await prepare_widget_chat(
            db,
            customer_id,
            body.message,
            body.conversation_id,
            http_request,
            visitor_token=body.visitor_token,
        )
        from app.bot.engine import process_message
        from app.bot.reply_persist import ensure_assistant_reply_persisted

        skill_ids_override = await _resolve_skill_override_ids(
            db,
            user_id=ctx.customer.user_id,
            skill_id=body.skill_id,
        )

        full_response = ""
        async for token in process_message(
            ctx.conversation,
            ctx.user_message,
            ctx.ai_config,
            db,
            customer_config=ctx.customer,
            skill_ids_override=skill_ids_override,
        ):
            full_response += token

        await db.flush()
        assistant_msg = await ensure_assistant_reply_persisted(
            db,
            ctx.conversation,
            ctx.user_message,
            full_response,
            ctx.ai_config,
        )
        if assistant_msg is None:
            assistant_msg = await resolve_assistant_message(db, ctx.conversation.id)
        await db.commit()

        return WidgetChatResponse(
            response=full_response or "抱歉，我暂时无法回复，请稍后再试。",
            conversation_id=ctx.conversation.id,
            message_id=assistant_msg.id if assistant_msg else ctx.user_message.id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Widget chat error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"AI processing error: {str(e)}",
        ) from e


@router.post("/{customer_id}/chat/stream")
async def widget_chat_stream(
    customer_id: str,
    body: WidgetChatRequest,
    http_request: Request,
):
    """Stream AI reply as Server-Sent Events (no auth)."""

    async def event_generator():
        from app.bot.engine import process_message
        from app.bot.reply_persist import ensure_assistant_reply_persisted

        async with async_session_factory() as db:
            try:
                ctx = await prepare_widget_chat(
                    db,
                    customer_id,
                    body.message,
                    body.conversation_id,
                    http_request,
                    visitor_token=body.visitor_token,
                )
                skill_ids_override = await _resolve_skill_override_ids(
                    db,
                    user_id=ctx.customer.user_id,
                    skill_id=body.skill_id,
                )
                full_response = ""
                async for token in process_message(
                    ctx.conversation,
                    ctx.user_message,
                    ctx.ai_config,
                    db,
                    customer_config=ctx.customer,
                    skill_ids_override=skill_ids_override,
                ):
                    full_response += token
                    yield sse_line("token", {"content": token})

                await db.flush()
                assistant_msg = await ensure_assistant_reply_persisted(
                    db,
                    ctx.conversation,
                    ctx.user_message,
                    full_response,
                    ctx.ai_config,
                )
                if assistant_msg is None:
                    assistant_msg = await resolve_assistant_message(
                        db, ctx.conversation.id
                    )
                await db.commit()

                yield sse_line(
                    "done",
                    {
                        "content": full_response,
                        "conversationId": ctx.conversation.id,
                        "messageId": assistant_msg.id
                        if assistant_msg
                        else ctx.user_message.id,
                    },
                )
            except HTTPException as e:
                await db.rollback()
                yield sse_line("error", {"message": e.detail})
            except BaseException as e:
                logger.error(f"Widget stream error: {e}", exc_info=True)
                await db.rollback()
                yield sse_line("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{customer_id}/conversation/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_widget_conversation(
    customer_id: str,
    conversation_id: str,
    request: Request,
    visitor_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Load widget conversation history (no auth)."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found or disabled")

    ensure_widget_domain_allowed(customer, request)

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.status == "active",
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not _conversation_belongs_to_customer(
        conversation, customer_id, customer, visitor_token
    ):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    return ConversationResponse.model_validate(conversation)


@router.get("/{customer_id}/speech/config", response_model=SpeechConfigResponse)
async def widget_speech_config(
    customer_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SpeechConfigResponse:
    """STT config for widget chat (no auth)."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found or disabled")
    ensure_widget_domain_allowed(customer, request)
    return SpeechConfigResponse(**STTService().get_public_config())


@router.post("/{customer_id}/speech/transcribe", response_model=TranscribeResponse)
async def widget_transcribe_audio(
    customer_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> TranscribeResponse:
    """Upload audio from widget and return transcribed text."""
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found or disabled")
    ensure_widget_domain_allowed(customer, request)

    data = await file.read()
    try:
        text, provider = await STTService().transcribe(
            data,
            filename=file.filename or "audio.webm",
            content_type=file.content_type,
        )
    except STTError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"语音识别失败: {e}",
        ) from e

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未识别到语音内容，请重试",
        )
    return TranscribeResponse(text=text, provider=provider)


@router.get("/online-agents")
async def list_online_agents():
    """List currently online agents (simple stub)."""
    from app.customer.manager import customer_manager
    return {
        "agents": customer_manager.get_online_agents(),
        "count": customer_manager.get_online_count(),
    }
