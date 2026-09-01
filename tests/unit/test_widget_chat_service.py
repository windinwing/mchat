from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from starlette.requests import Request

from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.services.widget_chat_service import (
    _can_resume_widget_conversation,
    prepare_widget_chat,
    widget_contact_info,
)
from app.utils.chat_upload import validate_chat_attachment


def _request() -> Request:
    return Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/api/widget/test/chat',
            'headers': [],
            'client': ('127.0.0.1', 12345),
            'scheme': 'http',
            'server': ('testserver', 80),
        }
    )


@pytest.mark.asyncio
async def test_prepare_widget_chat_updates_existing_conversation_timestamps(db_session):
    customer = CustomerConfig(name='Support', user_id='user-1', enabled=True)
    db_session.add(customer)
    await db_session.flush()

    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    conversation = Conversation(
        visitor_id='visitor-1',
        contact_info=widget_contact_info(customer.id),
        title=f'Widget: {customer.name}',
        status='active',
        updated_at=old_time,
        last_seen_at=old_time,
    )
    db_session.add(conversation)
    await db_session.flush()

    ctx = await prepare_widget_chat(
        db_session,
        customer.id,
        'hello',
        conversation.id,
        _request(),
        visitor_token='visitor-1',
    )

    assert ctx.conversation.id == conversation.id
    assert ctx.conversation.updated_at > old_time
    assert ctx.conversation.last_seen_at > old_time


def test_validate_chat_attachment_allows_common_video_types():
    validate_chat_attachment('demo.mp4', 'video/mp4', 1024)
    validate_chat_attachment('demo.webm', 'video/webm', 1024)


@pytest.mark.parametrize(
    "conversation",
    [
        Conversation(
            user_id="victim",
            visitor_id=None,
            customer_id="customer-1",
            status="active",
        ),
        Conversation(
            user_id=None,
            visitor_id=None,
            customer_id="customer-1",
            status="active",
        ),
        Conversation(
            user_id=None,
            visitor_id="real-token",
            customer_id="customer-1",
            status="active",
        ),
    ],
)
def test_widget_cannot_resume_nonvisitor_or_wrong_token_conversation(conversation):
    customer = CustomerConfig(
        id="customer-1",
        name="Support",
        user_id="owner",
        enabled=True,
    )

    assert not _can_resume_widget_conversation(
        conversation,
        customer.id,
        customer,
        "attacker-token",
    )
