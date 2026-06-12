"""Bot engine event handler - processes messages and streams AI responses."""

from fastapi import HTTPException as FastAPIHTTPException
from loguru import logger
from sqlalchemy import select

from app.bot.engine import process_message
from app.bot.patent_links import linkify_patent_ids, patent_link_settings_from_skills
from app.bot.reply_persist import ensure_assistant_reply_persisted, persist_assistant_reply
from app.services.llm_credentials import ensure_ai_config_api_key, is_usable_api_key
from app.core.database import async_session_factory
from app.core.event_bus import event_bus
from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.services.subscription_gate import ensure_channel_subscription_active
from app.models.message import Message
from app.models.user import User
from app.websocket import ws_manager

_bot_engine_initialized = False


async def on_message_created(
    message: Message,
    conversation: Conversation,
    user: User | None = None,
) -> None:
    """Handle message_created event: process with bot engine and stream response.

    Opens a fresh DB session, reloads the conversation, loads AI config,
    and streams AI-generated tokens to WebSocket subscribers.
    """
    cov_id = conversation.id
    logger.info(f"Bot processing message {message.id} in conversation {cov_id}")

    try:
        async with async_session_factory() as db:
            # Reload conversation in this session so ORM changes are tracked
            conv_result = await db.execute(
                select(Conversation).where(Conversation.id == cov_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv is None:
                logger.warning(f"Conversation {cov_id} not found")
                return

            customer_config = None
            if conv.customer_id:
                cust_result = await db.execute(
                    select(CustomerConfig).where(
                        CustomerConfig.id == conv.customer_id
                    )
                )
                customer_config = cust_result.scalar_one_or_none()
                if customer_config is not None:
                    try:
                        ensure_channel_subscription_active(customer_config)
                    except FastAPIHTTPException as sub_exc:
                        detail = sub_exc.detail
                        msg = (
                            detail.get("message")
                            if isinstance(detail, dict)
                            else str(detail)
                        )
                        await ws_manager.send_to_conversation(
                            cov_id,
                            {
                                "type": "chat:message",
                                "role": "assistant",
                                "content": msg or "订阅已到期",
                                "done": True,
                            },
                        )
                        return

            async def _load_ai_config(config_id: str | None) -> AIConfig | None:
                if not config_id:
                    return None
                cfg_result = await db.execute(
                    select(AIConfig).where(AIConfig.id == config_id)
                )
                return cfg_result.scalar_one_or_none()

            # Portal/widget: channel's AI config must win over global default (e.g. broken DeepSeek)
            ai_config = None
            channel_ai_id = (
                customer_config.ai_config_id if customer_config is not None else None
            )
            if channel_ai_id:
                ai_config = await _load_ai_config(channel_ai_id)
                if ai_config is not None and conv.ai_config_id != channel_ai_id:
                    conv.ai_config_id = channel_ai_id
                    await db.flush()

            if ai_config is None and conv.ai_config_id:
                ai_config = await _load_ai_config(conv.ai_config_id)

            if ai_config is None:
                cfg_result = await db.execute(
                    select(AIConfig).where(AIConfig.is_default == True)
                )
                ai_config = cfg_result.scalar_one_or_none()

            if ai_config is None:
                cfg_result = await db.execute(
                    select(AIConfig).where(AIConfig.api_key != "").limit(1)
                )
                ai_config = cfg_result.scalar_one_or_none()

            if ai_config is None:
                cfg_result = await db.execute(select(AIConfig).limit(1))
                ai_config = cfg_result.scalar_one_or_none()

            if ai_config is None:
                error_msg = (
                    "No AI configuration found. "
                    "Please configure an AI provider in the admin panel."
                )
                logger.warning(error_msg)
                err_row = await persist_assistant_reply(
                    db, conv, error_msg, is_error=True
                )
                await db.commit()
                await ws_manager.send_to_conversation(
                    cov_id,
                    {
                        "type": "chat:message",
                        "message": {
                            "id": err_row.id,
                            "role": "assistant",
                            "content": error_msg,
                            "conversation_id": cov_id,
                            "created_at": err_row.created_at.isoformat(),
                            "extra_data": {"is_error": True},
                        },
                    },
                )
                return

            ai_config = await ensure_ai_config_api_key(db, ai_config)
            if not is_usable_api_key(ai_config.api_key):
                error_msg = (
                    "未配置有效的 AI API 密钥。请在管理后台「模型工作台」填写 API Key，"
                    "或在 .env 设置 DEEPSEEK_API_KEY / MOONSHOT_API_KEY。"
                )
                logger.warning(error_msg)
                err_row = await persist_assistant_reply(
                    db, conv, error_msg, is_error=True, ai_config=ai_config
                )
                await db.commit()
                await ws_manager.send_to_conversation(
                    cov_id,
                    {
                        "type": "chat:message",
                        "message": {
                            "id": err_row.id,
                            "role": "assistant",
                            "content": error_msg,
                            "conversation_id": cov_id,
                            "created_at": err_row.created_at.isoformat(),
                            "extra_data": {"is_error": True},
                        },
                    },
                )
                return

            logger.info(
                f"Using AI config {ai_config.id} ({ai_config.provider}/{ai_config.model}, "
                f"api_base={ai_config.api_base or 'default'}) for conversation {cov_id}"
            )

            # Stream AI response tokens to WebSocket
            full_content = ""
            async for token in process_message(
                conv,
                message,
                ai_config,
                db,
                customer_config=customer_config,
                end_user=user,
            ):
                full_content += token
                await ws_manager.send_to_conversation(
                    cov_id,
                    {
                        "type": "chat:stream",
                        "conversation_id": cov_id,
                        "content": token,
                    },
                )

            await db.flush()

            assistant_row = await ensure_assistant_reply_persisted(
                db, conv, message, full_content, ai_config=ai_config
            )
            assistant_id = assistant_row.id if assistant_row is not None else None

            if not full_content.strip():
                msg_result = await db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == cov_id,
                        Message.role == "assistant",
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(1)
                )
                last_assistant = msg_result.scalar_one_or_none()
                if last_assistant is not None:
                    full_content = last_assistant.content or ""
                    assistant_id = last_assistant.id
                else:
                    full_content = (
                        "AI 未返回可见内容（可能仅调用了工具但结果未展示）。"
                        "请重试；若仍失败，请检查 API Key、Base URL 与网络连接。"
                    )
                    fallback = await persist_assistant_reply(
                        db, conv, full_content, is_error=True, ai_config=ai_config
                    )
                    assistant_id = fallback.id

            # Apply patent linkification to streamed content (same as engine does for DB)
            from app.bot.patent_links import default_patent_portal_url_template
            template = default_patent_portal_url_template()
            if template:
                full_content = linkify_patent_ids(full_content, enabled=True, template=template)

            # Signal stream end (include DB id so UI can dedupe)
            await ws_manager.send_to_conversation(
                cov_id,
                {
                    "type": "chat:stream:end",
                    "conversation_id": cov_id,
                    "content": full_content,
                    "id": assistant_id,
                    "message_id": assistant_id,
                },
            )

            await db.commit()
            logger.info(f"Bot completed response for conversation {cov_id}")

    except Exception as e:
        logger.error(f"Bot engine error: {e}", exc_info=True)
        err_text = f"Sorry, I encountered an error: {str(e)}"
        try:
            async with async_session_factory() as err_db:
                conv_result = await err_db.execute(
                    select(Conversation).where(Conversation.id == cov_id)
                )
                conv = conv_result.scalar_one_or_none()
                if conv is not None:
                    err_row = await persist_assistant_reply(
                        err_db, conv, err_text, is_error=True
                    )
                    await err_db.commit()
                    await ws_manager.send_to_conversation(
                        cov_id,
                        {
                            "type": "chat:message",
                            "message": {
                                "id": err_row.id,
                                "role": "assistant",
                                "content": err_text,
                                "conversation_id": cov_id,
                                "created_at": err_row.created_at.isoformat(),
                                "extra_data": {"is_error": True},
                            },
                        },
                    )
                    return
        except Exception as persist_err:
            logger.error(f"Failed to persist bot error reply: {persist_err}")
        await ws_manager.send_to_conversation(
            cov_id,
            {
                "type": "chat:message",
                "message": {
                    "id": f"ai-error-{message.id}",
                    "role": "assistant",
                    "content": err_text,
                    "conversation_id": cov_id,
                    "created_at": "2025-01-01T00:00:00Z",
                },
            },
        )


def init_bot_engine() -> None:
    """Subscribe bot engine handler to message_created events."""
    global _bot_engine_initialized
    if _bot_engine_initialized:
        return
    _bot_engine_initialized = True
    event_bus.subscribe("message_created", on_message_created)
    logger.info("Bot engine initialized and listening for messages")
