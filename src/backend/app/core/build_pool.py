"""Background worker pool for DevBridge build jobs.

Consumes jobs from the Redis build queue (``mchat:build:queue``) and runs them
via :func:`execute_queued_build_job`. Each build is a blocking ``subprocess.run``
(Cocos Creator compilation), so jobs run in a :class:`ThreadPoolExecutor` whose
size is controlled by ``GAMECENTER_BUILD_WORKER_POOL_SIZE`` (default 5).

A single dispatcher thread does ``brpop`` on the queue (5 s timeout) and submits
each job to the pool. The whole thing is started in ``lifespan`` and stopped on
shutdown.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from loguru import logger

from app.core.config import settings
from app.services.build_queue_service import blocking_pop_build_job, queue_enabled
from app.services.build_worker_runner import execute_queued_build_job

_pool: Optional[ThreadPoolExecutor] = None
_dispatcher_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None


def _dispatch_loop() -> None:
    """Pop build jobs from Redis and submit them to the thread pool."""
    import sys

    logger.info("Build worker dispatcher started (pool_size={})", _pool_size())
    poll_count = 0
    while _stop_event is not None and not _stop_event.is_set():
        poll_count += 1
        try:
            job = blocking_pop_build_job(timeout_seconds=5)
        except Exception as exc:
            # Log every poll failure; Redis hiccups are recoverable but silent.
            logger.error("Build queue poll failed (poll #{}): {}", poll_count, exc)
            print("Build queue poll failed: {}".format(exc), file=sys.stderr, flush=True)
            if _stop_event is not None and not _stop_event.is_set():
                _stop_event.wait(5)
            continue
        if job is None:
            continue
        slug = job.get("slug")
        build_id = job.get("build_id")
        logger.info("Build worker picked up slug={} build_id={}", slug, build_id)
        print("Build worker picked up slug={} build_id={}".format(slug, build_id), file=sys.stderr, flush=True)
        if _pool is None:
            logger.warning("Build pool not initialised, dropping job {}", build_id)
            break
        logger.info("Build worker picked up slug={} build_id={}", slug, build_id)
        _pool.submit(_run_job_safely, job)
    logger.info("Build worker dispatcher stopped")


def _run_job_safely(job: dict) -> None:
    """Execute a build job, logging any error (never raise in the pool)."""
    import sys

    slug = job.get("slug")
    build_id = job.get("build_id")
    logger.info("Build job starting slug={} build_id={}", slug, build_id)
    print("Build job starting slug={} build_id={}".format(slug, build_id), file=sys.stderr, flush=True)
    try:
        result = execute_queued_build_job(job)
        ok = result.get("ok", False)
        level = logger.info if ok else logger.warning
        level("Build job done slug={} build_id={} ok={}", slug, build_id, ok)
        print("Build job done slug={} ok={} error={}".format(slug, ok, result.get("error")), file=sys.stderr, flush=True)
        if not ok:
            logger.warning("Build error detail: {}", result.get("error"))
    except Exception:
        logger.exception("Build job crashed slug={} build_id={}", slug, build_id)


def _pool_size() -> int:
    raw = int(getattr(settings, "gamecenter_build_worker_pool_size", 5) or 5)
    return max(1, min(raw, 32))


def start_build_pool() -> None:
    """Start the dispatcher thread + worker pool (called from lifespan)."""
    global _pool, _dispatcher_thread, _stop_event

    if not queue_enabled():
        logger.info("Build queue disabled, build worker not started")
        return

    if _pool is not None:
        return  # already started

    size = _pool_size()
    _pool = ThreadPoolExecutor(max_workers=size, thread_name_prefix="build-worker")
    _stop_event = threading.Event()
    _dispatcher_thread = threading.Thread(
        target=_dispatch_loop, name="build-dispatcher", daemon=True
    )
    _dispatcher_thread.start()
    logger.info("Build worker pool started ({} workers)", size)


def stop_build_pool() -> None:
    """Signal the dispatcher to stop and shut down the pool."""
    global _pool, _dispatcher_thread, _stop_event

    if _stop_event is not None:
        _stop_event.set()
    if _dispatcher_thread is not None:
        _dispatcher_thread.join(timeout=10)
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
    _pool = None
    _dispatcher_thread = None
    _stop_event = None
    logger.info("Build worker pool stopped")
