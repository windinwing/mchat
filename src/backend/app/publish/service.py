"""Publish service — single entry point for the publish-content skill.

The skill layer talks to ``dispatch(...)`` only; it never imports a concrete
publisher. This keeps the seam between platform core and the publish module to
exactly one function.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.publish.base import PublishRequest, PublishResult
from app.publish.registry import get_publisher


def _request_from_payload(payload: dict[str, Any]) -> PublishRequest:
    """Build a :class:`PublishRequest` from a skill payload dict.

    Defensive: media items may arrive as dicts; coerce into PublishMedia so
    publishers can rely on typed access.
    """
    from app.publish.base import PublishMedia

    media_raw = payload.get("media") or []
    media: list[PublishMedia] = []
    if isinstance(media_raw, list):
        for item in media_raw:
            if isinstance(item, PublishMedia):
                media.append(item)
            elif isinstance(item, dict):
                media.append(
                    PublishMedia(
                        type=str(item.get("type") or "image"),
                        url=item.get("url"),
                        path=item.get("path"),
                        caption=item.get("caption"),
                    )
                )

    return PublishRequest(
        content=str(payload.get("content") or ""),
        title=payload.get("title"),
        media=media,
        extra=payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
        request_id=str(payload.get("request_id") or ""),
    )


async def _load_channel_config(channel_id: str) -> dict[str, Any] | None:
    """Load a Channel's decrypted config for publish dispatch.

    Uses a SYNCHRONOUS engine (run in a thread) to avoid the cross-loop issue:
    the global async engine binds to the loop it was created on, and a workflow
    background task may run on a different loop reference, causing
    "Future attached to a different loop". The sync path (pymysql) is loop-free
    and safe from any coroutine.
    """
    import os

    from app.workspace.context import get_workspace_context

    ctx = get_workspace_context()
    user_id = str(ctx.user_id) if ctx and getattr(ctx, "user_id", None) else ""
    if not user_id:
        user_id = (os.environ.get("MCHAT_USER_ID") or "").strip()
    if not user_id:
        return None

    return await asyncio.to_thread(_sync_load_channel_config, channel_id, user_id)


def _sync_load_channel_config(channel_id: str, user_id: str) -> dict[str, Any] | None:
    """Sync DB lookup of a channel's decrypted config (loop-free)."""
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from app.models.channel import Channel
        from app.services.channel_service import _decrypt_config
        from app.core.config import settings

        url = settings.database_url
        url = url.replace("+aiomysql", "+pymysql").replace("+asyncmy", "+pymysql")
        engine = create_engine(url, pool_pre_ping=True, future=True)
        try:
            with Session(engine) as session:
                row = session.scalars(
                    select(Channel).where(
                        Channel.id == channel_id, Channel.user_id == user_id
                    )
                ).first()
                if row is None:
                    return None
                session.expunge_all()
                return _decrypt_config(row.config)
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync channel config load failed for {}: {}", channel_id, exc)
        return None


async def dispatch(payload: dict[str, Any]) -> PublishResult:
    """Resolve a publisher from ``payload`` and execute the publish.

    Expected payload keys:
        - ``provider``: publisher key (e.g. ``"feishu"``).
        - ``channel_config``: credentials/options for this channel.
        - ``content`` / ``title`` / ``media`` / ``extra`` / ``request_id``.

    Returns a :class:`PublishResult` (never raises to the caller — failures are
    encoded in the result so workflow runs record them cleanly).
    """
    provider_key = str(payload.get("provider") or "").strip().lower()
    if not provider_key:
        return PublishResult(
            success=False,
            provider="",
            error_code="missing_provider",
            error_message="payload.provider is required",
        )

    # Bridge to the Channel table: if payload references a stored channel by id,
    # load its (decrypted) config and use it as channel_config. This lets a
    # workflow node say {provider, channel_id} instead of hard-coding secrets.
    # An explicit channel_config in the payload still wins per-key (merge).
    config: dict[str, Any] = {}
    channel_id = str(payload.get("channel_id") or "").strip()
    if channel_id:
        db_config = await _load_channel_config(channel_id)
        if db_config is not None:
            config = dict(db_config)
    payload_config = payload.get("channel_config")
    if isinstance(payload_config, dict):
        config.update(payload_config)

    content = str(payload.get("content") or "").strip()
    if not content and not (payload.get("media")):
        return PublishResult(
            success=False,
            provider=provider_key,
            error_code="empty_payload",
            error_message="content (or media) is required to publish",
        )

    request = _request_from_payload(payload)

    try:
        publisher = get_publisher(provider_key)
    except ValueError as exc:
        logger.warning("publish dispatch rejected: {}", exc)
        return PublishResult(
            success=False,
            provider=provider_key,
            error_code="unknown_provider",
            error_message=str(exc),
        )

    if not await publisher.validate_config(config):
        return PublishResult(
            success=False,
            provider=provider_key,
            error_code="invalid_config",
            error_message=f"channel_config for provider '{provider_key}' is incomplete",
        )

    # Draft mode: save the content as a pending draft WITHOUT actually sending.
    # The user reviews it later via /drafts and approves to send for real.
    if payload.get("draft"):
        await _save_draft(payload, provider_key, channel_id, request)
        return PublishResult(
            success=True,
            provider=provider_key,
            message="内容已存为待选草稿，等待审批后发送",
        )

    try:
        result = await publisher.publish(config, request)
        logger.info(
            "publish dispatch provider={} success={} remote_id={}",
            provider_key, result.success, result.remote_id,
        )
    except Exception as exc:  # noqa: BLE001 — encode into result, never raise
        logger.exception("publish dispatch failed provider={}: {}", provider_key, exc)
        result = PublishResult(
            success=False,
            provider=provider_key,
            error_code="publisher_error",
            error_message=str(exc),
        )
    # Persist a send record (fire-and-forget on a worker thread so it never
    # blocks the dispatch return or breaks on DB issues).
    await _record_publish(payload, provider_key, channel_id, request, result)
    return result


async def _save_draft(
    payload: dict[str, Any],
    provider: str,
    channel_id: str,
    request: PublishRequest,
) -> None:
    """Write a pending draft (status=pending) to publish_records — not sent yet."""
    try:
        await asyncio.to_thread(
            _sync_save_draft, payload, provider, channel_id, request
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft save failed: {}", exc)


def _sync_save_draft(
    payload: dict[str, Any],
    provider: str,
    channel_id: str,
    request: PublishRequest,
) -> None:
    import os
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.publish_record import PublishRecord

    user_id = os.environ.get("MCHAT_USER_ID", "")
    if not user_id:
        from app.workspace.context import get_workspace_context
        ctx = get_workspace_context()
        user_id = str(ctx.user_id) if ctx and getattr(ctx, "user_id", None) else ""
    if not user_id:
        return

    url = settings.database_url.replace("+aiomysql", "+pymysql").replace("+asyncmy", "+pymysql")
    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        record = PublishRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            channel_id=channel_id or None,
            provider=provider,
            title=(request.title or "")[:200] or None,
            content_preview=(request.content or "")[:200] or None,
            success=False,
            status="pending",
            media_type="video" if any(m.type == "video" for m in request.media) else ("image" if request.media else "text"),
        )
        with Session(engine) as session:
            session.add(record)
            session.commit()
    finally:
        engine.dispose()


async def _record_publish(
    payload: dict[str, Any],
    provider: str,
    channel_id: str,
    request: PublishRequest,
    result: PublishResult,
) -> None:
    """Write a PublishRecord row (sync engine on a thread — loop-free)."""
    try:
        await asyncio.to_thread(
            _sync_record_publish, payload, provider, channel_id, request, result
        )
    except Exception as exc:  # noqa: BLE001 — recording must never break dispatch
        logger.warning("publish record write failed: {}", exc)


def _sync_record_publish(
    payload: dict[str, Any],
    provider: str,
    channel_id: str,
    request: PublishRequest,
    result: PublishResult,
) -> None:
    """Insert a PublishRecord using a short-lived sync engine."""
    import os
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.models.publish_record import PublishRecord

    user_id = os.environ.get("MCHAT_USER_ID", "")
    if not user_id:
        from app.workspace.context import get_workspace_context

        ctx = get_workspace_context()
        user_id = str(ctx.user_id) if ctx and getattr(ctx, "user_id", None) else ""
    if not user_id:
        return  # can't attribute the record without a user

    url = settings.database_url.replace("+aiomysql", "+pymysql").replace("+asyncmy", "+pymysql")
    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        content = (request.content or "")[:200]
        title = (request.title or payload.get("title") or "")[:200]
        record = PublishRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            channel_id=channel_id or None,
            provider=provider,
            workflow_run_id=str(payload.get("request_id") or "")[:36] or None,
            workflow_name=None,
            title=title or None,
            content_preview=content or None,
            success=bool(result.success),
            remote_url=result.remote_url,
            remote_id=result.remote_id,
            error_message=result.error_message,
            error_code=result.error_code,
            status="sent",
            media_type="video" if any(m.type == "video" for m in request.media) else ("image" if request.media else "text"),
            sent_at=datetime.now(timezone.utc) if result.success else None,
        )
        with Session(engine) as session:
            session.add(record)
            session.commit()
    finally:
        engine.dispose()
