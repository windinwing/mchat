"""Tests for bot engine helpers and process_message entry paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.engine import _tool_result_display_text, process_message


def test_tool_result_display_text_string():
    assert _tool_result_display_text("hello") == "hello\n\n"


def test_tool_result_display_text_error_dict():
    text = _tool_result_display_text({"error": "boom", "hint": "try again"})
    assert "❌ boom" in text
    assert "try again" in text


def test_tool_result_display_text_outbound_assets():
    text = _tool_result_display_text(
        {
            "outbound_assets": [
                {"name": "report.pdf", "url": "/uploads/chat/x.pdf"},
            ]
        }
    )
    assert "report.pdf" in text
    assert "/uploads/chat/x.pdf" in text


@pytest.mark.asyncio
async def test_process_message_no_ai_config(db_session):
    conversation = SimpleNamespace(
        id="conv-1",
        contact_info=None,
        scope_type="personal",
        scope_id=None,
    )
    message = SimpleNamespace(
        id="msg-1",
        content="hi",
        extra_data=None,
        conversation_id="conv-1",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db_session.execute = AsyncMock(return_value=mock_result)

    chunks = []
    async for token in process_message(
        conversation=conversation,
        message=message,
        ai_config=None,
        db_session=db_session,
        customer_config=None,
    ):
        chunks.append(token)

    assert chunks
    assert "No AI configuration" in chunks[0]


@pytest.mark.asyncio
async def test_process_message_missing_api_key(db_session):
    conversation = SimpleNamespace(
        id="conv-1",
        contact_info=None,
        scope_type="personal",
        scope_id=None,
    )
    message = SimpleNamespace(
        id="msg-1",
        content="hello",
        extra_data=None,
        conversation_id="conv-1",
    )
    ai_config = SimpleNamespace(
        id="cfg-1",
        user_id="user-1",
        provider="openai",
        model="gpt-4o-mini",
        api_key="",
        system_prompt="You are helpful.",
        is_default=True,
    )

    with patch(
        "app.services.llm_credentials.ensure_ai_config_api_key",
        new_callable=AsyncMock,
        return_value=ai_config,
    ), patch("app.services.llm_credentials.is_usable_api_key", return_value=False):
        chunks = []
        async for token in process_message(
            conversation=conversation,
            message=message,
            ai_config=ai_config,
            db_session=db_session,
        ):
            chunks.append(token)

    assert chunks
    assert "API 密钥" in chunks[0]
