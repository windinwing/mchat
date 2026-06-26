"""Playwright-client publisher — delegates to a remote browser-machine.

For platforms with no official publish API (Xiaohongshu, Douyin, WeChat
Channels) the work runs on an independent client process that owns a
persistent, real-IP browser profile. This publisher does NOT run a browser: it
enqueues a :class:`PublishJob` and waits for the client to claim + complete it.

The remote machine fully simulates human behavior with a durable login state;
the central side only orchestrates. See ``docs/plan/publish-system/ARCHITECTURE.md``
§3 (Pull-mode protocol).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.publish.base import BasePublisher, PublishRequest, PublishResult
from app.publish.client.dispatcher import (
    claim_job,
    enqueue_job,
    get_job_status,
)
from app.publish.client.protocol import build_job

#: How long to block on a client picking up + finishing the job (seconds).
_DEFAULT_TIMEOUT_SECONDS = 180

#: Polling interval while waiting for the client result (seconds).
_POLL_INTERVAL_SECONDS = 2.0


class PlaywrightClientPublisher(BasePublisher):
    provider_key = "playwright_client"
    capabilities = ("publish:text", "publish:image")

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("platform") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        platform = (config.get("platform") or "").strip().lower()
        client_id_hint = (config.get("client_id") or "").strip()
        timeout = _coerce_timeout(config.get("timeout_seconds"))

        media_payload = [
            {"type": m.type, "url": m.url, "path": m.path, "caption": m.caption}
            for m in request.media
        ]

        job = build_job(
            platform=platform,
            content=request.content,
            title=request.title,
            media=media_payload,
            extra=request.extra,
        )
        # ``request_id`` (if any) is folded into extra for client-side tracing.
        if request.request_id:
            job.extra.setdefault("request_id", request.request_id)

        await enqueue_job(job)
        logger.info(
            "playwright job queued id={} platform={} timeout={}s",
            job.job_id, platform, timeout,
        )

        # Mark which client the request prefers (informational; claim is first-come).
        _ = client_id_hint

        final = await _wait_for_result(job.job_id, timeout)
        if final is None:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="timeout",
                error_message=(
                    f"No Playwright client completed the job within {timeout}s "
                    f"(platform={platform})"
                ),
            )

        result = final.result or {}
        if final.status == "failed" or final.error:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="client_error",
                error_message=final.error or "client reported failure",
                raw=result,
            )

        return PublishResult(
            success=bool(result.get("success", True)),
            provider=self.provider_key,
            message=str(result.get("message") or "Delivered via client machine"),
            remote_id=result.get("remote_id"),
            remote_url=result.get("remote_url"),
            raw=result,
        )


async def _wait_for_result(job_id: str, timeout: float) -> Any:
    """Block (cooperatively) until the client completes the job or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        job = await get_job_status(job_id)
        if job is not None and job.status in ("done", "failed"):
            return job
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return None


def _coerce_timeout(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS
