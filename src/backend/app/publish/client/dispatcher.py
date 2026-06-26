"""Client-machine job dispatcher — in-process queue (P1 skeleton).

Pull-mode handoff: clients call :func:`claim_job` to lease one pending job,
execute it, then :func:`complete_job` to post the result. The central side
holds jobs in a process-local dict keyed by ``job_id``.

This is intentionally dependency-free for MVP (no new DB table, no Redis
requirement). The four public functions form a stable backend interface —
swapping in a Redis/DB-backed implementation later changes nothing for callers
(the skill surface, the publishers, the HTTP layer).

Caveat: in-process state does not survive restarts and is not shared across
multiple backend workers. That is acceptable for a single-machine MVP with one
Playwright client; a persistent backend is tracked as P2 work.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from app.publish.client.protocol import PublishJob

#: job_id -> PublishJob
_jobs: dict[str, PublishJob] = {}

#: Serialize mutations under the asyncio loop (cheap, contention-free here).
_lock = asyncio.Lock()

#: Drop jobs older than this (s) to bound memory growth.
_JOB_TTL_SECONDS = 24 * 3600


async def enqueue_job(job: PublishJob) -> str:
    """Register a job and return its id."""
    async with _lock:
        _gc_locked()
        _jobs[job.job_id] = job
        logger.info("publish job enqueued id={} platform={}", job.job_id, job.platform)
    return job.job_id


async def claim_job(platform: str, client_id: str) -> PublishJob | None:
    """Lease the oldest pending job for ``platform`` to ``client_id``.

    Returns ``None`` when no job is waiting.
    """
    platform = (platform or "").strip().lower()
    async with _lock:
        _gc_locked()
        for job in _jobs.values():
            if job.platform == platform and job.status == "pending":
                job.status = "claimed"
                job.client_id = client_id
                job.updated_at = time.time()
                logger.info(
                    "publish job claimed id={} platform={} client={}",
                    job.job_id, job.platform, client_id,
                )
                return job
    return None


async def complete_job(
    job_id: str, *, result: dict[str, Any] | None = None, error: str | None = None
) -> PublishJob | None:
    """Mark a claimed job done with ``result`` or ``error``."""
    async with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        job.status = "failed" if error else "done"
        job.result = result
        job.error = error
        job.updated_at = time.time()
        logger.info(
            "publish job completed id={} status={}", job.job_id, job.status
        )
        return job


async def get_job_status(job_id: str) -> PublishJob | None:
    """Look up a job by id (for polling result by the publisher)."""
    async with _lock:
        return _jobs.get(job_id)


def _gc_locked() -> None:
    """Evict terminal jobs older than TTL. Caller holds ``_lock``."""
    cutoff = time.time() - _JOB_TTL_SECONDS
    stale = [jid for jid, job in _jobs.items() if job.status in ("done", "failed") and job.updated_at < cutoff]
    for jid in stale:
        _jobs.pop(jid, None)
