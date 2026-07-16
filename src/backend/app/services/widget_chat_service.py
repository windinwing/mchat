"""Shared widget chat preparation and streaming helpers."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.customer import CustomerConfig
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.maintenance_gate import ensure_public_api_available
from app.services.subscription_gate import ensure_channel_subscription_active
from app.utils.request import extract_client_ip
from app.utils.domain import is_domain_allowed

WIDGET_CUSTOMER_PREFIX = "widget_customer:"


def widget_contact_info(customer_id: str) -> str:
    return f"{WIDGET_CUSTOMER_PREFIX}{customer_id}"


def ensure_widget_domain_allowed(customer: CustomerConfig, request: Request) -> None:
    ensure_public_api_available()
    if not is_domain_allowed(
        customer.domains,
        request.headers.get("origin"),
        request.headers.get("referer"),
    ):
        raise HTTPException(
            status_code=403,
            detail="This domain is not allowed to use this widget",
        )


def _session_expired(conversation: Conversation, ttl_hours: int) -> bool:
    """True when widget conversation exceeded configured idle TTL."""
    if ttl_hours <= 0:
        return False
    last = conversation.last_seen_at or conversation.updated_at
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - last).total_seconds() > ttl_hours * 3600


def _visitor_matches(conversation: Conversation, visitor_token: str | None) -> bool:
    if not visitor_token:
        return False
    if not conversation.visitor_id:
        return True
    return conversation.visitor_id == visitor_token


def _can_resume_widget_conversation(
    conversation: Conversation | None,
    customer_id: str,
    customer: CustomerConfig,
    visitor_token: str | None,
) -> bool:
    if conversation is None:
        return False
    if conversation.status != "active":
        return False
    if not _visitor_matches(conversation, visitor_token):
        return False
    ttl = getattr(customer, "widget_session_ttl_hours", 24) or 24
    if _session_expired(conversation, ttl):
        return False
    if conversation.customer_id == customer_id:
        return True
    if conversation.contact_info == widget_contact_info(customer_id):
        return True
    return False


@dataclass
class WidgetChatContext:
    customer: CustomerConfig
    conversation: Conversation
    user_message: Message
    ai_config: AIConfig | None


async def prepare_widget_chat(
    db: AsyncSession,
    customer_id: str,
    message_text: str,
    conversation_id: str | None,
    request: Request,
    visitor_token: str | None = None,
    extra_data: dict | None = None,
) -> WidgetChatContext:
    result = await db.execute(
        select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found or disabled")

    ensure_channel_subscription_active(customer)
    ensure_widget_domain_allowed(customer, request)

    conversation: Conversation | None = None
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not _can_resume_widget_conversation(
            conversation, customer_id, customer, visitor_token
        ):
            conversation = None

    if conversation is None:
        vid = (visitor_token or "").strip() or f"visitor_{uuid.uuid4().hex[:12]}"
        conversation = Conversation(
            id=str(uuid.uuid4()),
            visitor_id=vid,
            customer_id=customer_id,
            client_ip=extract_client_ip(request),
            ai_config_id=customer.ai_config_id,
            title=f"Widget: {customer.name}",
            contact_info=widget_contact_info(customer_id),
            status="active",
        )
        db.add(conversation)
        await db.flush()
    elif not conversation.contact_info:
        conversation.contact_info = widget_contact_info(customer_id)

    user_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=message_text,
        extra_data=extra_data,
    )
    db.add(user_message)
    await db.flush()

    now = datetime.now(timezone.utc)
    conversation.updated_at = now
    conversation.last_seen_at = now

    ai_config = None
    if customer.ai_config_id:
        result = await db.execute(
            select(AIConfig).where(AIConfig.id == customer.ai_config_id)
        )
        ai_config = result.scalar_one_or_none()

    if ai_config is None:
        result = await db.execute(
            select(AIConfig)
            .where(AIConfig.is_default == True)
            .order_by(AIConfig.updated_at.desc())
            .limit(1)
        )
        ai_config = result.scalars().first()

    return WidgetChatContext(
        customer=customer,
        conversation=conversation,
        user_message=user_message,
        ai_config=ai_config,
    )


async def resolve_assistant_message(
    db: AsyncSession, conversation_id: str
) -> Message | None:
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def sse_line(event_type: str, payload: dict) -> str:
    data = {"type": event_type, **payload}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
