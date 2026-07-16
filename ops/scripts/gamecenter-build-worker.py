#!/usr/bin/env python3
"""DevBridge build worker pool — concurrent compile jobs off the API process.

Usage (on MChat server):
  /opt/xiaoxiao/mchat/src/backend/venv/bin/python \\
    /opt/xiaoxiao/mchat/ops/scripts/gamecenter-build-worker.py

Pool size: GAMECENTER_BUILD_WORKER_POOL_SIZE (default 5). Each slot consumes the
shared Redis queue independently; one stuck compile does not block the others.

Environment: reads /opt/xiaoxiao/mchat/.env via app.core.config (WorkingDirectory=src/backend).
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from loguru import logger  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.build_queue_service import blocking_pop_build_job  # noqa: E402
from app.services.build_worker_runner import execute_queued_build_job  # noqa: E402


def _pool_size() -> int:
    raw = int(getattr(settings, "gamecenter_build_worker_pool_size", 5) or 5)
    return max(1, min(raw, 32))


# ── Singleton lock ────────────────────────────────────────────────
# The build worker consumes a shared Redis queue. If two worker pools ever run
# at once (e.g. a manual `nohup` launch alongside the systemd service, or a
# stale process left by a deploy), they race on the same jobs — wasted CPU and
# duplicate compiles. This lock guarantees only one pool runs at a time.

LOCK_KEY = "mchat:build:worker:lock"
LOCK_TTL = 30  # seconds; refreshed every ~10s while alive


def _lock_token() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


def _acquire_lock() -> bool:
    """Try to grab the singleton lock. Returns False if another pool holds it."""
    import redis

    client = redis.from_url(settings.redis_url, decode_responses=True)
    return bool(client.set(LOCK_KEY, _lock_token(), nx=True, ex=LOCK_TTL))


def _refresh_lock(stop: threading.Event) -> None:
    """Background thread: keep the lock alive while the pool is running."""
    import redis

    client = redis.from_url(settings.redis_url, decode_responses=True)
    token = _lock_token()
    while not stop.wait(LOCK_TTL // 3 or 1):
        try:
            # Only refresh if we still own it (token matches).
            lua = (
                "if redis.call('get', KEYS[1]) == ARGV[1] "
                "then return redis.call('expire', KEYS[1], ARGV[2]) "
                "else return 0 end"
            )
            client.eval(lua, 1, LOCK_KEY, token, str(LOCK_TTL))
        except Exception as exc:
            logger.warning("Build worker lock refresh failed: {}", exc)


def _release_lock() -> None:
    """Release the lock on shutdown (only if we still own it)."""
    import redis

    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        token = _lock_token()
        lua = (
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end"
        )
        client.eval(lua, 1, LOCK_KEY, token)
    except Exception:
        pass


def _worker_loop(worker_id: int, stop: threading.Event) -> None:
    logger.info("Build worker slot {} started", worker_id)
    while not stop.is_set():
        try:
            job = blocking_pop_build_job(timeout_seconds=10)
            if not job:
                continue
            slug = job.get("slug") or "?"
            build_id = job.get("build_id") or "?"
            logger.info(
                "Worker slot {} processing slug={} build_id={}",
                worker_id,
                slug,
                build_id,
            )
            execute_queued_build_job(job)
        except Exception as exc:
            if stop.is_set():
                break
            logger.exception("Worker slot {} error: {}", worker_id, exc)
            time.sleep(2)
    logger.info("Build worker slot {} stopped", worker_id)


def main() -> int:
    # Guarantee only one worker pool runs at a time. If another instance (manual
    # launch or a stale deploy process) already holds the lock, exit cleanly so
    # the existing pool keeps the queue — no duplicate compiles.
    if not _acquire_lock():
        logger.warning(
            "Another build worker pool is already running (lock {} held). "
            "Exiting to avoid duplicate queue consumption.",
            LOCK_KEY,
        )
        return 0

    pool = _pool_size()
    stop = threading.Event()
    threads: list[threading.Thread] = []
    logger.info("Build worker pool started (size={})", pool)

    # Keep the singleton lock alive while running.
    lock_thread = threading.Thread(
        target=_refresh_lock, args=(stop,), name="build-worker-lock", daemon=True
    )
    lock_thread.start()

    for slot in range(1, pool + 1):
        thread = threading.Thread(
            target=_worker_loop,
            args=(slot, stop),
            name=f"build-worker-{slot}",
            daemon=False,
        )
        thread.start()
        threads.append(thread)
    try:
        while True:
            time.sleep(1)
            if not any(thread.is_alive() for thread in threads):
                logger.error("All build worker slots exited unexpectedly")
                return 1
    except KeyboardInterrupt:
        logger.info("Build worker pool stopping…")
        stop.set()
        for thread in threads:
            thread.join(timeout=30)
        return 0
    finally:
        stop.set()
        _release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
