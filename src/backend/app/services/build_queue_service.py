"""Redis-backed build job queue for DevBridge providers (GameCenter, etc.)."""

from __future__ import annotations

import json
from typing import Any

import redis
from loguru import logger

from app.core.config import settings

QUEUE_KEY = "mchat:build:queue"


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def queue_enabled() -> bool:
    return bool(getattr(settings, "gamecenter_build_queue_enabled", True))


def enqueue_build_job(job: dict[str, Any]) -> None:
    """Push a prepared build job (metadata.json should already exist as queued)."""
    payload = json.dumps(job, ensure_ascii=False)
    client = _redis_client()
    client.lpush(QUEUE_KEY, payload)
    logger.info(
        "Build job enqueued slug={} build_id={} provider={}",
        job.get("slug"),
        job.get("build_id"),
        job.get("provider_key"),
    )


def blocking_pop_build_job(timeout_seconds: int = 5) -> dict[str, Any] | None:
    """Worker: block until a job is available."""
    client = _redis_client()
    item = client.brpop(QUEUE_KEY, timeout=max(timeout_seconds, 1))
    if not item:
        return None
    _, raw = item
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Invalid build job payload: {}", exc)
        return None
    if not isinstance(data, dict):
        logger.error("Build job payload must be a JSON object")
        return None
    return data


def queue_depth() -> int:
    try:
        return int(_redis_client().llen(QUEUE_KEY))
    except Exception:
        return 0


def worker_pool_size() -> int:
    raw = int(getattr(settings, "gamecenter_build_worker_pool_size", 5) or 5)
    return max(1, min(raw, 32))
