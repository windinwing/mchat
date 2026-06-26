"""Image-client publisher — delegates image generation to a remote client machine.

Same pull-mode protocol as video_client but for image generation. The job
carries a prompt + generation params, the client machine (ComfyUI / SD / API)
claims it, generates the image, uploads the file to the center, and posts
back the image URL.

Shorter timeout than video (images are faster to generate).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.publish.base import BasePublisher, PublishRequest, PublishResult
from app.publish.client.dispatcher import enqueue_job, get_job_status
from app.publish.client.protocol import build_job

_DEFAULT_TIMEOUT_SECONDS = 600  # 10 min
_POLL_INTERVAL_SECONDS = 3.0


class ImageClientPublisher(BasePublisher):
    provider_key = "image_client"
    capabilities = ("publish:image", "generate:image")

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("platform") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        platform = (config.get("platform") or "").strip().lower()
        timeout = _coerce_timeout(config.get("timeout_seconds"))

        extra: dict[str, Any] = {
            "job_type": "generate_image",
            "reference_urls": [m.url for m in request.media if m.url],
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
        logger.info("image job queued id={} platform={} timeout={}s", job.job_id, platform, timeout)

        import asyncio
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        final = None
        while loop.time() < deadline:
            j = await get_job_status(job.job_id)
            if j is not None and j.status in ("done", "failed"):
                final = j
                break
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

        if final is None:
            return PublishResult(
                success=False, provider=self.provider_key, error_code="timeout",
                error_message=f"No image client completed within {timeout}s (platform={platform})",
            )
        result = final.result or {}
        if final.status == "failed" or final.error:
            return PublishResult(
                success=False, provider=self.provider_key, error_code="client_error",
                error_message=final.error or "image client reported failure", raw=result,
            )
        image_url = result.get("remote_url") or result.get("image_url")
        return PublishResult(
            success=bool(result.get("success", image_url is not None)),
            provider=self.provider_key,
            message=str(result.get("message") or "Image generated"),
            remote_url=image_url, raw=result,
        )


def _coerce_timeout(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS
