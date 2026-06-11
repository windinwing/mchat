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
    pool = _pool_size()
    stop = threading.Event()
    threads: list[threading.Thread] = []
    logger.info("Build worker pool started (size={})", pool)
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


if __name__ == "__main__":
    raise SystemExit(main())
