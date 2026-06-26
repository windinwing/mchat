"""skill 执行专用线程池。

与 uploads/search/embeddings 等共用的默认 ThreadPoolExecutor 隔离，
避免长跑 skill（如 stock-analysis 的网络 IO）占满默认池导致其他功能阻塞。

由 main.py 的 lifespan 在启动时创建、关闭时销毁。
executor.py 通过 get_skills_pool() 取用，用 loop.run_in_executor() 提交。
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from loguru import logger

_pool: Optional[ThreadPoolExecutor] = None
# 默认 16，可通过 SKILLS_POOL_SIZE 环境变量调整
_DEFAULT_SIZE = max(4, int(os.environ.get("SKILLS_POOL_SIZE", "16") or 16))


def start_skills_pool(max_workers: int = _DEFAULT_SIZE) -> ThreadPoolExecutor:
    """启动专用线程池（lifespan startup 调用）。重复调用安全。"""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="skill-exec",
        )
    return _pool


def get_skills_pool() -> ThreadPoolExecutor:
    """取专用池。未显式启动时惰性创建一个默认大小的。"""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(
            max_workers=_DEFAULT_SIZE,
            thread_name_prefix="skill-exec",
        )
    return _pool


def stop_skills_pool() -> None:
    """关闭专用线程池（lifespan shutdown 调用）。"""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def pool_stats() -> dict[str, int]:
    """Return a snapshot of the skills pool for monitoring / diagnostics.

    Keys: ``max_workers``, ``active`` (running + queued futures), ``headroom``
    (free slots). When the pool is saturated (``headroom == 0``) skill
    submissions queue silently — this snapshot surfaces that condition so
    operators can tell hung skills apart from a full pool.
    """
    if _pool is None:
        return {"max_workers": 0, "active": 0, "headroom": 0, "queued": 0}
    # ThreadPoolExecutor exposes no direct running count; _work_queue holds the
    # not-yet-started backlog, and active workers ≈ submitted − queued.
    max_workers = _pool._max_workers  # noqa: SLF001 — stdlib private, stable across CPython
    queue_size = 0
    try:
        queue_size = _pool._work_queue.qsize()  # noqa: SLF001
    except Exception:
        pass
    # ``_threads`` is the set of worker thread objects ever started; combined
    # with the work queue we approximate in-flight work.
    active_workers = min(len(getattr(_pool, "_threads", [])), max_workers)
    active = active_workers + queue_size
    headroom = max(0, max_workers - active)
    return {
        "max_workers": max_workers,
        "active": active,
        "queued": queue_size,
        "headroom": headroom,
    }


#: Emit a saturation warning at most this often (seconds) to avoid log spam.
_SATURATION_WARN_COOLDOWN = 60
_last_saturation_warn: float = 0.0
_saturation_lock = threading.Lock()


def warn_if_saturated() -> None:
    """Log a WARNING when the skills pool is at/near capacity.

    Solves R3: without this, a saturated pool accepts new work silently and it
    queues with no feedback — operators see workflows stuck in "running" with
    no clue why. This surfaces the condition through the normal log pipeline
    (rate-limited to one warning per minute).
    """
    global _last_saturation_warn
    stats = pool_stats()
    headroom = stats.get("headroom", 1)
    if headroom > 1:
        return
    now = time.time()
    with _saturation_lock:
        if now - _last_saturation_warn < _SATURATION_WARN_COOLDOWN:
            return
        _last_saturation_warn = now
    logger.warning(
        "⚠️ Skills thread pool near capacity: active={active}/{max_workers} "
        "queued={queued} headroom={headroom}. New skill submissions will queue "
        "until a worker frees up — long-running skills may be blocking the pool. "
        "Check /api/health/metrics and consider SKILLS_POOL_SIZE.",
        **stats,
    )
