"""WeChat Official Account webhook — message in, AI reply out."""

from __future__ import annotations

import asyncio
import html
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.engine import process_message
from app.channels.wechat_adapter import (
    build_text_reply,
    encrypt_reply_xml,
    parse_incoming,
    verify_signature,
)
from app.models.ai_config import AIConfig
from app.models.channel import Channel
from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.message import Message
from app.services.channel_service import (
    channel_get_or_create_conversation,
    channel_resolve_ai_config,
    channel_trigger_bound_workflows,
)
from app.core.database import async_session_factory

WECHAT_CONTACT_PREFIX = "wechat_channel:"
_WECHAT_PASSIVE_REPLY_TIMEOUT_SECONDS = 4.2
_WECHAT_ACTIVE_PUSH_DEFAULT = True
_WECHAT_TEXT_LIMIT = 2000
_WECHAT_TOKEN_SAFETY_WINDOW_SECONDS = 120
_WECHAT_ACCESS_TOKEN_CACHE: dict[str, tuple[str, float]] = {}

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def wechat_contact_info(channel_id: str) -> str:
    return f"{WECHAT_CONTACT_PREFIX}{channel_id}"


def _active_push_enabled(config: dict[str, Any]) -> bool:
    raw = config.get("active_push")
    if raw is None:
        return _WECHAT_ACTIVE_PUSH_DEFAULT
    if isinstance(raw, bool):
        return raw
    normalized = str(raw).strip().lower()
    return normalized not in {"0", "false", "off", "no", "n"}


def _to_wechat_plain_text(content: str) -> str:
    """Convert model markdown-like output into plain text for OA display."""
    text = html.unescape(content or "")
    text = text.replace("\r\n", "\n")
    text = _MARKDOWN_LINK_RE.sub(r"\1 \2", text)
    text = re.sub(r"```(?:[a-zA-Z0-9_+-]+)?\n?", "", text)
    text = text.replace("```", "")
    text = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if not text:
        return "抱歉，我暂时无法回复，请稍后再试。"
    if len(text) > _WECHAT_TEXT_LIMIT:
        return text[: _WECHAT_TEXT_LIMIT - 3] + "..."
    return text


def _wechat_text_error(data: dict[str, Any]) -> str:
    errcode = data.get("errcode")
    errmsg = data.get("errmsg")
    if int(errcode or 0) == 40164:
        return (
            f"errcode={errcode}, errmsg={errmsg}. "
            "请检查公众号 App Secret 是否正确，并将当前服务出口 IP 加入微信公众平台白名单。"
        )
    return f"errcode={errcode}, errmsg={errmsg}"


async def _fetch_wechat_access_token(
    app_id: str,
    app_secret: str,
    *,
    force_refresh: bool = False,
) -> str:
    now = time.time()
    cached = _WECHAT_ACCESS_TOKEN_CACHE.get(app_id)
    if (
        not force_refresh
        and cached
        and cached[0]
        and cached[1] > now + _WECHAT_TOKEN_SAFETY_WINDOW_SECONDS
    ):
        return cached[0]

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if int(data.get("errcode", 0) or 0) != 0:
        raise RuntimeError(
            f"微信 access_token 获取失败: {_wechat_text_error(data)}"
        )

    token = str(data.get("access_token") or "").strip()
    expires_in = int(data.get("expires_in") or 7200)
    if not token:
        raise RuntimeError("微信 access_token 响应缺少 access_token")
    _WECHAT_ACCESS_TOKEN_CACHE[app_id] = (
        token,
        now + max(300, expires_in - _WECHAT_TOKEN_SAFETY_WINDOW_SECONDS),
    )
    return token


async def _send_wechat_customer_text(
    *,
    app_id: str,
    app_secret: str,
    openid: str,
    content: str,
) -> None:
    payload = {
        "touser": openid,
        "msgtype": "text",
        "text": {"content": _to_wechat_plain_text(content)},
    }
    token = await _fetch_wechat_access_token(app_id, app_secret)

    async with httpx.AsyncClient(timeout=12.0) as client:
        for attempt in range(2):
            resp = await client.post(
                "https://api.weixin.qq.com/cgi-bin/message/custom/send",
                params={"access_token": token},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            errcode = int(data.get("errcode", 0) or 0)
            if errcode == 0:
                return

            if errcode in {40001, 40014, 42001} and attempt == 0:
                token = await _fetch_wechat_access_token(
                    app_id, app_secret, force_refresh=True
                )
                continue

            raise RuntimeError(
                f"微信客服消息发送失败: {_wechat_text_error(data)}"
            )


def _log_background_task_error(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except Exception as e:  # pragma: no cover - background task safety log
        logger.error(f"WeChat background push task failed: {e}", exc_info=True)


async def _push_wechat_reply_in_background(
    *,
    channel_id: str,
    customer_id: str,
    conversation_id: str,
    user_message_id: str,
    openid: str,
    app_id: str,
    app_secret: str,
) -> None:
    async with async_session_factory() as db:
        try:
            channel = await db.get(Channel, channel_id)
            customer = await db.get(CustomerConfig, customer_id)
            conversation = await db.get(Conversation, conversation_id)
            user_message = await db.get(Message, user_message_id)

            if (
                channel is None
                or customer is None
                or conversation is None
                or user_message is None
            ):
                logger.warning(
                    "Skip WeChat push due to missing records: "
                    f"channel={channel_id} customer={customer_id} "
                    f"conversation={conversation_id} msg={user_message_id}"
                )
                return

            ai_config = await channel_resolve_ai_config(db, customer)
            if ai_config is None:
                reply_text = "未配置 AI 模型，请在管理后台设置默认模型或绑定客服 Agent 的模型。"
            else:
                full_response = ""
                async for token in process_message(
                    conversation,
                    user_message,
                    ai_config,
                    db,
                    customer_config=customer,
                ):
                    full_response += token
                await db.commit()
                reply_text = (full_response or "").strip() or "抱歉，我暂时无法回复，请稍后再试。"

            await _send_wechat_customer_text(
                app_id=app_id,
                app_secret=app_secret,
                openid=openid,
                content=reply_text,
            )
        except Exception as e:
            logger.error(f"WeChat active push failed: {e}", exc_info=True)
            await db.rollback()


async def handle_wechat_webhook(
    channel: Channel,
    *,
    body: bytes,
    signature: str,
    timestamp: str,
    nonce: str,
    encrypt_type: str | None,
    msg_signature: str | None,
    client_ip: str | None,
    db: AsyncSession,
) -> str:
    """Process WeChat push and return XML response body (plaintext or encrypted)."""
    config = channel.config or {}
    token = str(config.get("token") or "")
    app_id = str(config.get("app_id") or "")
    encoding_aes_key = str(config.get("encoding_aes_key") or "")

    if not verify_signature(token, timestamp, nonce, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        parsed = parse_incoming(
            body,
            token=token,
            app_id=app_id,
            encoding_aes_key=encoding_aes_key,
            encrypt_type=encrypt_type,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    except Exception as e:
        logger.error(f"WeChat parse failed: {e}", exc_info=True)
        return "success"

    to_user = parsed.get("from_user", "")
    from_user = parsed.get("to_user", "")
    msg_type = parsed.get("msg_type", "")

    if not to_user or not from_user:
        logger.warning(f"WeChat message missing addresses: {parsed}")
        return "success"

    reply_text = await _dispatch_message(
        channel, parsed, db, openid=to_user, client_ip=client_ip
    )

    if not reply_text:
        return "success"

    return _wrap_reply(
        channel,
        parsed_fallback_to=to_user,
        to_user=to_user,
        from_user=from_user,
        content=reply_text,
        encrypt_type=encrypt_type,
        encoding_aes_key=encoding_aes_key,
        app_id=app_id,
        token=token,
        timestamp=timestamp,
        nonce=nonce,
    )


def _wrap_reply(
    channel: Channel,
    *,
    parsed_fallback_to: str,
    to_user: str,
    from_user: str,
    content: str,
    encrypt_type: str | None,
    encoding_aes_key: str,
    app_id: str,
    token: str,
    timestamp: str,
    nonce: str,
) -> str:
    if not to_user and parsed_fallback_to:
        to_user = parsed_fallback_to
    reply_xml = build_text_reply(to_user, from_user, content)
    if encrypt_type == "aes" and encoding_aes_key and app_id:
        return encrypt_reply_xml(
            reply_xml,
            token=token,
            encoding_aes_key=encoding_aes_key,
            app_id=app_id,
            timestamp=timestamp,
            nonce=nonce,
        )
    return reply_xml


async def _dispatch_message(
    channel: Channel,
    parsed: dict[str, str],
    db: AsyncSession,
    *,
    openid: str,
    client_ip: str | None,
) -> str:
    msg_type = parsed.get("msg_type", "")
    config = channel.config or {}
    customer_id = str(config.get("customer_id") or "").strip()

    if msg_type == "event":
        event = (parsed.get("event") or "").lower()
        if event == "subscribe":
            welcome = await _welcome_for_customer(customer_id, db)
            return _to_wechat_plain_text(
                welcome or "欢迎关注！直接发送文字即可开始对话。"
            )
        return ""

    if msg_type == "text":
        text = (parsed.get("content") or "").strip()
        if not text:
            return ""
        if _active_push_enabled(config):
            app_id = str(config.get("app_id") or "").strip()
            app_secret = str(config.get("app_secret") or "").strip()
            if not app_id or not app_secret:
                return "请先在频道配置中填写 App ID 和 App Secret。"

            queued, fallback_reply = await _queue_active_text_message(
                channel,
                customer_id,
                openid,
                text,
                db,
                client_ip=client_ip,
                app_id=app_id,
                app_secret=app_secret,
            )
            if queued:
                return ""
            return _to_wechat_plain_text(fallback_reply)

        return await _process_text_message(
            channel, customer_id, openid, text, db, client_ip=client_ip
        )

    if msg_type in ("image", "voice", "video", "shortvideo", "location", "link"):
        return _to_wechat_plain_text("暂仅支持文字消息，请直接输入您的问题。")

    return ""


async def _queue_active_text_message(
    channel: Channel,
    customer_id: str,
    openid: str,
    text: str,
    db: AsyncSession,
    *,
    client_ip: str | None,
    app_id: str,
    app_secret: str,
) -> tuple[bool, str]:
    if not customer_id:
        return (
            False,
            "公众号尚未绑定客服 Agent。请在 mchat 管理后台 → 频道管理 → "
            "编辑此微信公众号，选择「客服配置（Agent）」。",
        )

    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        return False, "绑定的客服配置不存在或已禁用，请联系管理员。"

    if customer.user_id != channel.user_id:
        return False, "客服配置与频道不属于同一账号，请重新绑定。"

    try:
        await _fetch_wechat_access_token(app_id, app_secret)
    except Exception as e:
        logger.warning(
            "WeChat active push unavailable, fallback to passive reply: channel={} openid={} error={}",
            channel.id,
            openid,
            e,
        )
        return False, (
            "当前无法使用微信公众号主动下发，已自动切回被动回复。"
            f"原因：{e}"
        )

    conversation = await channel_get_or_create_conversation(
        db,
        openid,
        customer,
        contact_info=wechat_contact_info(channel.id),
        title=f"WeChat: {customer.name}",
        client_ip=client_ip,
    )

    user_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=text,
    )
    db.add(user_message)
    await db.flush()

    conversation.updated_at = datetime.now(timezone.utc)
    conversation.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    try:
        await channel_trigger_bound_workflows(
            db,
            channel,
            event_type="message",
            event_payload={
                "sender_id": openid,
                "conversation_id": conversation.id,
                "content": text,
            },
        )
    except Exception as e:
        logger.warning(f"WeChat channel workflow trigger failed: {e}")

    task = asyncio.create_task(
        _push_wechat_reply_in_background(
            channel_id=channel.id,
            customer_id=customer.id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            openid=openid,
            app_id=app_id,
            app_secret=app_secret,
        )
    )
    task.add_done_callback(_log_background_task_error)
    return True, ""


async def _welcome_for_customer(
    customer_id: str, db: AsyncSession
) -> str | None:
    if not customer_id:
        return None
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if customer and customer.welcome_message:
        return customer.welcome_message.strip()
    return None


async def _process_text_message(
    channel: Channel,
    customer_id: str,
    openid: str,
    text: str,
    db: AsyncSession,
    client_ip: str | None,
) -> str:
    if not customer_id:
        return (
            "公众号尚未绑定客服 Agent。请在 mchat 管理后台 → 频道管理 → "
            "编辑此微信公众号，选择「客服配置（Agent）」。"
        )

    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        return "绑定的客服配置不存在或已禁用，请联系管理员。"

    if customer.user_id != channel.user_id:
        return "客服配置与频道不属于同一账号，请重新绑定。"

    conversation = await channel_get_or_create_conversation(
        db,
        openid,
        customer,
        contact_info=wechat_contact_info(channel.id),
        title=f"WeChat: {customer.name}",
        client_ip=client_ip,
    )

    user_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=text,
    )
    db.add(user_message)
    await db.flush()

    # Persist user message first so timeout/rollback in AI stage won't lose inbound data.
    conversation.updated_at = datetime.now(timezone.utc)
    conversation.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    try:
        await channel_trigger_bound_workflows(
            db,
            channel,
            event_type="message",
            event_payload={
                "sender_id": openid,
                "conversation_id": conversation.id,
                "content": text,
            },
        )
    except Exception as e:
        logger.warning(f"WeChat channel workflow trigger failed: {e}")

    ai_config = await _resolve_ai_config(db, customer)

    if ai_config is None:
        return "未配置 AI 模型，请在管理后台设置默认模型或绑定客服 Agent 的模型。"

    async def _generate_ai_reply() -> str:
        full = ""
        async for token in process_message(
            conversation,
            user_message,
            ai_config,
            db,
            customer_config=customer,
        ):
            full += token
        return full

    full_response = ""
    try:
        full_response = await asyncio.wait_for(
            _generate_ai_reply(),
            timeout=_WECHAT_PASSIVE_REPLY_TIMEOUT_SECONDS,
        )
        await db.commit()
    except asyncio.TimeoutError:
        logger.warning(
            "WeChat reply timeout (>{}s): channel={} openid={}",
            _WECHAT_PASSIVE_REPLY_TIMEOUT_SECONDS,
            channel.id,
            openid,
        )
        await db.rollback()
        return _to_wechat_plain_text("消息已收到，正在处理中。请稍后再发“继续”获取回复。")
    except Exception as e:
        logger.error(f"WeChat AI reply failed: {e}", exc_info=True)
        await db.rollback()
        return _to_wechat_plain_text(f"处理消息时出错：{e}")

    reply = (full_response or "").strip()
    if not reply:
        reply = "抱歉，我暂时无法回复，请稍后再试。"
    return _to_wechat_plain_text(reply)
