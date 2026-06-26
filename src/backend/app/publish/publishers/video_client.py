"""Video-client publisher — delegates video generation to a remote client machine.

Same pull-mode protocol as PlaywrightClientPublisher but for video generation:
the job carries a prompt + generation params, the client machine (running
ComfyUI / a third-party API / browser automation) claims it, generates the
video, uploads the file to the center, and posts back the video URL.

Key difference from playwright_client: much longer timeout (video generation
takes minutes), and the result's remote_url is a downloadable video URL.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.publish.base import BasePublisher, PublishRequest, PublishResult
from app.publish.client.dispatcher import (
    enqueue_job,
    get_job_status,
)
from app.publish.client.protocol import build_job

#: Video generation can take 10+ minutes; give generous headroom.
_DEFAULT_TIMEOUT_SECONDS = 1800  # 30 min

_POLL_INTERVAL_SECONDS = 5.0  # less aggressive polling for long jobs


class VideoClientPublisher(BasePublisher):
    provider_key = "video_client"
    capabilities = ("publish:video", "generate:video")

    async def validate_config(self, config: dict[str, Any]) -> bool:
        # platform identifies the engine: "video:comfyui" / "video:kling" / ...
        return bool((config.get("platform") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        platform = (config.get("platform") or "").strip().lower()
        timeout = _coerce_timeout(config.get("timeout_seconds"))

        # Build job — content is the video prompt, extra carries gen params.
        extra: dict[str, Any] = {
            "job_type": "generate_video",
            "reference_urls": [m.url for m in request.media if m.url],
            "duration": config.get("duration"),
            "resolution": config.get("resolution"),
            "engine_params": config.get("engine_params"),
        }
        if request.request_id:
            extra["request_id"] = request.request_id

        job = build_job(
            platform=platform,
            content=request.content,
            title=request.title,
            media=[{"type": m.type, "url": m.url, "path": m.path} for m in request.media],
            extra=extra,
        )
        await enqueue_job(job)
        logger.info("video job queued id={} platform={} timeout={}s", job.job_id, platform, timeout)

        final = await _wait_for_result(job.job_id, timeout)
        if final is None:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="timeout",
                error_message=f"No video client completed the job within {timeout}s (platform={platform})",
            )

        result = final.result or {}
        if final.status == "failed" or final.error:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="client_error",
                error_message=final.error or "video client reported failure",
                raw=result,
            )

        video_url = result.get("remote_url") or result.get("video_url")
        return PublishResult(
            success=bool(result.get("success", video_url is not None)),
            provider=self.provider_key,
            message=str(result.get("message") or "Video generated"),
            remote_url=video_url,
            raw=result,
        )


async def _wait_for_result(job_id: str, timeout: float) -> Any:
    import asyncio

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
