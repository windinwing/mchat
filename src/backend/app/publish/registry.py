"""Publisher registry — mirrors ``app/services/devbridge_registry.py``.

Providers register a ``BasePublisher`` subclass keyed by a stable
``provider_key``. Callers resolve a publisher by key without knowing the
concrete class, so new channels can be added without touching the skill
surface or workflow engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.publish.base import BasePublisher
from app.publish.publishers import build_builtin_publishers


@dataclass(slots=True)
class PublisherProvider:
    """Registry entry for one publisher backend.

    Mirrors ``DevBridgeProvider``: a stable key, a human title, advertised
    capability tags, and a factory that returns a ``BasePublisher`` instance.
    """

    key: str
    title: str
    capabilities: list[str]
    factory: Callable[[], BasePublisher]


def _build_registry() -> dict[str, PublisherProvider]:
    providers: dict[str, PublisherProvider] = {}
    for publisher in build_builtin_publishers():
        key = publisher.provider_key
        if not key:
            continue
        providers[key] = PublisherProvider(
            key=key,
            title=_default_title(key),
            capabilities=list(publisher.capabilities),
            factory=(lambda p=publisher: p),
        )
    return providers


def _default_title(key: str) -> str:
    pretty = {
        "feishu": "飞书 Feishu",
        "dingtalk": "钉钉 DingTalk",
        "wecom": "企业微信 WeCom",
        "wechat_mp": "微信公众号",
        "slack": "Slack",
        "telegram_channel": "Telegram Channel",
        "discord": "Discord",
        "twitter_x": "X (Twitter)",
        "facebook": "Facebook",
        "linkedin": "LinkedIn",
        "playwright_client": "客户机 (Playwright)",
    }
    return pretty.get(key, key)


def list_publishers() -> list[PublisherProvider]:
    """Return all registered publisher providers (sorted by key)."""
    return [item for _, item in sorted(_build_registry().items())]


def get_publisher(key: str) -> BasePublisher:
    """Resolve a publisher instance by ``provider_key``.

    Raises ``ValueError`` if no publisher is registered for ``key``.
    """
    normalized = (key or "").strip().lower()
    provider = _build_registry().get(normalized)
    if provider is None:
        raise ValueError(f"Unknown publisher provider: {key!r}")
    return provider.factory()
