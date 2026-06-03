"""Tests for Cloud Portal OpenClaw-style Markdown studio memory."""

from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.models.conversation import Conversation
from cloud.bot.studio_memory import register_cloud_chat_extensions
from cloud.config import cloud_settings
from cloud.services.studio_memory_service import (
    StudioMemoryService,
    execute_studio_memory_tool,
    format_studio_memory_section,
    is_studio_chat,
)

register_cloud_chat_extensions()


@pytest.fixture
def studio_root(tmp_path, monkeypatch):
    root = tmp_path / "tenants"
    monkeypatch.setattr(settings, "workspace_root_dir", str(root))
    monkeypatch.setattr(settings, "workspace_legacy_studio_dir", "")
    monkeypatch.setattr(cloud_settings, "studio_memory_enabled", True)
    return root


def test_workspace_isolation(studio_root):
    a = StudioMemoryService("user-a", "channel-1")
    b = StudioMemoryService("user-b", "channel-1")
    c = StudioMemoryService("user-a", "channel-2")

    a.write_memory_file("memory for user-a ch1", mode="replace")
    b.write_memory_file("memory for user-b ch1", mode="replace")
    c.write_memory_file("memory for user-a ch2", mode="replace")

    assert a.read_memory_file().strip() == "memory for user-a ch1"
    assert b.read_memory_file().strip() == "memory for user-b ch1"
    assert c.read_memory_file().strip() == "memory for user-a ch2"


def test_append_daily_turn(studio_root):
    service = StudioMemoryService("user-1", "ch-1")
    service.append_daily_turn("你好", "你好，有什么可以帮你？", conversation_id="conv-123")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = service.read_daily_file(today)
    assert "**User:**" in content
    assert "你好" in content
    assert "**Assistant:**" in content
    assert "conv-123"[:8] in content


def test_read_bootstrap_includes_memory_and_daily(studio_root):
    service = StudioMemoryService("user-1", "ch-1")
    service.write_memory_file("长期偏好：使用中文回复", mode="replace")
    service.append_daily_turn("task", "done")
    bootstrap = service.read_bootstrap()
    section = format_studio_memory_section(bootstrap)
    assert "长期偏好" in section
    assert "Recent daily notes" in section


def test_studio_memory_tools_write_and_search(studio_root):
    service = StudioMemoryService("user-1", "ch-1")
    write_result = execute_studio_memory_tool(
        service,
        "studio_memory_write",
        {"target": "memory", "content": "项目代号 Phoenix", "mode": "append"},
    )
    assert write_result.get("ok") is True

    daily_result = execute_studio_memory_tool(
        service,
        "studio_memory_write",
        {"target": "daily", "content": "今日完成检索 3 篇专利", "mode": "append"},
    )
    assert daily_result.get("ok") is True

    search_result = execute_studio_memory_tool(
        service,
        "studio_memory_search",
        {"query": "Phoenix", "top_k": 3},
    )
    assert search_result.get("ok") is True
    assert any("Phoenix" in (r.get("snippet") or "") for r in search_result.get("results", []))


def test_studio_memory_get_slice(studio_root):
    service = StudioMemoryService("user-1", "ch-1")
    service.write_memory_file("line1\nline2\nline3", mode="replace")
    result = execute_studio_memory_tool(
        service,
        "studio_memory_get",
        {"path": "MEMORY.md", "line_start": 2, "line_end": 2},
    )
    assert result.get("content") == "line2"


def test_is_studio_chat():
    assert is_studio_chat(Conversation(user_id="u1", customer_id="c1")) is True
    assert is_studio_chat(Conversation(user_id="u1", visitor_id="v1")) is False
    assert is_studio_chat(Conversation(visitor_id="v1")) is False


def test_append_session_reset(studio_root):
    service = StudioMemoryService("user-1", "ch-1")
    service.append_session_reset()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert "Session reset" in service.read_daily_file(today)


def test_invalid_workspace_segment_raises():
    with pytest.raises(ValueError):
        StudioMemoryService("../evil", "ch-1")
