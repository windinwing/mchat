"""Playwright runners — one per platform (P3 implements these).

Each runner owns a persistent browser profile for its platform and publishes a
job by fully simulating human behavior (real clicks, typing, random delays,
scrolling). Implemented incrementally; ``get_runner`` returns None for
unimplemented platforms so the agent can fail the job gracefully.

Base class + registry here; concrete runners land in P3.
"""

from __future__ import annotations

from typing import Any


class BaseRunner:
    """Base class for a platform Playwright runner."""

    platform: str = ""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        """Execute the publish. Returns {success, message, remote_id?, remote_url?}."""
        raise NotImplementedError(f"runner for {self.platform} not implemented")


_REGISTRY: dict[str, type[BaseRunner]] = {}


def register(platform: str):
    """Decorator to register a runner class for a platform."""

    def _wrap(cls: type[BaseRunner]) -> type[BaseRunner]:
        cls.platform = platform
        _REGISTRY[platform] = cls
        return cls

    return _wrap


def get_runner(platform: str, cfg: dict[str, Any]) -> BaseRunner | None:
    """Return a runner instance for the platform, or None if unimplemented.

    Lazily imports the platform module so its ``@register`` decorator runs on
    first use (avoiding importing playwright at package load time).
    """
    if platform not in _REGISTRY:
        _load_platform(platform)
    cls = _REGISTRY.get(platform)
    if cls is None:
        return None
    return cls(cfg)


def _load_platform(platform: str) -> None:
    """Import the runner module for ``platform`` if it exists."""
    import importlib

    known = ("xiaohongshu", "douyin", "weibo", "video")
    if platform not in known:
        return
    try:
        importlib.import_module(f"runners.{platform}")
    except Exception:
        # Module-level errors (e.g. missing playwright) shouldn't crash lookup;
        # the caller reports "unsupported" and the job fails cleanly.
        pass
